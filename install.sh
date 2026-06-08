#!/usr/bin/env bash
#
# Whispr Installer
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/whispr"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/whispr"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "========================================"
echo "  Whispr Installer"
echo "========================================"
echo

# --- Python version check ---
echo "Checking Python version..."
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
if [[ $PYTHON_MAJOR -lt 3 ]] || [[ $PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -lt 10 ]]; then
    echo "Error: Python 3.10+ required (found $PYTHON_VERSION)"
    exit 1
fi
echo "  Python $PYTHON_VERSION OK"

# --- System dependency check ---
echo
echo "Checking system dependencies..."
MISSING_DEPS=""

pkg-config --exists gtk4          2>/dev/null || MISSING_DEPS="$MISSING_DEPS libgtk-4-dev"
pkg-config --exists pygobject-3.0 2>/dev/null || MISSING_DEPS="$MISSING_DEPS python3-gi python3-gi-cairo gir1.2-gtk-4.0"
pkg-config --exists portaudio-2.0 2>/dev/null || MISSING_DEPS="$MISSING_DEPS libportaudio2 portaudio19-dev"
command -v sox      &>/dev/null    || MISSING_DEPS="$MISSING_DEPS sox libsox-fmt-all"
command -v xdotool  &>/dev/null    || MISSING_DEPS="$MISSING_DEPS xdotool"
command -v notify-send &>/dev/null || MISSING_DEPS="$MISSING_DEPS libnotify-bin"
command -v xsel     &>/dev/null && command -v xclip &>/dev/null || \
    { command -v xsel &>/dev/null || MISSING_DEPS="$MISSING_DEPS xsel"; }
python3 -c "import ensurepip" &>/dev/null || MISSING_DEPS="$MISSING_DEPS python3-venv python3-pip"
# GTK3 typelib for tray_applet.py
python3 -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk" &>/dev/null \
    || MISSING_DEPS="$MISSING_DEPS gir1.2-gtk-3.0"

if [[ -n "$MISSING_DEPS" ]]; then
    echo "  Missing:$MISSING_DEPS"
    echo
    read -p "  Install now with apt? [Y/n] " -n 1 -r; echo
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        sudo apt install -y $MISSING_DEPS
    else
        echo "Please install missing packages and re-run."
        exit 1
    fi
fi
echo "  System dependencies OK"

# --- whisper.cpp ---
echo
echo "Checking for whisper.cpp..."
WHISPER_BIN=""
WHISPER_MODEL=""

# Prefer server binary
if [[ -x "$HOME/projects/whisper.cpp/build/bin/whisper-server" ]]; then
    WHISPER_BIN="$HOME/projects/whisper.cpp/build/bin/whisper-server"
fi
# Find first available model
WHISPER_MODEL=$(find "$HOME/projects/whisper.cpp/models" -name "*.bin" 2>/dev/null | head -1)

if [[ -n "$WHISPER_BIN" && -n "$WHISPER_MODEL" ]]; then
    echo "  Server:  $WHISPER_BIN"
    echo "  Model:   $WHISPER_MODEL"
    HAVE_SERVER=true
else
    HAVE_SERVER=false
    echo "  whisper.cpp server not found at ~/projects/whisper.cpp"
    echo "  To build it:"
    echo "    git clone https://github.com/ggerganov/whisper.cpp ~/projects/whisper.cpp"
    echo "    cd ~/projects/whisper.cpp && cmake -B build && cmake --build build -j\$(nproc)"
    echo "    bash models/download-ggml-model.sh tiny.en"
    echo "  Then re-run this installer, or use --openai flag instead."
    echo
fi

# --- Create directories ---
echo
echo "Creating directories..."
mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$CONFIG_DIR" "$SYSTEMD_DIR"

# --- Python venv ---
echo
echo "Setting up Python virtual environment..."
[[ -d "$INSTALL_DIR/venv" ]] && rm -rf "$INSTALL_DIR/venv"
python3 -m venv --system-site-packages "$INSTALL_DIR/venv"

echo "Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip wheel -q
"$INSTALL_DIR/venv/bin/pip" install sounddevice numpy pynput Pillow -q

# --- Copy app files ---
echo
echo "Installing Whispr..."
cp "$SCRIPT_DIR/whispr.py"      "$INSTALL_DIR/"
cp "$SCRIPT_DIR/overlay.py"     "$INSTALL_DIR/"
cp "$SCRIPT_DIR/tray_applet.py" "$INSTALL_DIR/"

# --- Launcher ---
cat > "$BIN_DIR/whispr" << 'LAUNCHER'
#!/usr/bin/env bash
WHISPR_DIR="$HOME/.local/share/whispr"
exec "$WHISPR_DIR/venv/bin/python" "$WHISPR_DIR/whispr.py" "$@"
LAUNCHER
chmod +x "$BIN_DIR/whispr"

# --- Default config (only if none exists) ---
if [[ ! -f "$CONFIG_DIR/config.py" ]]; then
    SERVER_LINE=""
    [[ "$HAVE_SERVER" == "true" ]] && SERVER_LINE="whisper_server = \"127.0.0.1:58080\""
    cat > "$CONFIG_DIR/config.py" << CONF
# Whispr configuration
trigger_keys = "alt,print_screen"
hold_duration = 0.5
whisper_model = ""
$SERVER_LINE
use_openai = False
auto_paste = True
CONF
fi

# --- Systemd services ---
echo
echo "Configuring systemd services..."

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

if [[ "$HAVE_SERVER" == "true" ]]; then
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
fi

# Disable .desktop autostart — systemd owns startup
AUTOSTART="$HOME/.config/autostart/whispr.desktop"
if [[ -f "$AUTOSTART" ]]; then
    sed -i 's/X-GNOME-Autostart-enabled=true/X-GNOME-Autostart-enabled=false/' "$AUTOSTART"
fi

systemctl --user daemon-reload

if [[ "$HAVE_SERVER" == "true" ]]; then
    systemctl --user enable whisper-server
    systemctl --user start whisper-server
    sleep 2
fi
systemctl --user enable whispr
systemctl --user start whispr

echo
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo
if [[ "$HAVE_SERVER" == "true" ]]; then
echo "  whisper-server  running at 127.0.0.1:58080"
fi
echo "  whispr          running — hold Alt or Print Screen to record"
echo
echo "Both services start automatically on login."
echo
echo "Config: ~/.config/whispr/config.py"
echo
echo "Status:"
echo "  systemctl --user status whispr"
[[ "$HAVE_SERVER" == "true" ]] && echo "  systemctl --user status whisper-server"
echo
