import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio
import os
import time

class ScreenRecorder:
    def __init__(self, parent_window, callback_fn):
        self.window = parent_window
        self.callback_fn = callback_fn
        self.recording = False

        self.init_proxy()

    def init_proxy(self):
        try:
            self.proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.NONE,
                None,
                'org.gnome.Shell.Screencast',
                '/org/gnome/Shell/Screencast',
                'org.gnome.Shell.Screencast',
                None
            )
        except GLib.Error as e:
            self.show_error(str(e))

    def start(self):
        if not self.recording:
            try:
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                self.output_path = os.path.join(GLib.get_user_cache_dir(), f"screen-{timestamp}")

                success, path = self.proxy.call_sync(
                    'Screencast',
                    GLib.Variant(
                        '(sa{sv})',
                        (self.output_path, {})
                    ),
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None
                )

                if success:
                    self.recording = True
                    return True

            except GLib.Error as e:
                self.show_error(str(e))

            return False

    def stop(self, *args):
        if self.recording:
            try:
                self.proxy.call_sync(
                    'StopScreencast',
                    None,
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None
                )

                self.recording = False
                widget = self.callback_fn(self.output_path+".mp4")
                widget.convert_path()

            except GLib.Error as e:
                self.show_error(str(e))

    def show_error(self, message):
        dialog = Adw.MessageDialog.new(self.window)
        dialog.set_heading("Error")
        dialog.set_body(str(message))
        dialog.set_modal(True)
        dialog.add_response("ok", "OK")
        dialog.present()
