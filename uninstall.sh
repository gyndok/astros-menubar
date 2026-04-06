#!/bin/bash

PLIST_NAME="com.gyndok.astros-menubar"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "=== Astros Menu Bar Uninstaller ==="

# Kill running process
pkill -f "astros_menubar.py" 2>/dev/null && echo "Stopped running app." || echo "App was not running."

# Unload and remove LaunchAgent
if [ -f "$PLIST_PATH" ]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null
    rm -f "$PLIST_PATH"
    echo "Removed LaunchAgent."
else
    echo "No LaunchAgent found."
fi

echo ""
read -p "Delete config and cache at ~/.config/astros-menubar/? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$HOME/.config/astros-menubar"
    echo "Config and cache deleted."
else
    echo "Config preserved at ~/.config/astros-menubar/"
fi

echo ""
echo "=== Uninstall Complete ==="
