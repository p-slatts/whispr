#!/usr/bin/env python3
"""
Whispr System Tray - AppIndicator integration for GNOME/Pop!_OS
"""

import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import AppIndicator3, GLib, Gtk  # noqa: E402


class WhisprTray:
    """System tray icon and menu for Whispr"""

    # Icon names (must be installed in icon theme or use absolute paths)
    ICON_IDLE = "whispr-symbolic"
    ICON_RECORDING = "whispr-recording-symbolic"
    ICON_TRANSCRIBING = "whispr-transcribing-symbolic"

    def __init__(self, whispr_instance):
        """
        Initialize tray icon

        Args:
            whispr_instance: Reference to main Whispr instance for callbacks
        """
        self.whispr = whispr_instance
        self.indicator = None
        self.menu = None
        self.status_item = None
        self.record_item = None
        self.recent_menu = None
        self.autostart_item = None

        # Recent transcriptions (stored in whispr instance)
        self._setup_indicator()

    def _get_icon_path(self, icon_name: str) -> str:
        """Get full path to icon file"""
        # First check local icons directory (development)
        local_path = Path(__file__).parent / "icons" / f"{icon_name}.svg"
        if local_path.exists():
            return str(local_path)

        # Check installed location
        installed_path = (
            Path.home() / ".local/share/icons/hicolor/scalable/apps" / f"{icon_name}.svg"
        )
        if installed_path.exists():
            return str(installed_path)

        # Fall back to icon name (let GTK find it)
        return icon_name

    def _setup_indicator(self):
        """Create the AppIndicator"""
        self.indicator = AppIndicator3.Indicator.new(
            "whispr",
            self._get_icon_path(self.ICON_IDLE),
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Whispr")

        # Build menu
        self._build_menu()
        self.indicator.set_menu(self.menu)

    def _build_menu(self):
        """Build the tray menu"""
        self.menu = Gtk.Menu()

        # Status item (non-clickable)
        self.status_item = Gtk.MenuItem(label="Whispr Ready")
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Start/Stop recording
        self.record_item = Gtk.MenuItem(label="Start Recording")
        self.record_item.connect("activate", self._on_record_clicked)
        self.menu.append(self.record_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Recent transcriptions submenu
        recent_item = Gtk.MenuItem(label="Recent Transcriptions")
        self.recent_menu = Gtk.Menu()
        self._update_recent_menu()
        recent_item.set_submenu(self.recent_menu)
        self.menu.append(recent_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Autostart toggle
        self.autostart_item = Gtk.CheckMenuItem(label="Run at Startup")
        self.autostart_item.set_active(self._is_autostart_enabled())
        self.autostart_item.connect("toggled", self._on_autostart_toggled)
        self.menu.append(self.autostart_item)

        # Settings
        settings_item = Gtk.MenuItem(label="Settings...")
        settings_item.connect("activate", self._on_settings_clicked)
        self.menu.append(settings_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Quit
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self._on_quit_clicked)
        self.menu.append(quit_item)

        self.menu.show_all()

    def _update_recent_menu(self):
        """Update the recent transcriptions submenu"""
        # Clear existing items
        for child in self.recent_menu.get_children():
            self.recent_menu.remove(child)

        # Get recent transcriptions from whispr
        recent = (
            self.whispr.get_recent_transcriptions()
            if hasattr(self.whispr, "get_recent_transcriptions")
            else []
        )

        if recent:
            for _i, text in enumerate(recent[:5]):
                # Truncate long text
                display_text = text[:40] + "..." if len(text) > 40 else text
                display_text = display_text.replace("\n", " ")
                item = Gtk.MenuItem(label=display_text)
                item.connect("activate", self._on_recent_clicked, text)
                self.recent_menu.append(item)

            self.recent_menu.append(Gtk.SeparatorMenuItem())

            clear_item = Gtk.MenuItem(label="Clear History")
            clear_item.connect("activate", self._on_clear_history)
            self.recent_menu.append(clear_item)
        else:
            empty_item = Gtk.MenuItem(label="(No recent transcriptions)")
            empty_item.set_sensitive(False)
            self.recent_menu.append(empty_item)

        self.recent_menu.show_all()

    def _is_autostart_enabled(self) -> bool:
        """Check if autostart is enabled"""
        autostart_file = Path.home() / ".config/autostart/whispr.desktop"
        return autostart_file.exists()

    def _on_record_clicked(self, widget):
        """Handle record button click"""
        if hasattr(self.whispr, "toggle_recording"):
            self.whispr.toggle_recording()

    def _on_recent_clicked(self, widget, text: str):
        """Copy recent transcription to clipboard"""
        try:
            subprocess.run(["xsel", "-ib"], input=text.encode(), check=True, timeout=1)
            self.whispr._notify("Whispr", "Copied to clipboard")
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

    def _on_clear_history(self, widget):
        """Clear transcription history"""
        if hasattr(self.whispr, "clear_transcription_history"):
            self.whispr.clear_transcription_history()
        self._update_recent_menu()

    def _on_autostart_toggled(self, widget):
        """Toggle autostart"""
        if hasattr(self.whispr, "set_autostart"):
            self.whispr.set_autostart(widget.get_active())
        else:
            self._set_autostart(widget.get_active())

    def _set_autostart(self, enabled: bool):
        """Enable or disable autostart"""
        autostart_dir = Path.home() / ".config/autostart"
        autostart_file = autostart_dir / "whispr.desktop"

        if enabled:
            autostart_dir.mkdir(parents=True, exist_ok=True)
            # Copy or create desktop file
            source_file = Path(__file__).parent / "whispr-autostart.desktop"
            if source_file.exists():
                import shutil

                shutil.copy(source_file, autostart_file)
            else:
                # Create basic autostart file
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

    def _on_settings_clicked(self, widget):
        """Open settings dialog"""
        if hasattr(self.whispr, "show_settings"):
            self.whispr.show_settings()

    def _on_quit_clicked(self, widget):
        """Quit application"""
        if self.whispr.app:
            self.whispr.app.quit()

    def set_state(self, state: str):
        """
        Update tray icon and menu based on state

        Args:
            state: One of 'idle', 'waiting', 'recording', 'transcribing'
        """
        if state == "recording":
            self.indicator.set_icon_full(self._get_icon_path(self.ICON_RECORDING), "Recording")
            GLib.idle_add(self._update_status, "Recording...")
            GLib.idle_add(self._update_record_label, "Stop Recording")
        elif state == "transcribing":
            self.indicator.set_icon_full(
                self._get_icon_path(self.ICON_TRANSCRIBING), "Transcribing"
            )
            GLib.idle_add(self._update_status, "Transcribing...")
            GLib.idle_add(self._update_record_label, "Processing...")
        else:  # idle or waiting
            self.indicator.set_icon_full(self._get_icon_path(self.ICON_IDLE), "Ready")
            GLib.idle_add(self._update_status, "Whispr Ready")
            GLib.idle_add(self._update_record_label, "Start Recording")

    def _update_status(self, text: str):
        """Update status menu item (must be called from main thread)"""
        if self.status_item:
            self.status_item.set_label(text)

    def _update_record_label(self, text: str):
        """Update record menu item label (must be called from main thread)"""
        if self.record_item:
            self.record_item.set_label(text)
            # Disable during transcription
            self.record_item.set_sensitive(text != "Processing...")

    def on_transcription_complete(self, text: str):
        """Called when a transcription is complete"""
        GLib.idle_add(self._update_recent_menu)
