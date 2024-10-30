import os
import re
import ast
import time
import json
import subprocess
import threading
import venv
from typing import Optional
from pathlib import Path
from urllib.parse import urljoin

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gio, Adw, GLib, Gdk, Pango, GdkPixbuf

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import markdown

from . import config
from . import managers






class Tool:
    name = None

    def __init__(self, name):
        self.name = name
        self.config = config.ConfigManager()

    def get_dependencies(self):
        return []

    def get_tool(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.config.tools.get(self.name).get("description"),
                "parameters": {
                    "type": "object",
                    "properties": self.get_parameters()

                },
                "required": self.get_required()
            },

        }

    def get_parameters(self):
        pass

    def get_required(self):
        pass

    def get_widget(self, function_args) -> Adw.Bin:
        pass

class Widget(Adw.Bin):
    name = "Widget"
    icon = "applications-system-symbolic"
    def __init__(self):
        super().__init__()
        self.result = ""
        self.expanded = False
        self.set_valign(Gtk.Align.START)
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(self.main_box)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("osd")
        self.main_box.append(self.progress_bar)

        self.header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.header_box.set_margin_top(12)
        self.header_box.set_margin_bottom(12)
        self.header_box.set_margin_start(12)
        self.header_box.set_margin_end(12)
        self.main_box.append(self.header_box)

        self.icon = Gtk.Image.new_from_icon_name(self.icon)
        self.icon.set_pixel_size(24)
        self.header_box.append(self.icon)

        self.title_label = Gtk.Label(label=self.name)
        self.title_label.add_css_class("heading")
        self.title_label.set_hexpand(True)
        self.title_label.set_halign(Gtk.Align.START)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.header_box.append(self.title_label)

        self.details_revealer = Gtk.Revealer()
        self.details_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.main_box.append(self.details_revealer)

        self.details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.details_box.set_margin_top(0)
        self.details_box.set_margin_bottom(12)
        self.details_box.set_margin_start(12)
        self.details_box.set_margin_end(12)
        self.details_revealer.set_child(self.details_box)

        click_controller = Gtk.GestureClick.new()
        click_controller.connect("pressed", self.on_header_clicked)
        self.header_box.add_controller(click_controller)

    def on_header_clicked(self, gesture, n_press, x, y):
        self.expanded = not self.expanded
        self.details_revealer.set_reveal_child(self.expanded)

    def run(self):
        pass

    def set_progress(self, value):
        self.progress_bar.set_fraction(value)

    def stop(self):
        pass

    def __str__(self):
        return self.result

class ToolPython(Tool):
    def get_parameters(self):
        return {
            "name": {
                "type": "string",
                "description": self.config.tools.get(self.name).get("name_description"),
            },
            "code": {
                "type": "string",
                "description": self.config.tools.get(self.name).get("code_description"),
            },
            "modules": {
                "type": "array",
                "items": {"type": "string"},
                "description": self.config.tools.get(self.name).get("modules_description"),
            }
        }

    def get_dependencies(self):
        return ["name_description", "code_description", "modules_description"]

    def get_required(self):
        return ["name", "code"]

    def get_widget(self, function_args) -> Adw.Bin:
        return WidgetPython(
            function_args.get("name", "Python Code"),
            function_args.get("code"),
            function_args.get("modules", [])
        )

    def get_name(self):
        return self.name


class ExpressionFinder(ast.NodeVisitor):
    def __init__(self):
        self.expressions = []
        self.last_lineno = 0

    def visit_Expr(self, node):
        self.expressions.append((node.lineno, node))
        self.last_lineno = max(self.last_lineno, node.lineno)
        self.generic_visit(node)


