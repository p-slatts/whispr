#!/usr/bin/env python3
"""Whispr tray applet — separate subprocess to avoid GTK3/GTK4 conflict.
Uses Gtk.StatusIcon (XEmbed) which Cinnamon's notification area displays.

Protocol (text lines):
  stdin  ← parent:  "enabled:true" / "enabled:false"
  stdout → parent:  "toggle" / "quit"
"""
import sys
import atexit
import os
import tempfile
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

enabled = sys.argv[1] == 'true' if len(sys.argv) > 1 else True

_toggle_item = None
_icon_paths: dict = {}


def _render_w_icon(active: bool) -> str:
    """Render bold-italic W on panel background colour, return temp PNG path."""
    from PIL import Image, ImageDraw, ImageFont
    panel_bg = (235, 235, 237)
    fg = (20, 20, 20) if active else (170, 170, 172)
    size = 256
    img = Image.new('RGB', (size, size), panel_bg)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            '/usr/share/fonts/opentype/inter/Inter-BoldItalic.otf', 210)
    except Exception:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), 'W', font=font)
    x = (size - (bbox[2] - bbox[0])) // 2 - bbox[0]
    y = (size - (bbox[3] - bbox[1])) // 2 - bbox[1]
    d.text((x, y), 'W', fill=fg, font=font)
    tmp = tempfile.mktemp(suffix='.png')
    img.save(tmp)
    atexit.register(lambda p=tmp: os.path.exists(p) and os.unlink(p))
    return tmp


try:
    _icon_paths[True] = _render_w_icon(True)
    _icon_paths[False] = _render_w_icon(False)
    _use_w = True
except Exception:
    _use_w = False


def _set_icon(state: bool):
    if _use_w:
        status_icon.set_from_file(_icon_paths[state])
    else:
        status_icon.set_from_icon_name(
            'audio-input-microphone' if state else 'audio-input-microphone-muted')


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

status_icon = Gtk.StatusIcon.new()
status_icon.set_tooltip_text('Whispr')
status_icon.set_visible(True)
_set_icon(enabled)


def _on_popup_menu(icon, button, time):
    _menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, time)


def _on_activate(icon):
    _menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, 0,
                Gtk.get_current_event_time())


status_icon.connect('popup-menu', _on_popup_menu)
status_icon.connect('activate', _on_activate)


def _update_state(state: bool) -> bool:
    global enabled
    enabled = state
    _set_icon(state)
    if _toggle_item:
        _toggle_item.handler_block_by_func(_on_toggle)
        _toggle_item.set_active(state)
        _toggle_item.handler_unblock_by_func(_on_toggle)
    return False


def _stdin_reader():
    for line in sys.stdin:
        cmd = line.strip()
        if cmd.startswith('enabled:'):
            GLib.idle_add(_update_state, cmd[8:] == 'true')


threading.Thread(target=_stdin_reader, daemon=True).start()

Gtk.main()
