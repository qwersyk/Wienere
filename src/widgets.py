from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import GObject
import base64

class FileOnPanel(Adw.Bin):
    __gsignals__ = {
        'clicked': (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self, file, type):
        super().__init__()

        self.set_size_request(200, -1)

        self.file = file
        self.type = type
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        if self.type == "image":
            image = Gtk.Image.new_from_icon_name("x-office-drawing-symbolic")
        else:
            image = Gtk.Image.new_from_icon_name("text-x-generic-symbolic")
        image.set_size_request(20, 20)
        box.append(image)
        self.label = Gtk.Label(label=file)
        self.label.set_ellipsize(Pango.EllipsizeMode.START)
        self.label.set_max_width_chars(12)
        box.append(self.label)
        if self.type == "image":
            pin_icon = Gtk.Image.new_from_icon_name("view-pin-symbolic")
            box.append(pin_icon)

        close_button = Gtk.Button()
        close_icon = Gtk.Image.new_from_icon_name("window-close-symbolic")
        close_button.set_child(close_icon)
        close_button.add_css_class("flat")
        close_button.add_css_class("circular")
        close_button.connect("clicked", self.on_close_clicked)
        box.append(close_button)
        self.set_child(box)

    def convert_path(self):
        try:
            with open(self.file, "rb") as image_file:
                self.file = "data:image/jpeg;base64,"+base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            print(f"Error encoding image: {str(e)}")
            self.file = None

    def on_close_clicked(self, button):
        self.emit("clicked")


    def change_file(self, file):
        self.file = file
        self.label.set_text(file)

    def get_file(self):
        return self.file

    def get_type(self):
        return self.type
    def __str__(self):
        return self.file