class WidgetPython(Widget):
    injection = """
import builtins

def custom_input(prompt=""):
    print(f"__INPUT_HANDLER__{prompt}", flush=True)
    return builtins.input()

input = custom_input

import getpass

def custom_getpass(prompt="Password: "):
    print(f"__GETPASS_HANDLER__{prompt}", flush=True)
    return builtins.input()

getpass.getpass = custom_getpass
"""
    def __init__(self, name, code, modules):
        self.code = code
        self.background = False
        self.modules = modules
        self.name = name

        self.icon = "applications-system-symbolic"

        self.installed_modules_file = os.path.join(GLib.get_user_config_dir(), "installed_modules.json")
        self.installed_modules = self.load_installed_modules()
        self.venv_dir = os.path.join(GLib.get_user_cache_dir(), "python_venv")
        self.create_virtual_env()

        super().__init__()

        self.command_entry = Gtk.Entry()
        self.command_entry.set_text(self.code)
        self.command_entry.set_editable(False)
        self.command_entry.set_hexpand(True)
        self.command_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-copy-symbolic")
        self.details_box.append(self.command_entry)

        self.command_entry.connect("icon-release", self.on_copy_clicked)

        self.output_view = Gtk.TextView()
        self.output_view.set_editable(False)
        self.output_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.output_view.set_css_classes(["monospace"])
        self.output_buffer = self.output_view.get_buffer()

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_child(self.output_view)
        scrolled_window.set_vexpand(True)
        scrolled_window.set_propagate_natural_height(True)
        self.details_box.append(scrolled_window)

        if self.modules:
            self.modules_list = {}
            flow_box = Gtk.FlowBox()
            flow_box.set_valign(Gtk.Align.START)
            flow_box.set_selection_mode(Gtk.SelectionMode.NONE)
            flow_box.set_homogeneous(False)
            flow_box.set_max_children_per_line(1000)
            label = Gtk.Label(label=f"Modules:")
            label.set_halign(Gtk.Align.START)
            flow_box.append(label)
            for module in modules:
                label = Gtk.Label(label=module)
                label.set_halign(Gtk.Align.START)
                if module in self.installed_modules:
                    label.add_css_class("success")
                else:
                    label.add_css_class("warning")
                flow_box.append(label)
                self.modules_list[module] = label
            self.details_box.append(flow_box)

    def create_virtual_env(self):
        if not os.path.exists(self.venv_dir):
            venv.create(self.venv_dir, with_pip=True)
            self.update_output("Virtual environment created.")

    def on_copy_clicked(self, entry, icon_pos):
        clipboard = self.get_display().get_clipboard()
        clipboard.set(self.code)

    def load_installed_modules(self):
        if os.path.exists(self.installed_modules_file):
            with open(self.installed_modules_file, 'r') as f:
                return set(json.load(f))
        return set()

    def save_installed_modules(self):
        with open(self.installed_modules_file, 'w') as f:
            json.dump(list(self.installed_modules), f)

    def run(self):
        def execute_action():
            modules_to_install = [m for m in self.modules if m not in self.installed_modules]
            if modules_to_install:
                event = threading.Event()
                GLib.idle_add(self.show_module_install_dialog, modules_to_install, event)
                event.wait()

            self.execute_code()

        if not self.background:
            execute_action()
        else:
            thread = threading.Thread(target=execute_action)
            thread.start()

    def show_module_install_dialog(self, modules_to_install, event):
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            "Install Required Modules",
            f"This code requires the following modules:\n{', '.join(modules_to_install)}\n\nDo you want to install them?"
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("install", "Install")
        dialog.set_default_response("install")
        dialog.set_close_response("cancel")

        dialog.connect("response", self.on_install_dialog_response, modules_to_install, event)
        dialog.present()

    def on_install_dialog_response(self, dialog, response, modules_to_install, event):
        if response == "install":
            thread = threading.Thread(target=self.install_modules, args=(modules_to_install, event))
            thread.start()
        else:
            self.update_output("Module installation cancelled.")
            event.set()

        dialog.destroy()

    def install_modules(self, modules_to_install, event):
        for module in modules_to_install:
            try:
                self.update_output(f"Installing {module} in virtual environment...")
                subprocess.check_call([os.path.join(self.venv_dir, "bin", "python"), "-m", "pip", "install", module])
                self.update_output(f"{module} installed successfully.")
                self.installed_modules.add(module)
                self.modules_list[module].set_css_classes(["success"])

            except subprocess.CalledProcessError as e:
                self.update_output(f"Failed to install {module}: {e}")
                self.modules_list[module].set_css_classes(["error"])

        self.save_installed_modules()
        event.set()

    def input(self, prompt="", password=False):
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            "Input Required" if not password else "Password Required",
            prompt,
        )
        if password:
            entry = Gtk.PasswordEntry()
        else:
            entry = Gtk.Entry()
            entry.set_activates_default(True)
        entry.set_margin_top(12)
        entry.set_margin_bottom(12)
        entry.set_margin_start(12)
        entry.set_margin_end(12)



        dialog.set_extra_child(entry)


        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")

        result = None

        def on_response(dialog, response):
            nonlocal result
            if response == "ok":
                result = entry.get_text()
            dialog.destroy()

        dialog.connect("response", on_response)


        dialog.present()

        while result is None:
            if not dialog.is_visible():
                return ""
            time.sleep(0.1)

        return result

    def execute_code(self):
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{env.get('PYTHONPATH', '')}:{os.getcwd()}"
            process = subprocess.Popen(
                [os.path.join(self.venv_dir, "bin", "python"), "-c", self.injection+self.wrap_code_with_expression_capture()],
                text=True,
                env=env,
                cwd=GLib.get_user_data_dir(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
                universal_newlines=True
            )
            self.result= ""
            input_requested = False

            try:
                while True:

                    line = process.stdout.readline()
                    print(line)
                    if line == '' and process.poll() is not None:
                        break

                    if line.startswith("__INPUT_HANDLER__"):
                        input_requested = True
                        prompt = line[17:]
                        user_input = self.input(prompt.strip())
                        self.result+="\n"+prompt.strip()+user_input
                        process.stdin.write(user_input + "\n")
                        process.stdin.flush()
                    elif line.startswith("__GETPASS_HANDLER__"):
                        input_requested = True
                        prompt = line[19:]
                        user_input = self.input(prompt.strip(), password=True)
                        self.result+="\n"+prompt.strip()+"********"
                        process.stdin.write(user_input + "\n")
                        process.stdin.flush()
                    else:
                        self.result+="\n"+line.strip()
                        if input_requested:
                            input_requested = False

            finally:
                process.stdin.close()
                process.wait()
            self.command_entry.add_css_class("success")
            self.progress_bar.add_css_class("success")
            if not self.result:
                self.result = "Done"
        except Exception as e:
            self.result = str(e)
            self.command_entry.add_css_class("error")
            self.progress_bar.add_css_class("error")

        GLib.idle_add(self.update_output, self.result)
        GLib.idle_add(self.set_progress, 1)

    def wrap_code_with_expression_capture(self):
        try:
            tree = ast.parse(self.code)

            finder = ExpressionFinder()
            finder.visit(tree)

            lines = self.code.split('\n')

            new_lines = []
            current_line = 0

            for line_num, line in enumerate(lines, 1):

                new_lines.append(line)
                current_line += 1

                for expr_line, expr_node in finder.expressions:
                    if expr_line == line_num:

                        expr_text = line.strip()

                        if (not expr_text.startswith('print') and
                                not expr_text.startswith('#') and
                                not expr_text.startswith('"""') and
                                not expr_text.startswith("'''")):

                            indentation = len(line) - len(line.lstrip())
                            indent = ' ' * indentation

                            capture_code = (
                                f"{indent}_expr_result = {expr_text}\n"
                                f"{indent}if _expr_result is not None:\n"
                                f"{indent}    print(f'[Expression Output]: {{repr(_expr_result)}}')"
                            )
                            new_lines.append(capture_code)
                            current_line += 3

            return '\n'.join(new_lines)
        except SyntaxError:

            return self.code

    def update_output(self, text):
        def do_update():
            end_iter = self.output_buffer.get_end_iter()
            self.output_buffer.insert(end_iter, text + "\n")

        GLib.idle_add(do_update)



class ToolMemory(Tool):
    def __init__(self, name):
        super().__init__(name)
        self.memory_file = os.path.join(GLib.get_user_config_dir(), f"{self.name}_memory.json")
        if not os.path.exists(self.memory_file):
            with open(self.memory_file, 'w') as file:
                json.dump([], file)

    def get_dependencies(self):
        return ["note_description"]

    def get_widget(self, function_args) -> Adw.Bin:
        return WidgetMemory(function_args.get("note", "None"), self.memory_file)

    def get_parameters(self):
        return {
            "note": {
                "type": "string",
                "description": self.config.tools.get(self.name).get("note_description"),
            },
        }

    def get_required(self):
        return ["note"]

    def get_name(self):
        return self.name

    def get_note(self):
        with open(self.memory_file, 'r') as file:
            return json.load(file)


class WidgetMemory(Widget):
    def __init__(self, note, memory_file):
        self.note = note
        self.memory_file = memory_file

        self.icon = "text-editor-symbolic"
        self.name = "Memory"

        super().__init__()


        self.output_view = Gtk.TextView()
        self.output_view.set_editable(False)
        self.output_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.output_view.set_css_classes(["monospace"])
        self.output_buffer = self.output_view.get_buffer()

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_child(self.output_view)
        scrolled_window.set_vexpand(True)
        self.details_box.append(scrolled_window)

    def run(self):
        with open(self.memory_file, 'r') as file:
            notes = json.load(file)
        notes.append(self.note)
        with open(self.memory_file, 'w') as file:
            json.dump(notes, file)
        self.output_buffer.set_text(str(self.note))
        self.set_progress(1)
        self.progress_bar.add_css_class("success")


class ToolURLTextExtractor(Tool):

    def get_dependencies(self):
        return ["name_description", "url_description"]

    def get_parameters(self):
        return {
            "name": {
                "type": "string",
                "description": self.config.tools.get(self.name).get("name_description"),
            },
            "url": {
                "type": "string",
                "description": self.config.tools.get(self.name).get("url_description"),
            },
        }

    def get_required(self):
        return ["name", "url"]

    def get_widget(self, function_args) -> Adw.Bin:
        return WidgetURLTextExtractor(
            function_args.get("name", "URL Text Extractor"),
            function_args.get("url", "")
        )

    def get_name(self):
        return self.name


class WidgetURLTextExtractor(Widget):
    def __init__(self, name, url):
        self.url = url
        self.icon = "web-browser-symbolic"
        self.name = name

        super().__init__()

        self.url_entry = Gtk.Entry()
        self.url_entry.set_text(self.url)
        self.url_entry.set_editable(False)
        self.url_entry.set_hexpand(True)
        self.url_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-copy-symbolic")
        self.details_box.append(self.url_entry)

        self.url_entry.connect("icon-release", self.on_copy_clicked)

        self.output_view = Gtk.TextView()
        self.output_view.set_editable(False)
        self.output_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.output_buffer = self.output_view.get_buffer()

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_child(self.output_view)
        scrolled_window.set_vexpand(True)
        self.details_box.append(scrolled_window)


    def on_copy_clicked(self, entry, icon_pos):
        clipboard = self.get_display().get_clipboard()
        clipboard.set(self.url)

    def run(self):
        self.execute_extraction()

    def execute_extraction(self):
        try:
            self.set_progress(0.1)
            self.update_output("Fetching URL...")
            headers = {'User-Agent': UserAgent().random}
            response = requests.get(self.url, headers=headers, timeout=10)
            response.raise_for_status()
            self.set_progress(0.3)
            self.update_output("Parsing content...")
            soup = BeautifulSoup(response.text, 'html.parser')

            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()

            self.set_progress(0.5)
            self.update_output("Extracting text...")
            content = []
            for element in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'a']):
                text = element.get_text(strip=True)

                if element.name == 'a' and element.has_attr('href'):
                    link_url = urljoin(self.url, element['href'])
                    content.append(f"{text} [{link_url}]")
                else:
                    content.append(text)

            self.set_progress(0.8)
            self.update_output("Formatting result...")
            self.result = '\n\n'.join(content)
            self.result = re.sub(r'\n\s*\n', '\n\n', self.result)
            self.result = re.sub(r'\s+', ' ', self.result)

            self.set_progress(1.0)
            self.url_entry.add_css_class("success")
            self.progress_bar.add_css_class("success")
            self.update_output(self.result)
        except Exception as e:
            self.result = str(e)
            self.url_entry.add_css_class("error")
            self.progress_bar.add_css_class("error")
            self.update_output(f"Error: {self.result}")

        self.set_progress(1.0)

    def update_output(self, text):
        def do_update():
            self.output_buffer.set_text(text)

        GLib.idle_add(do_update)



