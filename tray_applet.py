#!/usr/bin/env python3
"""Whispr tray applet — separate subprocess to avoid GTK3/GTK4 conflict.
Uses XApp.StatusIcon (native Cinnamon SNI support).

Protocol (text lines):
  stdin  ← parent:  "enabled:true" / "enabled:false"
  stdout → parent:  "toggle" / "quit"
"""
import sys
import threading
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('XApp', '1.0')
from gi.repository import Gtk, XApp, GLib

enabled = sys.argv[1] == 'true' if len(sys.argv) > 1 else True

_toggle_item = None


def _icon_name(state: bool) -> str:
    return 'audio-input-microphone' if state else 'audio-input-microphone-muted'


status_icon = XApp.StatusIcon.new()
status_icon.set_tooltip_text('Whispr')
status_icon.set_visible(True)
status_icon.set_icon_name(_icon_name(enabled))


def _on_toggle(item):
    print('toggle', flush=True)


def _on_quit(item):
    print('quit', flush=True)
    Gtk.main_quit()


def _make_menu() -> Gtk.Menu:
    global _toggle_item
    menu = Gtk.Menu()

    _toggle_item = Gtk.CheckMenuItem.new_with_label('Enabled')
    _toggle_item.set_active(enabled)
    _toggle_item.connect('activate', _on_toggle)
    menu.append(_toggle_item)

    menu.append(Gtk.SeparatorMenuItem())

    quit_item = Gtk.MenuItem.new_with_label('Quit Whispr')
    quit_item.connect('activate', _on_quit)
    menu.append(quit_item)

    menu.show_all()
    return menu


_menu = _make_menu()
status_icon.set_primary_menu(_menu)
status_icon.set_secondary_menu(_menu)


def _update_state(state: bool) -> bool:
    global enabled
    enabled = state
    status_icon.set_icon_name(_icon_name(state))
    if _toggle_item:
        _toggle_item.handler_block_by_func(_on_toggle)
        _toggle_item.set_active(state)
        _toggle_item.handler_unblock_by_func(_on_toggle)
    return False  # GLib.idle_add: don't repeat


def _stdin_reader():
    for line in sys.stdin:
        cmd = line.strip()
        if cmd.startswith('enabled:'):
            GLib.idle_add(_update_state, cmd[8:] == 'true')


threading.Thread(target=_stdin_reader, daemon=True).start()

Gtk.main()
