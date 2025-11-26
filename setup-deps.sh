#!/usr/bin/env bash
#
# Whispr Dependencies Setup (requires sudo)
#

set -e

echo "Installing Whispr dependencies..."
echo

# System packages
sudo apt update
sudo apt install -y \
    python3-pip \
    python3.10-venv \
    libportaudio2 \
    portaudio19-dev \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-4.0 \
    xsel \
    xdotool

echo
echo "Dependencies installed successfully!"
echo "Now run: ./install.sh"