class ToolRunBasicChat(Tool):

    def get_dependencies(self):
        return ["name_description", "message_description", "chat"]

    def get_parameters(self):
        return {
            "name": {
                "type": "string",
                "description": self.config.tools.get(self.name).get("name_description"),
            },
            "message": {
                "type": "string",
                "description": self.config.tools.get(self.name).get("message_description"),
            },
        }

    def get_required(self):
        return ["name", "message"]

    def get_widget(self, function_args) -> Adw.Bin:
        return WidgetRunSimpleChat(
            function_args.get("name", "Chat"),
            function_args.get("message"),
            self.config.tools.get(self.name).get("chat")
        )

    def get_name(self):
        return self.name


class WidgetRunSimpleChat(Widget):
    def __init__(self, name, message, chat):

        self.message = message
        self.chat_name = chat
        self.icon = "user-available-symbolic"
        self.name = name

        self.config = config.ConfigManager()

        super().__init__()

        self.message_entry = Gtk.Entry()
        self.message_entry.set_text(self.message)
        self.message_entry.set_editable(False)
        self.message_entry.set_hexpand(True)
        self.message_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-copy-symbolic")
        self.details_box.append(self.message_entry)

        self.message_entry.connect("icon-release", self.on_copy_clicked)

        self.output_view = Gtk.Box()

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_child(self.output_view)
        scrolled_window.set_vexpand(True)

        scrolled_window.set_propagate_natural_height(True)
        self.details_box.append(scrolled_window)



    def on_copy_clicked(self, entry, icon_pos):
        clipboard = self.get_display().get_clipboard()
        clipboard.set(self.message)

    def run(self):
        self.chat = managers.chatManagers.get(self.config.chats.get(self.chat_name)["type"])(self.chat_name)
        widget = self.chat.send_message(self.message)
        self.output_view.append(widget)
        while self.chat.result == None:
            continue

        self.result = self.chat.get_result() if self.chat.get_result() else ""
        self.set_progress(1)

    def stop(self):
        self.chat.result = ""
        self.chat.execution_control.stop_all()





