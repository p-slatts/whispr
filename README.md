# Whispr

Hold a key to record, release to transcribe and paste. WisprFlow-style speech-to-text for Linux.

## Features

- **Hold-to-talk** — hold Alt or Print Screen for 0.5 s, release to transcribe
- **Auto-paste** — text lands at the cursor in any app, terminal included
- **Animated overlay** — standby pulse → waveform → transcribing spinner
- **System tray** — W icon with Enable/Disable toggle and Quit
- **Multiple backends** — whisper.cpp server, local whisper.cpp, or OpenAI API
- **Starts on login** — managed by systemd user services

## Quick install (fresh Ubuntu machine)

### 1. Install system packages

```bash
cd ~/projects/whispr
./setup-deps.sh
```

### 2. Build whisper.cpp + download a model

```bash
git clone https://github.com/ggerganov/whisper.cpp ~/projects/whisper.cpp
cd ~/projects/whisper.cpp
cmake -B build && cmake --build build -j$(nproc)
bash models/download-ggml-model.sh tiny.en
```

### 3. Install Whispr

```bash
cd ~/projects/whispr
./install.sh
```

That's it. The installer builds the venv, writes both systemd services, enables them, and starts everything. On every subsequent login both services come up automatically.

## Usage

| Action | Result |
|---|---|
| Hold **Alt** or **Print Screen** for 0.5 s | Recording starts (waveform shown) |
| Release | Transcribes and pastes at cursor |
| Release before 0.5 s | Cancels |
| Click tray **W** icon | Enable / Disable toggle, Quit |

## Configuration

`~/.config/whispr/config.py` — edit and restart whispr to apply.

```python
trigger_keys   = "alt,print_screen"  # comma-separated: alt, ctrl, super, print_screen
hold_duration  = 0.5                 # seconds to hold before recording
whisper_server = "127.0.0.1:58080"  # whisper.cpp server (recommended)
whisper_model  = ""                  # local model path (auto-detected if empty)
use_openai     = False               # use OpenAI Whisper API instead
auto_paste     = True                # paste at cursor after transcription
```

Save current CLI flags as defaults:
```bash
whispr --server 127.0.0.1:58080 --save-config
```

## Services

```bash
systemctl --user status whispr
systemctl --user status whisper-server

systemctl --user restart whispr
systemctl --user stop whisper-server
```

## Transcription backends

| Backend | Flag | Notes |
|---|---|---|
| whisper.cpp server | `--server 127.0.0.1:58080` | Fastest — server loads model once |
| whisper.cpp local | *(auto-detected)* | Slower on first use |
| OpenAI API | `--openai` | Requires `OPENAI_API_KEY` |

## Requirements

- Ubuntu 22.04+ / Linux Mint 21+ (X11, Cinnamon/GNOME/XFCE)
- Python 3.10+
- GTK 4 + GTK 3 (`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-gtk-3.0`)
- sox (`rec` command for audio capture)
- xdotool, xsel
- whisper.cpp **or** OpenAI API key

## License

MIT
