from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Gdk
from . import config
from . import managers
from . import widgets




@Gtk.Template(resource_path='/io/github/qwersyk/Wienere/window.ui')
class WienereWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'WienereWindow'

    chat_selector = Gtk.Template.Child()
    clear_button = Gtk.Template.Child()
    message_carousel = Gtk.Template.Child()
    message_entry = Gtk.Template.Child()
    attach_button = Gtk.Template.Child()
    image_button = Gtk.Template.Child()
    voice_button = Gtk.Template.Child()
    send_button = Gtk.Template.Child()
    files_box = Gtk.Template.Child()
    carousel_indicator = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.history = []
        self.chats = []
        self.images = []
        self.files = []
        self.is_recording = False
        self.chat = None
        self.config = config.ConfigManager()


        self.chat_list = self.chat_selector.get_model()
        self.setup_signals()
        self.voice_button.set_visible(False)
        self.chats = list(self.config.chats)
        for chat in self.chats:
            self.add_chat(chat)

    def update_config(self):
        configManager = config.ConfigManager()

        if self.chats != list(configManager.chats):
            self.config = None
            while self.chat_list:
                self.chat_list.remove(0)
            self.config = configManager
            self.chats = list(self.config.chats)
            for chat in self.chats:
                self.add_chat(chat)
        else:
            self.config = configManager
    def on_key_pressed(self, controller, keyval, keycode, state):
        if state & Gdk.ModifierType.ALT_MASK:
            if keyval == Gdk.KEY_Up:
                self.navigate_history(1)
                return True
            elif keyval == Gdk.KEY_Down:
                self.navigate_history(-1)
                return True
        return False

    def navigate_history(self, direction):
        if not self.history:
            return

        if self.history_index == -1:
            self.current_input = self.message_entry.get_text()

        new_index = self.history_index + direction
        if 0 <= new_index < len(self.history):
            self.history_index = new_index
            self.message_entry.set_text(self.history[self.history_index])
        elif new_index == -1:
            self.history_index = -1
            self.message_entry.set_text(self.current_input)

    def setup_signals(self):
        self.chat_selector.connect('notify::selected-item', self.on_chat_changed)
        self.clear_button.connect('clicked', self.clear_chat_history)
        self.send_button.connect('clicked', self.on_send_message)
        self.voice_button.connect('clicked', self.on_voice_button_clicked)
        self.attach_button.connect('clicked', self.on_attach_button_clicked)
        self.image_button.connect('clicked', self.on_image_button_clicked)
        self.message_entry.connect('activate', self.on_send_message)

        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_controller)

    def add_chat(self, chat_name):
        self.chat_list.append(chat_name)

    def on_chat_changed(self, dropdown, pspec):
        self.clear_chat_history()

    def stop_current_execution(self):
        if self.chat:
            self.chat.execution_control.stop_all()

    def clear_chat_history(self, *args):
        selected = self.chat_selector.get_selected_item()
        if selected and self.config:
            chat_name = self.chat_selector.get_selected_item().get_string()
            self.stop_current_execution()
            self.chat = managers.chatManagers.get(self.config.chats.get(chat_name)["type"])(chat_name)
            if type(self.chat) != managers.VisionChatManager:
                for i in self.images:
                    self.on_close_file_clicked(i)
            if type(self.chat) != managers.ToolChatManager:
                for i in self.files:
                    self.on_close_file_clicked(i)
            self.set_button()
        while self.message_carousel.get_n_pages() > 0:
            self.message_carousel.remove(self.message_carousel.get_nth_page(0))

    def set_button(self):
        if type(self.chat)==managers.BaseChatManager:
            self.image_button.set_visible(False)
            self.attach_button.set_visible(False)
        if type(self.chat)==managers.ToolChatManager:
            self.image_button.set_visible(False)
            self.attach_button.set_visible(True)
        if type(self.chat)==managers.VisionChatManager:
            self.image_button.set_visible(True)
            self.attach_button.set_visible(False)

    def on_send_message(self, widget):
        message = self.message_entry.get_text()
        if message:
            self.chat.execution_control.stop_all()
            self.message_entry.set_text("")
            self.history.insert(0, message)
            self.history_index = -1
            self.current_input = ""

            if type(self.chat) == managers.ToolChatManager:
                widget = self.chat.send_message(message, self.files)
                for file in self.files:
                    self.on_close_file_clicked(file)
            if type(self.chat) == managers.VisionChatManager:
                widget = self.chat.send_message(message, self.images)
            if type(self.chat) == managers.BaseChatManager:
                widget = self.chat.send_message(message)
            self.new_page(widget)

    def on_voice_button_clicked(self, button):
        self.is_recording = not self.is_recording
        if self.is_recording:
            self.set_voice_chat(True)
            button.set_icon_name("media-playback-stop-symbolic")
        else:
            self.set_voice_chat(False)
            button.set_icon_name("audio-input-microphone-symbolic")

    def on_attach_button_clicked(self, button):
        dialog = Gtk.FileChooserNative.new(
            title="Select a file",
            parent=self,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.set_modal(True)
        dialog.connect("response", self.on_file_chosen)
        dialog.show()

    def on_file_chosen(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                file_path = file.get_path()
                widget = widgets.FileOnPanel(file_path, "file")
                widget.connect("clicked", self.on_close_file_clicked)
                self.files.append(widget)
                self.files_box.append(widget)

        dialog.destroy()

    def on_image_button_clicked(self, button):
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading(_("Add an image"))
        dialog.set_body(_("Would you like to add an image from a file or a URL?"))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("file", _("Choose a file"))
        dialog.add_response("url", _("Enter a URL"))
        dialog.set_default_response("file")
        dialog.set_close_response("cancel")
        dialog.connect("response", self.on_image_dialog_response)
        dialog.present()

    def on_image_dialog_response(self, dialog, response):
        if response == "file":
            self.on_path_dialog_response()
        elif response == "url":
            self.show_url_dialog()
        dialog.destroy()

    def on_path_dialog_response(self):
        dialog = Gtk.FileChooserNative.new(
            title="Select an image",
            parent=self,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.set_modal(True)
        filter_images = Gtk.FileFilter()
        filter_images.set_name("Images")
        filter_images.add_mime_type("image/*")
        dialog.add_filter(filter_images)

        dialog.connect("response", self.on_image_chosen)
        dialog.show()

    def on_image_chosen(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                file_path = file.get_path()
                widget = self.add_url_of_image(file_path)
                widget.convert_path()

    def show_url_dialog(self):
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading(_("Add an image from a URL"))
        dialog.set_body(_("Enter the URL of the image you want to add."))

        url_entry = Gtk.Entry()
        dialog.set_extra_child(url_entry)

        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("ok", -("Ok"))
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")

        dialog.connect("response", self.on_url_dialog_response, url_entry)
        dialog.present()

    def on_url_dialog_response(self, dialog, response, entry):
        if response == "ok":
            url = entry.get_text().strip()
            if url:
                self.add_url_of_image(url)
        dialog.destroy()


    def add_url_of_image(self, url):
        if self.images:
            self.images[0].change_file(url)
        else:
            widget = widgets.FileOnPanel(url, "image")
            widget.connect("clicked", self.on_close_file_clicked)
            self.images = [widget]
            self.files_box.append(widget)
        return widget

    def on_close_file_clicked(self, widget):
        if widget in self.images:
            self.images = []
        if widget in self.files:
            self.files.remove(widget)
        if widget in self.files_box:
            self.files_box.remove(widget)

    def set_voice_chat(self, mode):
        self.voice_button.set_hexpand(mode)
        self.message_entry.set_visible(not mode)
        if mode:
            self.attach_button.set_visible(False)
            self.image_button.set_visible(False)
        else:
            self.set_button()
        self.send_button.set_visible(not mode)

    def new_page(self, widget):
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_child(widget)
        scrolled_window.set_vexpand(True)
        self.message_carousel.append(scrolled_window)
        GLib.idle_add(self.message_carousel.scroll_to, scrolled_window, True)
