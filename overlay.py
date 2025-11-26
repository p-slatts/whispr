#!/usr/bin/env python3
"""
Whispr Overlay - Beautiful animated recording indicator
Designed to be minimal yet informative, like WisprFlow
"""

import math
import cairo

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Graphene


class WhisprOverlay(Gtk.Window):
    """
    Beautiful floating overlay showing recording state
    Features:
    - Pulsing waveform animation during recording
    - Smooth transitions between states
    - Minimal, non-intrusive design
    """

    def __init__(self):
        super().__init__()

        # Window setup
        self.set_title("Whispr")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(200, 80)

        # Make it float above everything
        self.set_modal(False)

        # State
        self.is_recording = False
        self.is_transcribing = False
        self.animation_phase = 0.0
        self.waveform_data = [0.0] * 20  # Audio level history
        self.animation_id = None

        # Drawing area for custom rendering
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_content_width(200)
        self.drawing_area.set_content_height(80)
        self.drawing_area.set_draw_func(self._draw)
        self.set_child(self.drawing_area)

        # Apply CSS for transparency
        self._setup_css()

    def _setup_css(self):
        """Setup transparent window styling"""
        css = b"""
        window {
            background-color: transparent;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _draw(self, area, cr, width, height):
        """Custom drawing for the overlay"""
        # Clear with transparency
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        # Draw rounded rectangle background
        radius = 20
        self._draw_rounded_rect(cr, 0, 0, width, height, radius)

        if self.is_transcribing:
            # Blue gradient for transcribing
            gradient = cairo.LinearGradient(0, 0, width, 0)
            gradient.add_color_stop_rgba(0, 0.1, 0.3, 0.5, 0.92)
            gradient.add_color_stop_rgba(1, 0.15, 0.4, 0.6, 0.92)
            cr.set_source(gradient)
        else:
            # Dark gradient for recording
            gradient = cairo.LinearGradient(0, 0, width, 0)
            gradient.add_color_stop_rgba(0, 0.12, 0.12, 0.15, 0.92)
            gradient.add_color_stop_rgba(1, 0.15, 0.15, 0.18, 0.92)
            cr.set_source(gradient)

        cr.fill_preserve()

        # Draw border
        if self.is_recording:
            # Pulsing red border
            pulse = 0.5 + 0.5 * math.sin(self.animation_phase * 2)
            cr.set_source_rgba(0.9, 0.2, 0.2, 0.6 + 0.4 * pulse)
            cr.set_line_width(3)
        elif self.is_transcribing:
            # Cyan border
            cr.set_source_rgba(0.2, 0.8, 0.9, 0.8)
            cr.set_line_width(2)
        else:
            cr.set_source_rgba(0.5, 0.5, 0.5, 0.5)
            cr.set_line_width(1)

        cr.stroke()

        if self.is_recording:
            self._draw_recording_state(cr, width, height)
        elif self.is_transcribing:
            self._draw_transcribing_state(cr, width, height)

    def _draw_rounded_rect(self, cr, x, y, w, h, r):
        """Draw a rounded rectangle path"""
        cr.new_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _draw_recording_state(self, cr, width, height):
        """Draw recording indicator with waveform"""
        # Pulsing red dot
        cx = 30
        cy = height / 2
        pulse = 0.8 + 0.2 * math.sin(self.animation_phase * 3)

        # Glow effect
        for i in range(3):
            glow_radius = 12 + i * 4
            alpha = 0.3 - i * 0.1
            cr.set_source_rgba(0.9, 0.2, 0.2, alpha * pulse)
            cr.arc(cx, cy, glow_radius, 0, 2 * math.pi)
            cr.fill()

        # Main dot
        cr.set_source_rgba(0.95, 0.25, 0.25, 1.0)
        cr.arc(cx, cy, 8 * pulse, 0, 2 * math.pi)
        cr.fill()

        # Waveform visualization
        wave_x = 55
        wave_width = width - 70
        wave_height = 30
        wave_y = height / 2

        # Draw waveform bars
        bar_count = len(self.waveform_data)
        bar_width = wave_width / bar_count - 2

        for i, level in enumerate(self.waveform_data):
            x = wave_x + i * (wave_width / bar_count)

            # Animated level with some smoothing
            animated_level = level * (0.8 + 0.2 * math.sin(self.animation_phase * 4 + i * 0.3))
            bar_height = max(4, wave_height * animated_level)

            # Gradient color based on level
            r = 0.9 + 0.1 * level
            g = 0.3 - 0.2 * level
            b = 0.3 - 0.2 * level

            cr.set_source_rgba(r, g, b, 0.9)

            # Draw rounded bar
            self._draw_rounded_rect(
                cr,
                x, wave_y - bar_height / 2,
                bar_width, bar_height,
                2
            )
            cr.fill()

        # "Recording" text
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(11)
        cr.set_source_rgba(1, 1, 1, 0.7)
        cr.move_to(wave_x, height - 10)
        cr.show_text("Recording...")

    def _draw_transcribing_state(self, cr, width, height):
        """Draw transcribing indicator with spinner"""
        cx = width / 2
        cy = height / 2 - 5

        # Spinning arc
        start_angle = self.animation_phase * 2
        arc_length = math.pi * 1.2

        # Glow
        cr.set_source_rgba(0.2, 0.8, 0.9, 0.3)
        cr.set_line_width(6)
        cr.arc(cx, cy, 18, start_angle, start_angle + arc_length)
        cr.stroke()

        # Main arc
        cr.set_source_rgba(0.3, 0.9, 1.0, 0.9)
        cr.set_line_width(3)
        cr.arc(cx, cy, 18, start_angle, start_angle + arc_length)
        cr.stroke()

        # "Transcribing" text
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(11)
        cr.set_source_rgba(1, 1, 1, 0.8)

        text = "Transcribing..."
        extents = cr.text_extents(text)
        cr.move_to(cx - extents.width / 2, height - 10)
        cr.show_text(text)

    def show_recording(self):
        """Show recording state"""
        self.is_recording = True
        self.is_transcribing = False
        self.waveform_data = [0.3] * 20  # Initial waveform
        self._start_animation()
        self._center_on_screen()
        self.present()

    def show_transcribing(self):
        """Show transcribing state"""
        self.is_recording = False
        self.is_transcribing = True
        self.drawing_area.queue_draw()

    def hide_overlay(self):
        """Hide the overlay"""
        self._stop_animation()
        self.is_recording = False
        self.is_transcribing = False
        self.set_visible(False)

    def update_audio_level(self, level: float):
        """Update audio level for waveform visualization"""
        # Shift waveform data and add new level
        self.waveform_data = self.waveform_data[1:] + [min(1.0, level)]

    def _center_on_screen(self):
        """Center the overlay on the primary monitor"""
        display = Gdk.Display.get_default()
        if display:
            monitors = display.get_monitors()
            if monitors.get_n_items() > 0:
                monitor = monitors.get_item(0)
                geom = monitor.get_geometry()

                # Position at bottom center
                x = geom.x + (geom.width - 200) // 2
                y = geom.y + geom.height - 150

                # GTK4 doesn't have move(), we need to use surface API
                # For now, rely on window manager

    def _start_animation(self):
        """Start animation loop"""
        if self.animation_id is None:
            self.animation_id = GLib.timeout_add(33, self._animate)  # ~30fps

    def _stop_animation(self):
        """Stop animation loop"""
        if self.animation_id is not None:
            GLib.source_remove(self.animation_id)
            self.animation_id = None

    def _animate(self) -> bool:
        """Animation tick"""
        self.animation_phase += 0.1

        # Simulate audio levels when recording (will be replaced with real data)
        if self.is_recording:
            import random
            # Add some natural-looking variation
            base = 0.3 + 0.4 * math.sin(self.animation_phase * 0.5)
            noise = random.uniform(-0.15, 0.15)
            self.update_audio_level(max(0.1, min(1.0, base + noise)))

        self.drawing_area.queue_draw()
        return True


# Standalone test
if __name__ == '__main__':
    import sys

    app = Gtk.Application(application_id='com.whispr.overlay.test')

    def on_activate(app):
        overlay = WhisprOverlay()
        overlay.set_application(app)
        overlay.show_recording()

        # Test state transitions
        def switch_to_transcribing():
            overlay.show_transcribing()
            return False

        def hide():
            overlay.hide_overlay()
            app.quit()
            return False

        GLib.timeout_add(3000, switch_to_transcribing)
        GLib.timeout_add(5000, hide)

    app.connect('activate', on_activate)
    app.run()
