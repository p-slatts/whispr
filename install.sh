#!/usr/bin/env bash
#
# Whispr Installer
# WisprFlow-style speech-to-text for Linux
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/whispr"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/whispr"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "========================================"
echo "  Whispr Installer"
echo "  WisprFlow-style speech-to-text"
echo "========================================"
echo

# Check for Python 3.10+
echo "Checking Python version..."
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [[ $PYTHON_MAJOR -lt 3 ]] || [[ $PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -lt 10 ]]; then
    echo "Error: Python 3.10+ required (found $PYTHON_VERSION)"
    exit 1
fi
echo "  Python $PYTHON_VERSION OK"

# Check for required system packages
echo
echo "Checking system dependencies..."

MISSING_DEPS=""

# Check for GTK4
if ! pkg-config --exists gtk4 2>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS libgtk-4-dev"
fi

# Check for PyGObject dependencies
if ! pkg-config --exists pygobject-3.0 2>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS python3-gi python3-gi-cairo gir1.2-gtk-4.0"
fi

# Check for PortAudio (for sounddevice)
if ! pkg-config --exists portaudio-2.0 2>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS libportaudio2 portaudio19-dev"
fi

# Check for xdotool
if ! command -v xdotool &>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS xdotool"
fi

# Check for xsel
if ! command -v xsel &>/dev/null && ! command -v xclip &>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS xsel"
fi

# Check for python3-venv
if ! python3 -c "import ensurepip" &>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS python3.10-venv python3-pip"
fi

# Check for XApp GI bindings (needed by tray_applet.py for Cinnamon SNI support)
if ! python3 -c "import gi; gi.require_version('XApp','1.0'); from gi.repository import XApp" &>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS gir1.2-xapp-1.0"
fi

if [[ -n "$MISSING_DEPS" ]]; then
    echo
    echo "Missing system dependencies. Install with:"
    echo "  sudo apt install$MISSING_DEPS"
    echo
    read -p "Install now? [Y/n] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        sudo apt install -y $MISSING_DEPS
    else
        echo "Please install dependencies and re-run this script."
        exit 1
    fi
fi

echo "  System dependencies OK"

# Check for whisper.cpp
echo
echo "Checking for whisper.cpp..."
if command -v transcribe &>/dev/null; then
    echo "  Found 'transcribe' command"
elif command -v whisper-cli &>/dev/null; then
    echo "  Found 'whisper-cli' command"
else
    echo "  Warning: whisper.cpp not found"
    echo "  You'll need to either:"
    echo "    1. Install whisper.cpp and symlink: ln -s /path/to/whisper-cli ~/.local/bin/transcribe"
    echo "    2. Use --server option to connect to a whisper.cpp server"
    echo "    3. Use --openai option to use OpenAI Whisper API"
    echo
fi

# Create directories
echo
echo "Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$SYSTEMD_DIR"

# Create virtual environment with system site packages (for PyGObject)
echo
echo "Setting up Python virtual environment..."
if [[ -d "$INSTALL_DIR/venv" ]]; then
    rm -rf "$INSTALL_DIR/venv"
fi
# Use --system-site-packages to access system PyGObject (python3-gi)
python3 -m venv --system-site-packages "$INSTALL_DIR/venv"

# Install Python dependencies (PyGObject comes from system)
echo
echo "Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip wheel
"$INSTALL_DIR/venv/bin/pip" install sounddevice numpy pynput

# Copy application files
echo
echo "Installing Whispr..."
cp "$SCRIPT_DIR/whispr.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/overlay.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/tray_applet.py" "$INSTALL_DIR/"

# Create launcher script
cat > "$BIN_DIR/whispr" << 'LAUNCHER'
#!/usr/bin/env bash
WHISPR_DIR="$HOME/.local/share/whispr"
exec "$WHISPR_DIR/venv/bin/python" "$WHISPR_DIR/whispr.py" "$@"
LAUNCHER
chmod +x "$BIN_DIR/whispr"

# Create whispr systemd service
cat > "$SYSTEMD_DIR/whispr.service" << 'SERVICE'
[Unit]
Description=Whispr - Speech to Text
After=graphical-session.target whisper-server.service
Wants=whisper-server.service

[Service]
Type=simple
ExecStart=%h/.local/bin/whispr
Restart=on-failure
RestartSec=5
Environment=DISPLAY=:0
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

[Install]
WantedBy=graphical-session.target
SERVICE

# Create whisper-server systemd service (adjust paths if needed)
WHISPER_BIN="$HOME/projects/whisper.cpp/build/bin/whisper-server"
WHISPER_MODEL="$HOME/projects/whisper.cpp/models/ggml-tiny.en-q5_0.bin"
if [[ -x "$WHISPER_BIN" && -f "$WHISPER_MODEL" ]]; then
    cat > "$SYSTEMD_DIR/whisper-server.service" << SERVICE2
[Unit]
Description=Whisper.cpp Inference Server
After=network.target

[Service]
Type=simple
ExecStart=$WHISPER_BIN -m $WHISPER_MODEL -t 4 --host 127.0.0.1 --port 58080
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
SERVICE2
    echo "  Created whisper-server.service"
fi

# Disable .desktop autostart — systemd manages startup now
AUTOSTART="$HOME/.config/autostart/whispr.desktop"
if [[ -f "$AUTOSTART" ]]; then
    sed -i 's/X-GNOME-Autostart-enabled=true/X-GNOME-Autostart-enabled=false/' "$AUTOSTART"
fi

# Enable and start both services
echo
echo "Enabling services..."
systemctl --user daemon-reload
systemctl --user enable whisper-server whispr
systemctl --user start whisper-server
sleep 2
systemctl --user start whispr

echo
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo
echo "Both services enabled and started:"
echo "  whisper-server  — whisper.cpp at 127.0.0.1:58080"
echo "  whispr          — hold Alt/Print Screen to record"
echo
echo "They will restart automatically on login."
echo
echo "Manage with:"
echo "  systemctl --user status whispr"
echo "  systemctl --user status whisper-server"
echo
echo "Config: ~/.config/whispr/config.py"
echo
echo "Config file: ~/.config/whispr/config.py"
echo
