#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/opt/homebrew/bin/python3.13"

echo "=== Astros Menu Bar — Build ==="

cd "$SCRIPT_DIR"

# Install build dependency
echo "Installing py2app..."
$PYTHON -m pip install --user --break-system-packages py2app 2>/dev/null || \
$PYTHON -m pip install py2app

# Clean previous build
rm -rf build dist

# Build the .app bundle
echo "Building .app..."
$PYTHON setup.py py2app 2>&1

if [ -d "dist/Astros Menu Bar.app" ]; then
    echo ""
    echo "=== Build Successful ==="
    echo "App: $SCRIPT_DIR/dist/Astros Menu Bar.app"
    echo ""
    echo "To share: zip the .app and send it"
    echo "  cd dist && zip -r 'Astros Menu Bar.zip' 'Astros Menu Bar.app'"
    echo ""
    # Create the zip automatically
    cd dist
    zip -r "Astros Menu Bar.zip" "Astros Menu Bar.app" -x "*.DS_Store"
    echo "Zip created: $SCRIPT_DIR/dist/Astros Menu Bar.zip"
    echo "Send this file to your brother and sister!"
else
    echo ""
    echo "=== Build Failed ==="
    echo "Check output above for errors."
    exit 1
fi
