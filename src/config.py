from gi.repository import Gtk, Gio, Adw, GLib
import json
import os

CONFIG_FILE =  os.path.join(GLib.get_user_config_dir(), 'config.json')



class ConfigManager:
    def __init__(self):

        self.config = {"models": {}, "tools": {}, "chats": {}}

        self.load_config()
        self.models = self.config["models"]
        self.tools = self.config["tools"]
        self.chats = self.config["chats"]

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                self.config = json.load(f)
        else:
            self.save_config()

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=2)

    def add_item(self, category, name, data):
        self.config[category][name] = data
        self.save_config()

    def update_item(self, category, name, data):
        if name in self.config[category]:
            self.config[category][name] = data
            self.save_config()

    def remove_item(self, category, name):
        if name in self.config[category]:
            del self.config[category][name]
            self.save_config()

    def get_item(self, category, name):
        return self.config[category].get(name)

    def get_all_items(self, category):
        return self.config[category]

class ConfigWindow(Adw.PreferencesWindow):
    def __init__(self, win, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_transient_for(win)
        self.set_modal(True)

        self.win = win

        self.config_manager = ConfigManager()

        self.set_title(_("Configuration Manager"))
        self.set_default_size(360, 500)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(self.main_box)

        header_bar = Adw.HeaderBar()
        self.main_box.append(header_bar)

        self.stack = Adw.ViewStack()
        self.stack.set_vexpand(True)
        switcher = Adw.ViewSwitcherBar()
        switcher.set_stack(self.stack)

        view_switcher_title = Adw.ViewSwitcherTitle()
        view_switcher_title.set_stack(self.stack)

        view_switcher_title.set_title("Configuration")

        header_bar.set_title_widget(view_switcher_title)

        self.main_box.append(self.stack)
        self.main_box.append(switcher)

        self.show_stacks()
        view_switcher_title.connect("notify::title-visible",
                                    lambda _, __: switcher.set_reveal(view_switcher_title.get_title_visible()))
        self.connect("close-request", self.on_window_close)

    def on_window_close(self, *args):
        self.win.update_config()
        self.close()


    def show_stacks(self):
        self.create_config_page("Models", "models", "system-run-symbolic")
        self.create_config_page("Tools", "tools", "applications-system-symbolic")
        self.create_config_page("Chats", "chats", "user-available-symbolic")
    def create_config_page(self, title, category, icon):
        page = Adw.PreferencesPage()
        page.title = title
        page.icon_name = icon
        self.stack.add_titled_with_icon(page, category, title, icon)

        group = Adw.PreferencesGroup()
        page.add(group)

        for name, data in self.config_manager.get_all_items(category).items():
            row = self.create_config_row(name, data, category)
            group.add(row)

        add_button = Gtk.Button(label=f"Add {title.rstrip('s')}")
        add_button.connect("clicked", self.on_add_item_clicked, category)
        add_button.add_css_class("suggested-action")
        add_button.set_margin_top(12)
        group.add(add_button)

    def create_config_row(self, name, data, category):
        row = Adw.ActionRow(title=name, subtitle=data.get('type', ''))

        edit_button = Gtk.Button(icon_name="document-edit-symbolic")
        edit_button.set_valign(Gtk.Align.CENTER)
        edit_button.connect("clicked", self.on_edit_item_clicked, category, name)
        row.add_suffix(edit_button)

        delete_button = Gtk.Button(icon_name="user-trash-symbolic")
        delete_button.set_valign(Gtk.Align.CENTER)
        delete_button.add_css_class("destructive-action")
        delete_button.connect("clicked", self.on_delete_item_clicked, category, name)
        row.add_suffix(delete_button)

        return row

    def on_add_item_clicked(self, button, category):
        self.show_item_dialog(category)

    def on_edit_item_clicked(self, button, category, name):
        self.show_item_dialog(category, name)

    def show_item_dialog(self, category, name=None):
        from . import tools
        dialog = Adw.Window(transient_for=self, modal=True)
        dialog.set_default_size(400, -1)
        dialog.category = category

        header_bar = Adw.HeaderBar()
        header_bar.set_show_end_title_buttons(False)

        cancel_button = Gtk.Button(label=_("Cancel"))
        cancel_button.connect("clicked", lambda _: dialog.close())
        header_bar.pack_start(cancel_button)

        save_button = Gtk.Button(label=_("Save"))
        save_button.add_css_class("suggested-action")
        save_button.connect("clicked", self.on_save_item, dialog, category, name)
        header_bar.pack_end(save_button)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(header_bar)

        content = Adw.PreferencesPage()
        box.append(content)

        dialog.set_content(box)

        group = Adw.PreferencesGroup()
        content.add(group)

        dialog.name_entry = Adw.EntryRow(title=_("Name"))
        group.add(dialog.name_entry)

        dialog.type_combo = Adw.ComboRow(title=_("Type"))
        if category == "tools":
            types=["python", "memory", "urlTextExtractor", "runSimpleChat"]

        else:
            types=["tool", "simple", "vision"]
        type_store = Gtk.StringList.new(types)
        dialog.type_combo.set_model(type_store)


        group.add(dialog.type_combo)
        if category == "models":
            dialog.api_key_entry = Adw.PasswordEntryRow(title=_("API Key"))
            group.add(dialog.api_key_entry)

            dialog.base_url_entry = Adw.EntryRow(title=_("Base URL"))
            group.add(dialog.base_url_entry)

            dialog.model_entry = Adw.EntryRow(title=_("Model"))
            group.add(dialog.model_entry)

        if category == "tools":
            dialog.descriptions = {}
            for tool_name, tool_object in tools.tools.items():
                for description in tool_object.get_dependencies(None):
                    if description not in dialog.descriptions:
                        dialog.descriptions[description] = Adw.EntryRow(title=description)
                        group.add(dialog.descriptions[description])
                        dialog.descriptions[description].set_visible(False)

            dialog.description_entry = Adw.EntryRow(title=_("Description"))
            group.add(dialog.description_entry)
            dialog.type_combo.connect("notify::selected-item", self.on_type_combo_changed, dialog)
            self.on_type_combo_changed(dialog.type_combo, None, dialog)


        if category == "chats":
            dialog.start_message_entry = Adw.EntryRow(title=_("Start Message"))
            group.add(dialog.start_message_entry)

            dialog.tools_entry = Adw.EntryRow(title=_("Tools (comma-separated)"))
            group.add(dialog.tools_entry)

            dialog.model_entry = Adw.EntryRow(title=_("Model"))
            group.add(dialog.model_entry)
            dialog.type_combo.connect("notify::selected-item", self.on_type_combo_changed, dialog)
            self.on_type_combo_changed(dialog.type_combo, None, dialog)

        if name:
            item_data = self.config_manager.get_item(category, name)
            dialog.name_entry.set_text(name)
            dialog.type_combo.set_selected(types.index(item_data["type"]))
            if category == "models":
                dialog.api_key_entry.set_text(item_data.get("api_key", ""))
                dialog.base_url_entry.set_text(item_data.get("base_url", ""))
                dialog.model_entry.set_text(item_data.get("MODEL", ""))
            if category == "tools":
                dialog.description_entry.set_text(item_data.get("description", ""))
                for description_name, description_entry in dialog.descriptions.items():
                    description_entry.set_text(item_data.get(description_name, ""))
            if category == "chats":
                dialog.start_message_entry.set_text(item_data.get("start_message", ""))
                dialog.tools_entry.set_text(", ".join(item_data.get("tools", [])))
                dialog.model_entry.set_text(item_data.get("model", ""))



        dialog.present()

    def on_type_combo_changed(self, combo, _, dialog):
        from . import tools
        if dialog.category == "tools":
            for description_name ,description_entry in dialog.descriptions.items():
                description_entry.set_visible(description_name in tools.tools[combo.get_selected_item().get_string()].get_dependencies(None))
        if dialog.category == "chats":
            dialog.tools_entry.set_visible(combo.get_selected_item().get_string()=="tool")
    def on_save_item(self, button, dialog, category, old_name):
        name = dialog.name_entry.get_text()
        item_data = {
            "type": dialog.type_combo.get_selected_item().get_string(),
        }
        if category == "models":
            item_data["api_key"] = dialog.api_key_entry.get_text()
            item_data["base_url"] = dialog.base_url_entry.get_text()
            item_data["MODEL"] = dialog.model_entry.get_text()

        if category == "tools":
            item_data["description"] = dialog.description_entry.get_text()
            for description_name, description_entry in dialog.descriptions.items():
                item_data[description_name] = description_entry.get_text()

        if category == "chats":
            item_data["start_message"] = dialog.start_message_entry.get_text()
            item_data["tools"] = [tool.strip() for tool in dialog.tools_entry.get_text().split(',')]
            item_data["model"] = dialog.model_entry.get_text()

        if old_name and old_name != name:
            self.config_manager.remove_item(category, old_name)

        self.config_manager.add_item(category, name, item_data)
        self.refresh_pages(category)
        dialog.close()

    def on_delete_item_clicked(self, button, category, name):
        dialog = Adw.MessageDialog(
            transient_for=self,
            modal=True,
            heading=_("Delete ") + str(category.rstrip('s').capitalize()),
            body=_("Are you sure you want to delete ")+str(name)+"?",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_delete_dialog_response, category, name)
        dialog.present()

    def on_delete_dialog_response(self, dialog, response, category, name):
        if response == "delete":
            self.config_manager.remove_item(category, name)
            self.refresh_pages(category)

    def refresh_pages(self,category):


        while page := self.stack.get_first_child():
            self.stack.remove(page)

        self.show_stacks()
        self.stack.set_visible_child_name(category)