class MarkdownView(Gtk.Box):
    def __init__(self, text: str = ""):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12
        )
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_top(12)
        self.set_margin_bottom(12)

        if text:
            self.set_markdown(text)


    def set_markdown(self, text: str):
        self._clear_content()

        extensions = [
            'tables',
            'fenced_code',
            'def_list'
        ]

        html = markdown.markdown(text, extensions=extensions)
        soup = BeautifulSoup(html, 'html.parser')

        for element in soup.children:
            if element.name:
                self._process_element(element)

    def _clear_content(self):
        while child := self.get_first_child():
            self.remove(child)

    def _create_label_with_markup(self, element, heading_level: Optional[int] = None) -> Gtk.Widget:
        if isinstance(element, str):
            label = Gtk.Label(label=element, wrap=True)
            label.set_halign(Gtk.Align.START)
            label.set_selectable(True)
            return label

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box.set_halign(Gtk.Align.START)

        attr_list = Pango.AttrList()
        text_parts = []
        current_pos = 0
        current_widget = None

        if heading_level is not None:
            sizes = {1: 24, 2: 20, 3: 18, 4: 16, 5: 14, 6: 13}
            size = sizes.get(heading_level, 13)
            scale_attr = Pango.attr_scale_new(size / 13)
            scale_attr.start_index = 0
            scale_attr.end_index = 0xFFFF
            attr_list.insert(scale_attr)

            weight_attr = Pango.attr_weight_new(Pango.Weight.BOLD)
            weight_attr.start_index = 0
            weight_attr.end_index = 0xFFFF
            attr_list.insert(weight_attr)

        for node in element.children:
            if isinstance(node, str):
                if text_parts or not current_widget:
                    text_parts.append(node)
                continue

            if text_parts:
                text = ''.join(text_parts)
                label = Gtk.Label(label=text, wrap=True)
                label.set_attributes(attr_list)
                label.set_halign(Gtk.Align.START)
                label.set_selectable(True)
                box.append(label)
                text_parts = []
                attr_list = Pango.AttrList()
                current_pos = 0

            if node.name == 'a':
                link = Gtk.LinkButton(uri=node.get('href', ''), label=node.get_text())
                link.set_halign(Gtk.Align.START)
                link.add_css_class('flat')
                box.append(link)
                current_widget = link

            elif node.name in ['strong', 'b']:
                text = node.get_text()
                attr = Pango.attr_weight_new(Pango.Weight.BOLD)
                attr.start_index = current_pos
                attr.end_index = current_pos + len(text.encode('utf-8'))
                attr_list.insert(attr)
                text_parts.append(text)
                current_pos += len(text)
                current_widget = None

            elif node.name in ['em', 'i']:
                text = node.get_text()
                attr = Pango.attr_style_new(Pango.Style.ITALIC)
                attr.start_index = current_pos
                attr.end_index = current_pos + len(text.encode('utf-8'))
                attr_list.insert(attr)
                text_parts.append(text)
                current_pos += len(text)
                current_widget = None

            elif node.name == 'code':
                text = node.get_text()
                font_desc = Pango.FontDescription()
                font_desc.set_family("monospace")
                attr = Pango.attr_font_desc_new(font_desc)
                attr.start_index = current_pos
                attr.end_index = current_pos + len(text.encode('utf-8'))
                attr_list.insert(attr)
                text_parts.append(text)
                current_pos += len(text)
                current_widget = None

            elif node.name in ['del', 's']:
                text = node.get_text()
                attr = Pango.attr_strikethrough_new(True)
                attr.start_index = current_pos
                attr.end_index = current_pos + len(text.encode('utf-8'))
                attr_list.insert(attr)
                text_parts.append(text)
                current_pos += len(text)
                current_widget = None

        if text_parts:
            text = ''.join(text_parts)
            label = Gtk.Label(label=text, wrap=True)
            label.set_attributes(attr_list)
            label.set_halign(Gtk.Align.START)
            label.set_selectable(True)
            box.append(label)

        if box.get_first_child() == None:
            return Gtk.Label()

        if box.get_first_child() == box.get_last_child():
            return box.get_first_child()

        return box



    def _process_element(self, element):
        if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(element.name[1])
            label = self._create_label_with_markup(element, level)
            self.append(label)

        elif element.name == 'p':
            img = element.find('img')
            if img:
                self._add_image(img.get('src', ''), img.get('alt', ''))
            else:
                label = self._create_label_with_markup(element)
                self.append(label)

        elif element.name in ['ul', 'ol']:
            self._add_list(element)

        elif element.name == 'pre':
            self._add_code_block(element)

        elif element.name == 'blockquote':
            self._add_blockquote(element)

        elif element.name == 'table':
            self._add_table(element)

        elif element.name == 'hr':
            separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            separator.set_margin_top(10)
            separator.set_margin_bottom(10)
            self.append(separator)

    def _add_image(self, src: str, alt: str):
        try:
            if src.startswith("http://") or src.startswith("https://"):
                response = requests.get(src, stream=True)
                response.raise_for_status()
                input_stream = Gio.MemoryInputStream.new_from_data(response.content)
                pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
                    input_stream,
                    width=330,
                    height=-1,
                    preserve_aspect_ratio=True,
                    cancellable=None
                )
            else:
                path = Path(src)
                if path.exists():
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        str(path),
                        width=330,
                        height=-1,
                        preserve_aspect_ratio=True
                    )
                else:
                    pixbuf = None
            if pixbuf:
                picture = Gtk.Picture()

                picture.set_pixbuf(pixbuf)
                picture.set_halign(Gtk.Align.START)
                picture.set_can_shrink(True)
                picture.set_keep_aspect_ratio(True)

                picture.set_size_request(330, 330)

                if alt:
                    picture.set_tooltip_text(alt)

                self.append(picture)
        except (GLib.Error, requests.RequestException) as e:
            print(f"Error: {src}: {e}")

    def _add_list(self, element, level: int = 0):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        box.set_margin_start(20 * level)

        is_ordered = element.name == 'ol'
        for i, item in enumerate(element.find_all('li', recursive=False)):
            item_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

            bullet = Gtk.Label()
            if is_ordered:
                bullet.set_text(f"{i + 1}.")
            else:
                bullet.set_text("•")
            bullet.set_margin_end(5)
            item_box.append(bullet)

            content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

            for child in item.children:
                if child.name in ['ul', 'ol']:
                    self._add_list(child, level + 1)
                else:
                    text = child.get_text().strip()
                    if text:
                        label = self._create_label_with_markup(text)
                        content_box.append(label)

            item_box.append(content_box)
            box.append(item_box)

        self.append(box)

    def _add_code_block(self, element):
        code_element = element.find('code')
        if not code_element:
            return

        lang = None
        if 'class' in code_element.attrs:
            classes = code_element.attrs['class']
            lang_classes = [c for c in classes if c.startswith('language-')]
            if lang_classes:
                lang = lang_classes[0].replace('language-', '')

        code_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)


        if lang:
            header_box = Gtk.Box()
            header_box.set_margin_bottom(1)

            lang_label = Gtk.Label(label=lang.upper())
            lang_label.set_margin_start(10)
            lang_label.set_margin_top(5)
            lang_label.set_margin_bottom(5)
            lang_label.set_margin_end(10)

            header_box.append(lang_label)
            code_box.append(header_box)
            separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            code_box.append(separator)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)

        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_css_classes(["monospace"])
        text_view.set_wrap_mode(Gtk.WrapMode.NONE)
        text_view.set_margin_start(10)
        text_view.set_margin_end(10)
        text_view.set_margin_top(10)
        text_view.set_margin_bottom(10)

        buffer = text_view.get_buffer()
        buffer.set_text(code_element.get_text().strip())

        scrolled.set_child(text_view)
        code_box.append(scrolled)

        self.append(code_box)

    def _add_blockquote(self, element):
        quote_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        quote_box.set_margin_start(10)

        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        quote_box.append(separator)

        text = element.get_text().strip()
        status_map = {
            "[!CAUTION]": ("🛑CAUTION", "error"),
            "[!WARNING]": ("⚠️Warning", "warning"),
            "[!IMPORTANT]": ("❗Important", "important"),
            "[!TIP]": ("💡Tip", "tip"),
            "[!NOTE]": ("📝Note", "note"),
        }

        for key, (replacement, css_class) in status_map.items():
            pattern = re.compile(re.escape(key), re.IGNORECASE)
            if pattern.match(text):
                text = pattern.sub(replacement, text)
                quote_box.add_css_class(css_class)
                break

        label = self._create_label_with_markup(text)
        quote_box.append(label)
        self.append(quote_box)

    def _add_table(self, element):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)

        grid = Gtk.Grid()
        grid.set_row_spacing(1)
        grid.set_column_spacing(1)

        header_row = element.find('thead')
        if header_row:
            for col_idx, th in enumerate(header_row.find_all('th')):
                label = Gtk.Label(label=th.get_text().strip())
                grid.attach(label, col_idx, 0, 1, 1)

        tbody = element.find('tbody')
        if tbody:
            for row_idx, tr in enumerate(tbody.find_all('tr'), start=1):
                for col_idx, td in enumerate(tr.find_all('td')):
                    label = Gtk.Label(label=td.get_text().strip())
                    grid.attach(label, col_idx, row_idx, 1, 1)

        scrolled.set_child(grid)

        self.append(scrolled)


tools = {
    "python": ToolPython,
    "memory": ToolMemory,
    "urlTextExtractor": ToolURLTextExtractor,
    "runSimpleChat": ToolRunBasicChat
}
