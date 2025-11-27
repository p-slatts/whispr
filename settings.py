#!/usr/bin/env python3
"""
Whispr Settings Dialog - GTK configuration interface
"""

import gi

gi.require_version("Gtk", "3.0")
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

from gi.repository import Gtk  # noqa: E402


class WhisprSettingsDialog(Gtk.Window):
    """Settings dialog for Whispr configuration"""

    def __init__(self, whispr_instance, parent=None):
        """
        Initialize settings dialog

        Args:
            whispr_instance: Reference to main Whispr instance
            parent: Parent window (optional)
        """
        super().__init__(title="Whispr Settings")
        self.whispr = whispr_instance
        self.config = whispr_instance.config

        self.set_default_size(500, 450)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)

        if parent:
            self.set_transient_for(parent)
            self.set_modal(True)

        # Track changes
        self._changes: dict[str, Any] = {}

        self._build_ui()

    def _build_ui(self):
        """Build the settings UI"""
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_box)

        # Notebook (tabs)
        notebook = Gtk.Notebook()
        notebook.set_margin_start(10)
        notebook.set_margin_end(10)
        notebook.set_margin_top(10)
        main_box.pack_start(notebook, True, True, 0)

        # General tab
        general_page = self._create_general_page()
        notebook.append_page(general_page, Gtk.Label(label="General"))

        # Transcription tab
        transcription_page = self._create_transcription_page()
        notebook.append_page(transcription_page, Gtk.Label(label="Transcription"))

        # Output tab
        output_page = self._create_output_page()
        notebook.append_page(output_page, Gtk.Label(label="Output"))

        # Button box
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_margin_start(10)
        button_box.set_margin_end(10)
        button_box.set_margin_top(10)
        button_box.set_margin_bottom(10)
        main_box.pack_end(button_box, False, False, 0)

        # Buttons
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", self._on_cancel)
        button_box.pack_start(cancel_btn, False, False, 0)

        # Spacer
        button_box.pack_start(Gtk.Box(), True, True, 0)

        apply_btn = Gtk.Button(label="Apply")
        apply_btn.connect("clicked", self._on_apply)
        button_box.pack_end(apply_btn, False, False, 0)

        ok_btn = Gtk.Button(label="OK")
        ok_btn.get_style_context().add_class("suggested-action")
        ok_btn.connect("clicked", self._on_ok)
        button_box.pack_end(ok_btn, False, False, 0)

        self.show_all()

    def _create_section_label(self, text: str) -> Gtk.Label:
        """Create a section header label"""
        label = Gtk.Label()
        label.set_markup(f"<b>{text}</b>")
        label.set_halign(Gtk.Align.START)
        label.set_margin_top(15)
        label.set_margin_bottom(5)
        return label

    def _create_general_page(self) -> Gtk.Widget:
        """Create the General settings page"""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        page.set_margin_start(15)
        page.set_margin_end(15)
        page.set_margin_top(10)
        page.set_margin_bottom(10)

        # Trigger Keys section
        page.pack_start(self._create_section_label("Trigger Keys"), False, False, 0)

        keys_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)

        current_keys = self.config.trigger_keys.lower().split(",")
        current_keys = [k.strip() for k in current_keys]

        self.key_checkboxes = {}
        for key_name, key_label in [
            ("alt", "Alt"),
            ("print_screen", "Print Screen"),
            ("ctrl", "Ctrl"),
            ("super", "Super"),
        ]:
            cb = Gtk.CheckButton(label=key_label)
            cb.set_active(key_name in current_keys)
            cb.connect("toggled", self._on_key_toggled)
            self.key_checkboxes[key_name] = cb
            keys_box.pack_start(cb, False, False, 0)

        page.pack_start(keys_box, False, False, 0)

        # Hold Duration
        page.pack_start(self._create_section_label("Hold Duration"), False, False, 0)

        duration_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        duration_label = Gtk.Label(label="Hold key for")
        duration_box.pack_start(duration_label, False, False, 0)

        self.duration_spin = Gtk.SpinButton()
        self.duration_spin.set_range(0.1, 3.0)
        self.duration_spin.set_increments(0.1, 0.5)
        self.duration_spin.set_digits(1)
        self.duration_spin.set_value(self.config.hold_duration)
        self.duration_spin.connect("value-changed", self._on_duration_changed)
        duration_box.pack_start(self.duration_spin, False, False, 0)

        duration_label2 = Gtk.Label(label="seconds before recording starts")
        duration_box.pack_start(duration_label2, False, False, 0)

        page.pack_start(duration_box, False, False, 0)

        # Startup section
        page.pack_start(self._create_section_label("Startup"), False, False, 0)

        self.autostart_check = Gtk.CheckButton(label="Start Whispr automatically when you log in")
        self.autostart_check.set_active(self._is_autostart_enabled())
        self.autostart_check.connect("toggled", self._on_autostart_toggled)
        page.pack_start(self.autostart_check, False, False, 0)

        return page

    def _create_transcription_page(self) -> Gtk.Widget:
        """Create the Transcription settings page"""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        page.set_margin_start(15)
        page.set_margin_end(15)
        page.set_margin_top(10)
        page.set_margin_bottom(10)

        # Backend selection
        page.pack_start(self._create_section_label("Transcription Backend"), False, False, 0)

        self.backend_radios = {}

        # Local whisper.cpp
        local_radio = Gtk.RadioButton.new_with_label(None, "Local whisper.cpp")
        local_radio.connect("toggled", self._on_backend_changed, "local")
        self.backend_radios["local"] = local_radio
        page.pack_start(local_radio, False, False, 0)

        # Model path (for local)
        model_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        model_box.set_margin_start(25)
        model_label = Gtk.Label(label="Model:")
        model_box.pack_start(model_label, False, False, 0)

        self.model_entry = Gtk.Entry()
        self.model_entry.set_text(self.config.whisper_model or "")
        self.model_entry.set_hexpand(True)
        self.model_entry.set_placeholder_text("Path to .bin model file")
        self.model_entry.connect("changed", self._on_model_changed)
        model_box.pack_start(self.model_entry, True, True, 0)

        model_browse = Gtk.Button(label="Browse...")
        model_browse.connect("clicked", self._on_browse_model)
        model_box.pack_start(model_browse, False, False, 0)

        self.model_box = model_box
        page.pack_start(model_box, False, False, 0)

        # Server mode
        server_radio = Gtk.RadioButton.new_with_label_from_widget(local_radio, "Whisper.cpp Server")
        server_radio.connect("toggled", self._on_backend_changed, "server")
        self.backend_radios["server"] = server_radio
        page.pack_start(server_radio, False, False, 0)

        # Server address
        server_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        server_box.set_margin_start(25)
        server_label = Gtk.Label(label="Server:")
        server_box.pack_start(server_label, False, False, 0)

        self.server_entry = Gtk.Entry()
        self.server_entry.set_text(self.config.whisper_server or "")
        self.server_entry.set_placeholder_text("127.0.0.1:58080")
        self.server_entry.connect("changed", self._on_server_changed)
        server_box.pack_start(self.server_entry, True, True, 0)

        self.server_box = server_box
        page.pack_start(server_box, False, False, 0)

        # OpenAI API
        openai_radio = Gtk.RadioButton.new_with_label_from_widget(local_radio, "OpenAI Whisper API")
        openai_radio.connect("toggled", self._on_backend_changed, "openai")
        self.backend_radios["openai"] = openai_radio
        page.pack_start(openai_radio, False, False, 0)

        # API key
        api_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        api_box.set_margin_start(25)
        api_label = Gtk.Label(label="API Key:")
        api_box.pack_start(api_label, False, False, 0)

        self.api_entry = Gtk.Entry()
        self.api_entry.set_text(self.config.openai_api_key or "")
        self.api_entry.set_visibility(False)
        self.api_entry.set_placeholder_text("sk-...")
        self.api_entry.connect("changed", self._on_api_key_changed)
        api_box.pack_start(self.api_entry, True, True, 0)

        show_key = Gtk.CheckButton(label="Show")
        show_key.connect("toggled", lambda w: self.api_entry.set_visibility(w.get_active()))
        api_box.pack_start(show_key, False, False, 0)

        self.api_box = api_box
        page.pack_start(api_box, False, False, 0)

        # Set current backend
        if self.config.use_openai:
            openai_radio.set_active(True)
        elif self.config.whisper_server:
            server_radio.set_active(True)
        else:
            local_radio.set_active(True)

        self._update_backend_ui()

        return page

    def _create_output_page(self) -> Gtk.Widget:
        """Create the Output settings page"""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        page.set_margin_start(15)
        page.set_margin_end(15)
        page.set_margin_top(10)
        page.set_margin_bottom(10)

        # Text Output section
        page.pack_start(self._create_section_label("Text Output"), False, False, 0)

        self.auto_paste_check = Gtk.CheckButton(
            label="Automatically paste transcribed text at cursor"
        )
        self.auto_paste_check.set_active(self.config.auto_paste)
        self.auto_paste_check.connect("toggled", self._on_paste_toggled)
        page.pack_start(self.auto_paste_check, False, False, 0)

        self.clipboard_check = Gtk.CheckButton(label="Copy transcribed text to clipboard")
        self.clipboard_check.set_active(self.config.copy_to_clipboard)
        self.clipboard_check.connect("toggled", self._on_clipboard_toggled)
        page.pack_start(self.clipboard_check, False, False, 0)

        # Feedback section
        page.pack_start(self._create_section_label("Feedback"), False, False, 0)

        self.sounds_check = Gtk.CheckButton(label="Play sounds for recording start/stop")
        self.sounds_check.set_active(getattr(self.config, "play_sounds", True))
        self.sounds_check.connect("toggled", self._on_sounds_toggled)
        page.pack_start(self.sounds_check, False, False, 0)

        self.notifications_check = Gtk.CheckButton(label="Show desktop notifications")
        self.notifications_check.set_active(getattr(self.config, "show_notifications", True))
        self.notifications_check.connect("toggled", self._on_notifications_toggled)
        page.pack_start(self.notifications_check, False, False, 0)

        return page

    def _is_autostart_enabled(self) -> bool:
        """Check if autostart is enabled"""
        autostart_file = Path.home() / ".config/autostart/whispr.desktop"
        return autostart_file.exists()

    def _update_backend_ui(self):
        """Update UI based on selected backend"""
        local_active = self.backend_radios["local"].get_active()
        server_active = self.backend_radios["server"].get_active()
        openai_active = self.backend_radios["openai"].get_active()

        self.model_box.set_sensitive(local_active)
        self.server_box.set_sensitive(server_active)
        self.api_box.set_sensitive(openai_active)

    # Event handlers
    def _on_key_toggled(self, widget):
        keys = [k for k, cb in self.key_checkboxes.items() if cb.get_active()]
        if keys:
            self._changes["trigger_keys"] = ",".join(keys)

    def _on_duration_changed(self, widget):
        self._changes["hold_duration"] = widget.get_value()

    def _on_autostart_toggled(self, widget):
        self._changes["autostart"] = widget.get_active()

    def _on_backend_changed(self, widget, backend: str):
        if widget.get_active():
            if backend == "local":
                self._changes["use_openai"] = False
                self._changes["whisper_server"] = ""
            elif backend == "server":
                self._changes["use_openai"] = False
            elif backend == "openai":
                self._changes["use_openai"] = True
            self._update_backend_ui()

    def _on_model_changed(self, widget):
        self._changes["whisper_model"] = widget.get_text()

    def _on_server_changed(self, widget):
        self._changes["whisper_server"] = widget.get_text()

    def _on_api_key_changed(self, widget):
        self._changes["openai_api_key"] = widget.get_text()

    def _on_paste_toggled(self, widget):
        self._changes["auto_paste"] = widget.get_active()

    def _on_clipboard_toggled(self, widget):
        self._changes["copy_to_clipboard"] = widget.get_active()

    def _on_sounds_toggled(self, widget):
        self._changes["play_sounds"] = widget.get_active()

    def _on_notifications_toggled(self, widget):
        self._changes["show_notifications"] = widget.get_active()

    def _on_browse_model(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Select Whisper Model", parent=self, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )

        filter_bin = Gtk.FileFilter()
        filter_bin.set_name("Whisper Models (*.bin)")
        filter_bin.add_pattern("*.bin")
        dialog.add_filter(filter_bin)

        filter_all = Gtk.FileFilter()
        filter_all.set_name("All Files")
        filter_all.add_pattern("*")
        dialog.add_filter(filter_all)

        # Start in AI/Models if it exists
        models_dir = Path.home() / "AI" / "Models" / "whisper"
        if models_dir.exists():
            dialog.set_current_folder(str(models_dir))

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.model_entry.set_text(dialog.get_filename())

        dialog.destroy()

    def _apply_changes(self):
        """Apply all changes to config"""
        # Handle autostart separately
        if "autostart" in self._changes:
            self._set_autostart(self._changes.pop("autostart"))

        # Apply config changes
        for key, value in self._changes.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

        # Save config
        self.config.save()

        # Notify whispr of changes
        if hasattr(self.whispr, "reload_config"):
            self.whispr.reload_config()

        self._changes.clear()

    def _set_autostart(self, enabled: bool):
        """Enable or disable autostart"""
        autostart_dir = Path.home() / ".config/autostart"
        autostart_file = autostart_dir / "whispr.desktop"

        if enabled:
            autostart_dir.mkdir(parents=True, exist_ok=True)
            content = """[Desktop Entry]
Name=Whispr
Comment=Voice to text with hold-to-talk
Exec=whispr --tray
Icon=whispr
Type=Application
X-GNOME-Autostart-enabled=true
Hidden=false
"""
            autostart_file.write_text(content)
        else:
            if autostart_file.exists():
                autostart_file.unlink()

    def _on_cancel(self, widget):
        self._changes.clear()
        self.destroy()

    def _on_apply(self, widget):
        self._apply_changes()

    def _on_ok(self, widget):
        self._apply_changes()
        self.destroy()
