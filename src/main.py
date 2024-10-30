import sys
import gi
import subprocess

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Gio, Adw, GLib, Gdk
from .window import WienereWindow
from .config import ConfigWindow




class WienereApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id='io.github.qwersyk.Wienere',
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.create_action('quit', lambda *_: self.quit(), ['<primary>q'])
        self.create_action('about', self.on_about_action)
        self.create_action('preferences', self.on_preferences_action)
        self.create_action('open-folder', self.on_open_folder_action)
        self._setup_styles()


    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = WienereWindow(application=self)
        win.present()

    def on_about_action(self, *args):
        about = Adw.AboutDialog(application_name='Wienere',
                                application_icon='io.github.qwersyk.Wienere',
                                developer_name='qwersyk',
                                version='0.1.0',
                                developers=['qwersyk'],
                                copyright='© 2024 qwersyk')
        about.present(self.props.active_window)

    def on_open_folder_action(self, *args):
        data_path = GLib.get_user_data_dir()
        folder_uri = GLib.filename_to_uri(data_path)

        success = Gio.AppInfo.launch_default_for_uri(folder_uri, None)

    def _setup_styles(self):
        """Настройка CSS стилей для виджета"""
        css_provider = Gtk.CssProvider()
        css = """
        .important {
            color: rgb(130, 80, 223);
        }
        .tip {
            color: rgb(26, 127, 55);
        }
        .note {
            color: rgb(9, 105, 218);
        }
        """
        css_provider.load_from_data(css.encode())

        display = Gdk.Display.get_default()
        Gtk.StyleContext.add_provider_for_display(
            display,
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def on_preferences_action(self, widget, _):
        ConfigWindow(application=self, win=self.props.active_window).present()

    def update_config(self):
        win = self.props.active_window
        if win:
            win.update_config()

    def create_action(self, name, callback, shortcuts=None):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)


def main(version):
    app = WienereApplication()
    return app.run(sys.argv)
