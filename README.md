# Whispr

**WisprFlow-style speech-to-text for Linux**

Hold a key to record, release to transcribe and paste. Simple, fast, beautiful.

## Features

- **Hold-to-talk activation** - Hold Ctrl (configurable) for 0.5s to start recording
- **Beautiful animated overlay** - Real-time audio visualization while recording
- **Multiple backends** - Local whisper.cpp, whisper.cpp server, or OpenAI Whisper API
- **Auto-paste** - Transcribed text is automatically pasted to active window
- **BlahST compatible** - Automatically uses your existing BlahST/whisper.cpp config

## Quick Start

```bash
# Install dependencies (requires sudo)
cd ~/Projects/whispr
./setup-deps.sh

# Install Whispr
./install.sh

# Run!
whispr
```

## Usage

1. **Hold CTRL** for 0.5 seconds - Recording starts with visual indicator
2. **Keep holding** - See your audio levels in real-time
3. **Release CTRL** - Transcription happens and text is pasted

### Command Line Options

```bash
whispr                      # Default (Ctrl key, 0.5s hold)
whispr --key alt --hold 1   # Alt key with 1 second hold
whispr --server 127.0.0.1:58080  # Use whisper.cpp server
whispr --openai             # Use OpenAI Whisper API
whispr --no-paste           # Don't auto-paste
whispr --save-config        # Save current options as defaults
```

## Running as a Service

```bash
# Start on demand
systemctl --user start whispr

# Enable on login
systemctl --user enable whispr

# Check status
systemctl --user status whispr
```

## Configuration

Config file: `~/.config/whispr/config.py`

```python
# Trigger key: "ctrl", "alt", or "super"
trigger_key = "ctrl"

# How long to hold before recording starts
hold_duration = 0.5

# Whisper model (auto-detected from BlahST if empty)
whisper_model = ""

# Use whisper.cpp server instead of local
whisper_server = ""  # e.g., "127.0.0.1:58080"

# Use OpenAI Whisper API
use_openai = False

# Auto-paste transcribed text
auto_paste = True
```

## Requirements

- Python 3.10+
- GTK 4
- whisper.cpp (or server/OpenAI API)
- PortAudio
- xdotool, xsel

## Integration with BlahST

Whispr automatically reads your BlahST configuration from `~/.local/bin/blahst.cfg` to find your whisper model path. If you've set up BlahST, Whispr will just work!

## How It Works

```
[IDLE] ─── Ctrl pressed ──► [WAITING]
                                │
                    hold > 0.5s │ release before 0.5s
                                │        │
                                ▼        │
                          [RECORDING] ◄──┘
                                │
                     Ctrl released
                                │
                                ▼
                         [TRANSCRIBING]
                                │
                                ▼
              [Paste to active window] → [IDLE]
```

## License

MIT
