#!/usr/bin/env python3
"""
Whispr - WisprFlow-style speech-to-text for Linux
Hold Alt or Print Screen key to record, release to transcribe and paste.

Features:
- Hold-to-talk activation (configurable key and duration)
- Beautiful animated overlay with real-time audio visualization
- Multiple transcription backends (whisper.cpp local, server, OpenAI API)
- Auto-paste to active window
- System tray integration for GNOME/Pop!_OS
- Integrates with existing BlahST configuration
"""

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

# Global debug flag
DEBUG = False

# Global tray mode flag (set before GTK import)
TRAY_MODE = "--tray" in sys.argv


def debug(msg: str):
    """Print debug message if debug mode is enabled"""
    if DEBUG:
        print(f"DEBUG: {msg}", file=sys.stderr)


# Key monitoring
# GUI - use GTK 3 for tray mode (AppIndicator compatibility), GTK 4 otherwise
import gi  # noqa: E402
from pynput import keyboard  # noqa: E402
from pynput.keyboard import Key  # noqa: E402

if TRAY_MODE:
    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib, Gtk

    # Tray imports
    try:
        gi.require_version("AppIndicator3", "0.1")
        HAS_APPINDICATOR = True
    except ValueError:
        HAS_APPINDICATOR = False
        print("Warning: AppIndicator3 not available, tray icon disabled", file=sys.stderr)
else:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import GLib, Gtk

    HAS_APPINDICATOR = False

# Our overlay (only import for non-tray mode with GTK4)
WhisprOverlay = None
if not TRAY_MODE:
    from overlay import WhisprOverlay


@dataclass
class WhisprConfig:
    """Configuration for Whispr"""

    # Activation
    trigger_keys: str = "alt,print_screen"  # Comma-separated: ctrl, alt, super, print_screen
    hold_duration: float = 0.5  # seconds to hold before activating

    # Audio
    sample_rate: int = 16000
    channels: int = 1

    # Transcription
    whisper_model: str = ""  # Path to whisper model, empty = use BlahST config
    whisper_server: str = ""  # IP:PORT for whisper.cpp server
    use_openai: bool = False  # Use OpenAI Whisper API instead
    openai_api_key: str = ""

    # Output
    auto_paste: bool = True
    copy_to_clipboard: bool = True

    # UI
    overlay_position: str = "bottom"  # center, top, bottom

    # Feedback
    play_sounds: bool = True
    show_notifications: bool = True

    @classmethod
    def load(cls, path: Path | None = None) -> "WhisprConfig":
        """Load config from file or return defaults"""
        if path is None:
            path = Path.home() / ".config" / "whispr" / "config.py"

        config = cls()

        if path.exists():
            config_vars = {}
            try:
                exec(path.read_text(), config_vars)
                for key, value in config_vars.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
                # Backwards compatibility: old trigger_key -> new trigger_keys
                if "trigger_key" in config_vars and "trigger_keys" not in config_vars:
                    config.trigger_keys = config_vars["trigger_key"]
            except Exception as e:
                print(f"Error loading config: {e}", file=sys.stderr)

        # Try to get whisper model from BlahST config
        if not config.whisper_model:
            blahst_cfg = Path.home() / ".local" / "bin" / "blahst.cfg"
            if blahst_cfg.exists():
                try:
                    content = blahst_cfg.read_text()
                    ai_path = str(Path.home() / "AI" / "Models")

                    # Extract AI path
                    for line in content.splitlines():
                        if line.startswith("AI="):
                            ai_path = line.split("=", 1)[1].strip('"').strip("'")
                            ai_path = ai_path.replace("$HOME", str(Path.home()))
                            break

                    # Extract model path
                    for line in content.splitlines():
                        if line.startswith("WMODEL="):
                            model_path = line.split("=", 1)[1].strip('"').strip("'")
                            model_path = model_path.replace("$HOME", str(Path.home()))
                            model_path = model_path.replace("$AI", ai_path)
                            model_path = model_path.replace('${WHISPER_DMODEL:-"', "").rstrip('"}')

                            if Path(model_path).exists():
                                config.whisper_model = model_path
                            break
                except Exception as e:
                    print(f"Error reading BlahST config: {e}", file=sys.stderr)

        return config

    def save(self, path: Path | None = None):
        """Save config to file"""
        if path is None:
            path = Path.home() / ".config" / "whispr" / "config.py"

        path.parent.mkdir(parents=True, exist_ok=True)

        content = f'''# Whispr Configuration
# Edit this file to customize Whispr behavior

# Trigger keys (comma-separated): "ctrl", "alt", "super", "print_screen"
trigger_keys = "{self.trigger_keys}"

# How long to hold the key before recording starts (seconds)
hold_duration = {self.hold_duration}

# Whisper model path (leave empty to auto-detect from BlahST)
whisper_model = "{self.whisper_model}"

# Whisper.cpp server address (e.g., "127.0.0.1:58080")
whisper_server = "{self.whisper_server}"

# Use OpenAI Whisper API instead of local
use_openai = {self.use_openai}

# Auto-paste transcribed text
auto_paste = {self.auto_paste}
'''
        path.write_text(content)


