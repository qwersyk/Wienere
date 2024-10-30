import json
import threading
from queue import Queue

from gi.repository import Gtk, GLib
import base64
from . import config
from . import tools
from openai import OpenAI
from . import control


class BaseChatManager:
    def __init__(self, name):
        self.messages = []
        self.result = None
        self.name = name
        self.config = config.ConfigManager()
        model = self.config.models.get(self.config.chats.get(name).get("model"))
        self.client = OpenAI(
            api_key=model.get("api_key"),
        )
        if model.get("base_url"):
            self.client.base_url = model.get("base_url")
        self.MODEL = model.get("MODEL")
        if self.config.chats.get(name).get("start_message"):
            self.messages.append({
                "role": "system",
                "content": self.config.chats.get(name).get("start_message"),
            })
        self.lock = threading.Lock()
        self.execution_control = control.ExecutionControl()

    def send_message(self, message):
        with self.lock:
            self.messages.append({
                "role": "user",
                "content": message,
            })
        self.active_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.active_page.set_valign(Gtk.Align.START)
        exec_id = self.execution_control.start_new()
        self.process_message(exec_id)
        return self.active_page

    def process_message(self, exec_id):
        def get_response():
            if not self.execution_control.is_current(exec_id):
                return

            try:
                response = self.client.chat.completions.create(
                    model=self.MODEL,
                    messages=self.get_messages(),
                )
                GLib.idle_add(self.handle_response, response, exec_id)
            except Exception as e:
                GLib.idle_add(self.handle_error, str(e))
        threading.Thread(target=get_response, daemon=True).start()


    def handle_response(self, response, exec_id):
        if not self.execution_control.is_current(exec_id):
            return False

        response_message = response.choices[0].message

        with self.lock:
            self.messages.append(response_message)

        self.display_message(response.choices[0].message.content)

        return False

    def display_message(self, content):
        self.result = content

        self.active_page.append(tools.MarkdownView(content))

    def get_result(self):
        return self.result

    def handle_error(self, error):
        self.result = error
        label = Gtk.Label(label=error)
        label.set_wrap(True)
        label.set_halign(Gtk.Align.START)
        label.set_margin_start(12)
        label.set_margin_end(12)
        self.active_page.append(label)
        return False

    def add_widget_to_page(self, widget):
        self.active_page.append(widget)
        return False

    def get_messages(self):
        return self.messages


class ToolChatManager(BaseChatManager):

    def __init__(self, name):
        super().__init__(name)
        self.tools = []
        for tool_name in self.config.chats.get(name).get("tools"):
            tool = tools.tools.get(self.config.tools.get(tool_name)["type"])(tool_name)
            if type(tool) == tools.ToolMemory:
                self.messages.append({
                    "role": "system",
                    "content": "\n".join(tool.get_note()),
                })
            self.tools.append(tool)

        self.widget_queue = Queue()

    def send_message(self, message, files=None):
        if files:
            self.messages.append({
                "role": "user",
                "content": "Files: " + ", ".join(map(str,files)),
            })
        return super().send_message(message)

    def process_message(self, exec_id):
        def get_response():
            if not self.execution_control.is_current(exec_id):
                return

            try:

                response = self.client.chat.completions.create(
                    model=self.MODEL,
                    messages=self.get_messages(),
                    tools=[tool.get_tool() for tool in self.tools],
                )
                GLib.idle_add(self.handle_response, response, exec_id)
            except Exception as e:
                GLib.idle_add(self.handle_error, str(e))
        threading.Thread(target=get_response, daemon=True).start()


    def handle_response(self, response, exec_id):
        if not self.execution_control.is_current(exec_id):
            return False

        response_message = response.choices[0].message
        if response_message.tool_calls:
            response_message.tool_calls = response_message.tool_calls[:1]
        tool_calls = response_message.tool_calls

        with self.lock:
            self.messages.append(response_message)

        if tool_calls:

            for tool_call in tool_calls:
                self.widget_queue.put((tool_call, exec_id))
            self.process_next_widget(exec_id)
        else:
            self.display_message(response.choices[0].message.content)

        return False

    def process_next_widget(self, exec_id):
        if not self.execution_control.is_current(exec_id) or self.widget_queue.empty():
            if self.widget_queue.empty() and self.execution_control.is_current(exec_id):
                self.process_message(exec_id)
            return

        tool_call, current_exec_id = self.widget_queue.get()
        if current_exec_id != exec_id:
            self.process_next_widget(exec_id)
            return

        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)

        for tool in self.tools:
            if function_name == tool.get_name():
                widget = tool.get_widget(function_args)
                GLib.idle_add(self.add_widget_to_page, widget)

                threading.Thread(
                    target=self.run_widget,
                    args=(widget, tool_call, exec_id),
                    daemon=True
                ).start()
                break

    def run_widget(self, widget, tool_call, exec_id):
        t = threading.Thread(target=widget.run, daemon=True)
        t.start()
        while t.is_alive():
            if not self.execution_control.is_current(exec_id):
                widget.stop()
                return
        if self.execution_control.is_current(exec_id):
            with self.lock:
                self.messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": tool_call.function.name,
                    "widget": widget
                })
            GLib.idle_add(self.process_next_widget, exec_id)

    def get_messages(self):
        with self.lock:
            return [message if "widget" not in message else {k if k != "widget" else "content": str(v) for k, v in
                                                             message.items()} for message in self.messages]


class VisionChatManager(BaseChatManager):
    def send_message(self, message, images=None):

        exec_id = self.execution_control.start_new()

        # with self.lock:
        #     self.messages.append({
        #         "role": "user",
        #         "content": [
        #                        {
        #                            "type": "text",
        #                            "text": message
        #                        },
        #
        #                    ] + [{
        #             "type": "image_url",
        #             "image_url": {
        #                 "url": str(image)
        #             }
        #         } for image in images],
        #     })
        # args = (exec_id,)
        with self.lock:
            self.messages.append({
                "role": "user",
                "content": message,
            })
        args = (exec_id, images)
        self.active_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.process_message(*args)
        return self.active_page

    def process_message(self, exec_id, images=None):
        def get_response():
            if not self.execution_control.is_current(exec_id):
                return
            try:
                response = self.client.chat.completions.create(
                    model=self.MODEL,
                    messages=self.get_messages(images=images),
                )
                GLib.idle_add(self.handle_response, response, exec_id)
            except Exception as e:
                GLib.idle_add(self.handle_error, str(e))
        threading.Thread(target=get_response, daemon=True).start()

    def get_messages(self, images=None):
        if images and self.messages and self.messages[-1]["role"] == "user":

            return self.messages[:-1] + [{
                "role": "user",
                "content": [
                               {
                                   "type": "text",
                                   "text": self.messages[-1]["content"]
                               },

                           ] + [{
                    "type": "image_url",
                    "image_url": {
                        "url": str(image)
                    }
                } for image in images],
            }]
        return self.messages


chatManagers = {
    "tool": ToolChatManager,
    "simple": BaseChatManager,
    "vision": VisionChatManager
}
