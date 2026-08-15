#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_SCRIPT="$SCRIPT_DIR/astros_menubar.py"
PLIST_NAME="com.gyndok.astros-menubar"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "=== Astros Menu Bar Installer ==="

# Find a Homebrew Python (framework build — required for menu bar apps).
# Works on Apple Silicon (/opt/homebrew) and Intel (/usr/local).
PYTHON=""
for candidate in \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    /opt/homebrew/bin/python3.* \
    /usr/local/bin/python3.*; do
    if [ -x "$candidate" ]; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Homebrew Python not found."
    echo "Install with: brew install python"
    exit 1
fi
echo "Using Python: $PYTHON"

# Install Python dependencies
echo "Installing Python dependencies..."
$PYTHON -m pip install --user --break-system-packages -r "$SCRIPT_DIR/requirements.txt"

# Create config directory
mkdir -p "$HOME/.config/astros-menubar/cache"
echo "Config directory created at ~/.config/astros-menubar/"

# Create LaunchAgent plist
cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$APP_SCRIPT</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$HOME/.config/astros-menubar/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.config/astros-menubar/stderr.log</string>
</dict>
</plist>
PLIST

# Load the LaunchAgent
launchctl load "$PLIST_PATH"

echo ""
echo "=== Installation Complete ==="
echo "The ⚾ icon should appear in your menu bar."
echo ""
echo "To configure odds, edit ~/.config/astros-menubar/config.yaml"
echo "and add your API key from https://the-odds-api.com"
echo ""
echo "To uninstall: bash $SCRIPT_DIR/uninstall.sh"