class WhisprState(Enum):
    """State machine for Whispr"""

    IDLE = auto()
    WAITING = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()


class AudioRecorder:
    """Records audio using sox (like BlahST) for maximum compatibility"""

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording = False
        self.current_level = 0.0
        self.level_callback: callable | None = None
        self.rec_process: subprocess.Popen | None = None
        self.temp_wav = "/dev/shm/whispr_rec.wav"  # RAM disk like BlahST

    def start(self, level_callback: callable | None = None):
        """Start recording using sox"""
        self.level_callback = level_callback
        self.is_recording = True

        # Use sox rec command like BlahST does
        # rec -q -t wav $ramf rate 16k silence 1 0.1 1% 1 2.0 3% channels 1
        self.rec_process = subprocess.Popen(
            ["rec", "-q", "-t", "wav", self.temp_wav, "rate", "16k", "channels", "1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Start level monitoring in background (approximate)
        if self.level_callback:

            def monitor_level():
                while self.is_recording:
                    # Simulate level changes for visual feedback
                    import random

                    level = random.uniform(0.2, 0.8)
                    GLib.idle_add(self.level_callback, level)
                    time.sleep(0.05)

            thread = threading.Thread(target=monitor_level, daemon=True)
            thread.start()

    def stop(self) -> str | None:
        """Stop recording and return path to WAV file"""
        self.is_recording = False

        if self.rec_process:
            # Send SIGINT to stop recording gracefully
            self.rec_process.send_signal(signal.SIGINT)
            try:
                self.rec_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.rec_process.kill()
            self.rec_process = None

        # Small delay to ensure file is written
        time.sleep(0.1)

        if os.path.exists(self.temp_wav):
            file_size = os.path.getsize(self.temp_wav)
            debug(f"Recorded WAV file: {file_size} bytes")
            if file_size > 1000:  # Minimum viable audio
                return self.temp_wav
        return None


class Transcriber:
    """Handles transcription via various backends"""

    def __init__(self, config: WhisprConfig):
        self.config = config

    def transcribe(self, audio_path: str) -> str:
        """Transcribe audio file to text"""
        if self.config.use_openai:
            return self._transcribe_openai(audio_path)
        elif self.config.whisper_server:
            return self._transcribe_server(audio_path)
        else:
            return self._transcribe_local(audio_path)

    def _transcribe_local(self, audio_path: str) -> str:
        """Use local whisper.cpp"""
        transcribe_cmd = None
        for cmd in ["transcribe", "whisper-cli", "whisper"]:
            try:
                result = subprocess.run([cmd, "--help"], capture_output=True)
                if result.returncode == 0 or b"usage" in result.stderr.lower():
                    transcribe_cmd = cmd
                    break
            except FileNotFoundError:
                continue

        if not transcribe_cmd:
            raise RuntimeError(
                "No whisper.cpp found. Install whisper.cpp and create 'transcribe' symlink:\n"
                "  ln -s /path/to/whisper.cpp/whisper-cli ~/.local/bin/transcribe"
            )

        cmd = [transcribe_cmd, "-t", "8", "-nt"]
        if self.config.whisper_model:
            cmd.extend(["-m", self.config.whisper_model])
        cmd.extend(["-f", audio_path])

        debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        debug(f"Return code: {result.returncode}")
        debug(f"stdout: {result.stdout[:200] if result.stdout else 'EMPTY'}")
        debug(f"stderr length: {len(result.stderr) if result.stderr else 0}")

        # Check for actual errors (not just initialization/timing messages)
        stderr_lower = result.stderr.lower()
        has_error = (
            "error:" in stderr_lower
            or "failed to read" in stderr_lower
            or "could not open" in stderr_lower
        )
        if result.returncode != 0 or has_error:
            # Find the actual error line
            for line in result.stderr.splitlines():
                if "error" in line.lower() or "failed" in line.lower():
                    debug(f"Error line: {line}")
            raise RuntimeError(f"Transcription failed: {result.stderr}")

        # Whisperfile outputs to stderr, so check both
        output = result.stdout
        if not output.strip():
            # Extract transcription from stderr (filter out whisper_ logs)
            lines = result.stderr.splitlines()
            text_lines = [
                line for line in lines if not line.startswith(("whisper_", "system_info", "main:"))
            ]
            # Also filter timestamp lines like [00:00:00.000 --> 00:00:02.000]
            text_lines = [line for line in text_lines if not line.strip().startswith("[")]
            output = "\n".join(text_lines)

        debug(f"Final output: {output[:100] if output else 'EMPTY'}")

        return self._clean_text(output)

    def _transcribe_server(self, audio_path: str) -> str:
        """Use whisper.cpp server"""
        cmd = [
            "curl",
            "-s",
            f"http://{self.config.whisper_server}/inference",
            "-H",
            "Content-Type: multipart/form-data",
            "-F",
            f"file=@{audio_path}",
            "-F",
            "temperature=0.0",
            "-F",
            "response_format=text",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"Server transcription failed: {result.stderr}")

        return self._clean_text(result.stdout)

    def _transcribe_openai(self, audio_path: str) -> str:
        """Use OpenAI Whisper API"""
        api_key = self.config.openai_api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OpenAI API key not configured. Set OPENAI_API_KEY env var.")

        cmd = [
            "curl",
            "-s",
            "https://api.openai.com/v1/audio/transcriptions",
            "-H",
            f"Authorization: Bearer {api_key}",
            "-F",
            f"file=@{audio_path}",
            "-F",
            "model=whisper-1",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"OpenAI transcription failed: {result.stderr}")

        import json

        try:
            data = json.loads(result.stdout)
            return self._clean_text(data.get("text", ""))
        except json.JSONDecodeError:
            return self._clean_text(result.stdout)

    def _clean_text(self, text: str) -> str:
        """Clean up transcribed text"""
        import re

        text = re.sub(r"\([^)]*\)", "", text)  # (wind blowing)
        text = re.sub(r"\[[^\]]*\]", "", text)  # [MUSIC]
        text = text.strip()

        if text:
            text = text[0].upper() + text[1:]

        return text


class Whispr:
    """Main Whispr application"""

    MAX_HISTORY = 10  # Maximum transcriptions to keep in history

    def __init__(self, config: WhisprConfig | None = None, tray_mode: bool = False):
        self.config = config or WhisprConfig.load()
        self.state = WhisprState.IDLE
        self.recorder = AudioRecorder(self.config.sample_rate, self.config.channels)
        self.transcriber = Transcriber(self.config)
        self.tray_mode = tray_mode

        # Key tracking
        self.key_press_time: float | None = None
        self.trigger_pressed = False
        self.trigger_keys = self._get_trigger_keys()

        # GTK
        self.app: Gtk.Application | None = None
        self.overlay = None  # WhisprOverlay (GTK4 mode only)

        # Tray (GTK3 mode only)
        self.tray = None
        self.settings_dialog = None

        # Transcription history
        self._transcription_history: list[str] = []

        # Threading
        self._lock = threading.Lock()
        self._activation_source = None

    # --- Transcription History ---

    def get_recent_transcriptions(self) -> list[str]:
        """Get recent transcription history"""
        return self._transcription_history.copy()

    def add_transcription(self, text: str):
        """Add a transcription to history"""
        if text:
            self._transcription_history.insert(0, text)
            # Trim to max size
            self._transcription_history = self._transcription_history[: self.MAX_HISTORY]
            # Notify tray
            if self.tray:
                self.tray.on_transcription_complete(text)

    def clear_transcription_history(self):
        """Clear transcription history"""
        self._transcription_history.clear()

    # --- Settings ---

    def show_settings(self):
        """Show settings dialog"""
        if self.settings_dialog:
            self.settings_dialog.present()
            return

        from settings import WhisprSettingsDialog

        self.settings_dialog = WhisprSettingsDialog(self)
        self.settings_dialog.connect("destroy", self._on_settings_closed)
        self.settings_dialog.show_all()

    def _on_settings_closed(self, widget):
        """Handle settings dialog close"""
        self.settings_dialog = None

    def reload_config(self):
        """Reload configuration and apply changes"""
        self.trigger_keys = self._get_trigger_keys()

    def set_autostart(self, enabled: bool):
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

    # --- Tray State ---

    def _update_tray_state(self):
        """Update tray icon based on current state"""
        if self.tray:
            state_map = {
                WhisprState.IDLE: "idle",
                WhisprState.WAITING: "idle",
                WhisprState.RECORDING: "recording",
                WhisprState.TRANSCRIBING: "transcribing",
            }
            self.tray.set_state(state_map.get(self.state, "idle"))

    def toggle_recording(self):
        """Toggle recording on/off (for tray menu)"""
        with self._lock:
            if self.state == WhisprState.IDLE:
                # Start recording
                self._start_recording()
            elif self.state == WhisprState.RECORDING:
                # Stop recording
                self._stop_recording()

    def _get_trigger_keys(self) -> list:
        """Get normalized list of trigger key names"""
        return [k.strip().lower() for k in self.config.trigger_keys.split(",")]

    def _is_trigger_key(self, key) -> bool:
        """Check if pressed key is one of our triggers"""
        for trigger in self.trigger_keys:
            if trigger in ("ctrl", "control"):
                if key in (Key.ctrl, Key.ctrl_l, Key.ctrl_r):
                    return True
            elif trigger == "alt":
                if key in (Key.alt, Key.alt_l, Key.alt_r):
                    return True
            elif trigger in ("super", "meta", "cmd"):
                if key in (Key.cmd, Key.cmd_l, Key.cmd_r):
                    return True
            elif trigger == "print_screen" and key == Key.print_screen:
                return True

        return False

    def _on_key_press(self, key):
        """Handle key press"""
        # Debug: show what key was pressed
        debug(
            f"Key pressed: {key}, trigger_keys={self.trigger_keys}, is_trigger={self._is_trigger_key(key)}"
        )

        if not self._is_trigger_key(key):
            return

        with self._lock:
            if self.trigger_pressed:
                return  # Already pressed

            self.trigger_pressed = True

            if self.state == WhisprState.IDLE:
                self.key_press_time = time.time()
                self.state = WhisprState.WAITING

                # Cancel any pending activation
                if self._activation_source:
                    GLib.source_remove(self._activation_source)

                # Schedule activation check
                self._activation_source = GLib.timeout_add(
                    int(self.config.hold_duration * 1000), self._check_activation
                )

    def _on_key_release(self, key):
        """Handle key release"""
        if not self._is_trigger_key(key):
            return

        with self._lock:
            self.trigger_pressed = False

            if self.state == WhisprState.WAITING:
                # Released before activation
                self.state = WhisprState.IDLE
                self.key_press_time = None
                if self._activation_source:
                    GLib.source_remove(self._activation_source)
                    self._activation_source = None

            elif self.state == WhisprState.RECORDING:
                self._stop_recording()

    def _check_activation(self) -> bool:
        """Check if we should activate recording"""
        self._activation_source = None

        with self._lock:
            if self.state != WhisprState.WAITING:
                return False

            if not self.trigger_pressed:
                self.state = WhisprState.IDLE
                return False

            if self.key_press_time is None:
                return False

            elapsed = time.time() - self.key_press_time
            if elapsed >= self.config.hold_duration:
                self._start_recording()

        return False

    def _start_recording(self):
        """Start recording audio"""
        self.state = WhisprState.RECORDING
        self._update_tray_state()

        # Start recorder with level callback
        def on_level(level):
            if self.overlay:
                self.overlay.update_audio_level(level)

        self.recorder.start(level_callback=on_level)

        # Show overlay (GTK4 mode only)
        if self.overlay:
            GLib.idle_add(self.overlay.show_recording)

        # Play start sound
        self._play_sound("start")

        debug("Recording...")

    def _stop_recording(self):
        """Stop recording and start transcription"""
        self.state = WhisprState.TRANSCRIBING
        self._update_tray_state()

        # Update overlay (GTK4 mode only)
        if self.overlay:
            GLib.idle_add(self.overlay.show_transcribing)

        debug("Transcribing...")

        # Stop recording - now returns path to WAV file
        wav_path = self.recorder.stop()

        if wav_path:
            thread = threading.Thread(target=self._transcribe_file, args=(wav_path,))
            thread.daemon = True
            thread.start()
        else:
            GLib.idle_add(self._finish, None, "Recording too short")

    def _transcribe_file(self, wav_path: str):
        """Transcribe WAV file (runs in background thread)"""
        try:
            debug(f"Transcribing {wav_path}")
            text = self.transcriber.transcribe(wav_path)
            debug(f"Transcription result: {text[:50] if text else 'EMPTY'}...")

            GLib.idle_add(self._finish, text)

        except Exception as e:
            print(f"Transcription error: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            GLib.idle_add(self._finish, None, str(e))

    def _finish(self, text: str | None, error: str | None = None):
        """Finish transcription and output result"""
        if self.overlay:
            self.overlay.hide_overlay()

        self.state = WhisprState.IDLE
        self.key_press_time = None
        self._update_tray_state()

        if error:
            self._notify("Whispr", f"Error: {error}")
            self._play_sound("error")
            return

        if not text:
            self._notify("Whispr", "No speech detected")
            return

        debug(f"Result: {text}")

        # Add to transcription history
        self.add_transcription(text)

        # Auto-type text directly at cursor (without touching clipboard)
        if self.config.auto_paste:
            debug("Will type text in 250ms")
            # Delay to ensure modifier keys are fully released
            GLib.timeout_add(250, lambda: self._paste(text) or False)
        elif self.config.copy_to_clipboard:
            # Only copy to clipboard if not auto-pasting
            debug(f"Copying to clipboard: {text[:50]}...")
            self._copy_to_clipboard(text)

        # Success sound
        self._play_sound("success")

        # Notification with preview
        preview = text[:80] + "..." if len(text) > 80 else text
        self._notify("Whispr", preview)

    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard"""
        for cmd in [["xsel", "-ib"], ["xclip", "-selection", "clipboard"]]:
            try:
                subprocess.run(cmd, input=text.encode(), check=True)
                return
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        print("Warning: No clipboard tool found", file=sys.stderr)

    def _get_active_window_class(self) -> str:
        """Get the WM_CLASS of the active window"""
        try:
            # Get active window ID
            result = subprocess.run(
                ["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=1
            )
            if result.returncode != 0:
                return ""
            window_id = result.stdout.strip()

            # Get WM_CLASS using xprop
            result = subprocess.run(
                ["xprop", "-id", window_id, "WM_CLASS"], capture_output=True, text=True, timeout=1
            )
            if result.returncode == 0:
                # Parse: WM_CLASS(STRING) = "instance", "class"
                output = result.stdout.lower()
                debug(f"Window WM_CLASS: {output.strip()}")
                return output
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        return ""

    def _is_terminal_window(self) -> bool:
        """Check if the active window is a terminal emulator"""
        window_class = self._get_active_window_class()
        if not window_class:
            return False

        # Common terminal emulators
        terminals = [
            "gnome-terminal",
            "konsole",
            "xterm",
            "urxvt",
            "rxvt",
            "terminator",
            "tilix",
            "alacritty",
            "kitty",
            "st-256color",
            "xfce4-terminal",
            "mate-terminal",
            "lxterminal",
            "terminology",
            "guake",
            "yakuake",
            "tilda",
            "termite",
            "hyper",
            "wezterm",
            "foot",
            "contour",
            "cool-retro-term",
            "qterminal",
            "sakura",
            "roxterm",
            "evilvte",
            "lilyterm",
        ]
        return any(term in window_class for term in terminals)

    def _paste(self, text: str = None):
        """Paste text at cursor using multiple strategies for reliability"""
        debug(f"_paste called with text length: {len(text) if text else 0}")

        if not text:
            return

        try:
            # First, ensure all modifier keys are released
            debug("Releasing modifier keys...")
            subprocess.run(
                ["xdotool", "keyup", "ctrl", "alt", "shift", "super", "Print"],
                check=False,
                timeout=1,
            )
            time.sleep(0.15)

            # Get active window info for debugging
            try:
                result = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowname"],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                debug(f"Active window: {result.stdout.strip()}")
            except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass

            # Detect if we're in a terminal
            is_terminal = self._is_terminal_window()
            debug(f"Terminal detected: {is_terminal}")

            if is_terminal:
                # For terminals, use clipboard + Ctrl+Shift+V
                # Save current clipboard
                saved_clipboard = None
                try:
                    result = subprocess.run(["xsel", "-ob"], capture_output=True, timeout=1)
                    if result.returncode == 0:
                        saved_clipboard = result.stdout
                        debug(f"Saved clipboard: {len(saved_clipboard)} bytes")
                except (
                    FileNotFoundError,
                    subprocess.CalledProcessError,
                    subprocess.TimeoutExpired,
                ):
                    pass

                # Set clipboard and paste
                debug("Setting clipboard for terminal paste...")
                subprocess.run(["xsel", "-ib"], input=text.encode(), check=True, timeout=1)
                time.sleep(0.05)

                debug("Pasting with ctrl+shift+v...")
                subprocess.run(["xdotool", "key", "ctrl+shift+v"], check=True, timeout=2)
                debug("Terminal paste complete")

                # Restore clipboard
                if saved_clipboard is not None:

                    def restore_clipboard():
                        time.sleep(0.5)
                        try:
                            subprocess.run(
                                ["xsel", "-ib"], input=saved_clipboard, check=True, timeout=1
                            )
                            debug("Clipboard restored")
                        except (
                            FileNotFoundError,
                            subprocess.CalledProcessError,
                            subprocess.TimeoutExpired,
                        ):
                            pass

                    threading.Thread(target=restore_clipboard, daemon=True).start()
            else:
                # For GUI apps, use clipboard paste (faster for long text)
                # Save current clipboard contents
                saved_clipboard = None
                try:
                    result = subprocess.run(["xsel", "-ob"], capture_output=True, timeout=1)
                    if result.returncode == 0:
                        saved_clipboard = result.stdout
                        debug(f"Saved clipboard: {len(saved_clipboard)} bytes")
                except (
                    FileNotFoundError,
                    subprocess.CalledProcessError,
                    subprocess.TimeoutExpired,
                ):
                    pass

                # Put our text in clipboard
                debug(f"Setting clipboard to: {text[:30]}...")
                subprocess.run(["xsel", "-ib"], input=text.encode(), check=True, timeout=1)
                time.sleep(0.05)

                # Paste with Ctrl+V
                debug("Pasting with ctrl+v...")
                subprocess.run(
                    ["xdotool", "key", "--clearmodifiers", "ctrl+v"], check=True, timeout=2
                )
                debug("Paste complete")

                # Restore original clipboard after a delay
                if saved_clipboard is not None:

                    def restore_clipboard():
                        time.sleep(0.5)
                        try:
                            subprocess.run(
                                ["xsel", "-ib"], input=saved_clipboard, check=True, timeout=1
                            )
                            debug("Clipboard restored")
                        except (
                            FileNotFoundError,
                            subprocess.CalledProcessError,
                            subprocess.TimeoutExpired,
                        ):
                            pass

                    threading.Thread(target=restore_clipboard, daemon=True).start()

        except FileNotFoundError:
            print("xdotool or xsel not found, cannot auto-paste", file=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(f"Paste failed: {e}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            print("Paste timed out", file=sys.stderr)

    def _notify(self, title: str, message: str):
        """Show desktop notification"""
        if not self.config.show_notifications:
            return
        import contextlib

        with contextlib.suppress(FileNotFoundError):
            subprocess.run(
                ["notify-send", "-t", "3000", "-a", "Whispr", "-i", "whispr", title, message],
                check=True,
            )

    def _play_sound(self, sound_type: str):
        """Play feedback sound"""
        if not self.config.play_sounds:
            return

        sounds = {
            "start": "/usr/share/sounds/freedesktop/stereo/device-added.oga",
            "success": "/usr/share/sounds/freedesktop/stereo/complete.oga",
            "error": "/usr/share/sounds/freedesktop/stereo/dialog-error.oga",
        }

        sound_file = sounds.get(sound_type)
        if sound_file and Path(sound_file).exists():
            import contextlib

            with contextlib.suppress(FileNotFoundError):
                subprocess.Popen(
                    ["paplay", sound_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )

    def _on_activate(self, app):
        """GTK application activation (GTK4 mode only)"""
        if WhisprOverlay:
            self.overlay = WhisprOverlay()
            self.overlay.set_application(app)

        self._start_listener()

    def _on_activate_gtk3(self, app):
        """GTK application activation (GTK3/tray mode)"""
        # Create tray icon
        if HAS_APPINDICATOR:
            from tray import WhisprTray

            self.tray = WhisprTray(self)

        self._start_listener()

    def _start_listener(self):
        """Start key listener and show startup message"""
        # Start key listener in background thread
        listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        listener.start()

        key_names = [k.upper().replace("_", " ") for k in self.trigger_keys]
        keys_str = " or ".join(key_names)
        hold_time = self.config.hold_duration

        print("Whispr running!", file=sys.stderr)
        print(f"  Hold {keys_str} for {hold_time}s to start recording", file=sys.stderr)
        print("  Release to transcribe and paste", file=sys.stderr)

        self._notify("Whispr Ready", f"Hold {keys_str} for {hold_time}s to record")

    def run(self):
        """Run the application"""
        if self.tray_mode:
            self._run_tray_mode()
        else:
            self._run_overlay_mode()

    def _run_overlay_mode(self):
        """Run with GTK4 overlay (no tray)"""
        self.app = Gtk.Application(application_id="com.whispr.app")
        self.app.connect("activate", self._on_activate)
        self.app.hold()  # Keep running without visible windows

        # Handle Ctrl+C gracefully
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, self._on_sigint)

        self.app.run()

    def _run_tray_mode(self):
        """Run with GTK3 tray icon"""
        self.app = Gtk.Application(application_id="com.whispr.app")
        self.app.connect("activate", self._on_activate_gtk3)
        self.app.hold()

        # Handle Ctrl+C gracefully
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, self._on_sigint)

        self.app.run()

    def _on_sigint(self):
        """Handle SIGINT (Ctrl+C)"""
        print("\nExiting...", file=sys.stderr)
        self.app.quit()
        return GLib.SOURCE_REMOVE


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Whispr - WisprFlow-style speech-to-text for Linux",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  whispr                      # Use defaults (Alt key, 0.5s hold)
  whispr --tray               # Run with system tray icon
  whispr --keys ctrl --hold 1 # Use Ctrl key with 1 second hold
  whispr --server 127.0.0.1:58080  # Use whisper.cpp server
  whispr --openai             # Use OpenAI Whisper API
""",
    )
    parser.add_argument("--tray", action="store_true", help="Run with system tray icon (GTK3 mode)")
    parser.add_argument(
        "--keys", default=None, help="Trigger keys, comma-separated (default: alt,print_screen)"
    )
    parser.add_argument(
        "--hold", type=float, default=None, help="Hold duration in seconds (default: 0.5)"
    )
    parser.add_argument("--server", help="Whisper.cpp server address (IP:PORT)")
    parser.add_argument("--openai", action="store_true", help="Use OpenAI Whisper API")
    parser.add_argument("--no-paste", action="store_true", help="Disable auto-paste")
    parser.add_argument(
        "--save-config", action="store_true", help="Save current options as default config"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    # Set global debug flag
    global DEBUG
    DEBUG = args.debug

    config = WhisprConfig.load()
    if args.keys:
        config.trigger_keys = args.keys
    if args.hold is not None:
        config.hold_duration = args.hold

    if args.server:
        config.whisper_server = args.server
    if args.openai:
        config.use_openai = True
    if args.no_paste:
        config.auto_paste = False

    if args.save_config:
        config.save()
        print("Config saved to ~/.config/whispr/config.py", file=sys.stderr)

    whispr = Whispr(config, tray_mode=args.tray)
    whispr.run()


if __name__ == "__main__":
    main()
