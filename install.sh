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
AUTOSTART_DIR="$HOME/.config/autostart"
ICONS_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
APPS_DIR="$HOME/.local/share/applications"
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

# Check for GTK4 (for overlay mode)
if ! pkg-config --exists gtk4 2>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS libgtk-4-dev"
fi

# Check for GTK3 (for tray mode)
if ! pkg-config --exists gtk+-3.0 2>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS libgtk-3-dev"
fi

# Check for PyGObject dependencies
if ! pkg-config --exists pygobject-3.0 2>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-gtk-3.0"
fi

# Check for AppIndicator3 (for tray icon)
if ! python3 -c "import gi; gi.require_version('AppIndicator3', '0.1')" 2>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS gir1.2-appindicator3-0.1"
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
mkdir -p "$INSTALL_DIR/icons"
mkdir -p "$BIN_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$AUTOSTART_DIR"
mkdir -p "$ICONS_DIR"
mkdir -p "$APPS_DIR"
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
cp "$SCRIPT_DIR/tray.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/settings.py" "$INSTALL_DIR/"

# Copy icons
echo "Installing icons..."
cp "$SCRIPT_DIR/icons/"*.svg "$INSTALL_DIR/icons/"
cp "$SCRIPT_DIR/icons/"*.svg "$ICONS_DIR/"

# Update icon cache
gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor/" 2>/dev/null || true

# Install desktop file for applications menu
echo "Installing desktop files..."
cp "$SCRIPT_DIR/whispr.desktop" "$APPS_DIR/"

# Install autostart file (enabled by default)
cp "$SCRIPT_DIR/whispr-autostart.desktop" "$AUTOSTART_DIR/whispr.desktop"

# Update desktop database
update-desktop-database "$APPS_DIR" 2>/dev/null || true

# Create launcher script
cat > "$BIN_DIR/whispr" << 'LAUNCHER'
#!/usr/bin/env bash
WHISPR_DIR="$HOME/.local/share/whispr"
exec "$WHISPR_DIR/venv/bin/python" "$WHISPR_DIR/whispr.py" "$@"
LAUNCHER
chmod +x "$BIN_DIR/whispr"

# Create systemd service (optional, for non-tray mode)
cat > "$SYSTEMD_DIR/whispr.service" << 'SERVICE'
[Unit]
Description=Whispr - Speech to Text
Documentation=https://github.com/your-repo/whispr
After=graphical-session.target

[Service]
Type=simple
ExecStart=%h/.local/bin/whispr
Restart=on-failure
RestartSec=5

# Environment for GUI access
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
SERVICE

# Reload systemd
echo
echo "Configuring systemd service..."
systemctl --user daemon-reload

echo
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo
echo "Whispr has been installed and will start automatically on login."
echo
echo "To start now:"
echo "  whispr --tray             # Run with system tray icon"
echo "  whispr                    # Run without tray (overlay only)"
echo
echo "To disable autostart:"
echo "  rm ~/.config/autostart/whispr.desktop"
echo
echo "Usage:"
echo "  Hold ALT or PRINT SCREEN for 0.5 seconds to start recording"
echo "  Release to transcribe and paste"
echo
echo "The tray icon provides quick access to:"
echo "  - Start/Stop recording"
echo "  - Recent transcriptions"
echo "  - Settings"
echo "  - Autostart toggle"
echo
echo "Config file: ~/.config/whispr/config.py"
echo
