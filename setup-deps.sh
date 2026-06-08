#!/usr/bin/env bash
#
# Whispr system dependency installer (requires sudo)
#

set -e

echo "Installing Whispr system dependencies..."
echo

sudo apt update
sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-4.0 \
    gir1.2-gtk-3.0 \
    libportaudio2 \
    portaudio19-dev \
    sox \
    libsox-fmt-all \
    xsel \
    xdotool \
    libnotify-bin \
    pkg-config

echo
echo "Done. Now run: ./install.sh"
