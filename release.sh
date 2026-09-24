#!/bin/bash
# Build, sign, notarize, and zip a release of Astros Menu Bar.
#
# Usage: ./release.sh
#
# Settings (environment variables, all optional):
#   PYTHON          Python used for the py2app build (default: see build.sh)
#   SIGN_IDENTITY   codesign identity (default: first "Developer ID Application"
#                   in the keychain)
#   NOTARY_PROFILE  notarytool keychain profile (default: notarytool); create one
#                   with `xcrun notarytool store-credentials`
#
# Output: dist/Astros-Menu-Bar-<version>-arm64.zip, signed with the Developer
# ID, notarized, and stapled — ready to attach to a GitHub release.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP="dist/Astros Menu Bar.app"
NOTARY_PROFILE="${NOTARY_PROFILE:-notarytool}"
VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' sportsbar/config.py)"
ZIP="dist/Astros-Menu-Bar-${VERSION}-arm64.zip"

if [ -z "${SIGN_IDENTITY:-}" ]; then
    SIGN_IDENTITY="$(security find-identity -v -p codesigning \
        | grep -o '"Developer ID Application:[^"]*"' | head -1 | tr -d '"' || true)"
fi
if [ -z "$SIGN_IDENTITY" ]; then
    echo "No \"Developer ID Application\" identity found in the keychain." >&2
    echo "Set SIGN_IDENTITY, or install your Developer ID certificate." >&2
    exit 1
fi

echo "=== Astros Menu Bar — Release ${VERSION} ==="
echo "Signing identity: $SIGN_IDENTITY"
echo "Notary profile:   $NOTARY_PROFILE"
echo ""

# 1. Build
./build.sh
rm -f "dist/Astros Menu Bar.zip"  # build.sh's unsigned zip — not for release

# 2. Sign every Mach-O binary, innermost first. `codesign --deep` skips the
#    extension modules py2app puts under Contents/Resources, and notarization
#    rejects anything not signed with the Developer ID and a secure timestamp.
echo ""
echo "Signing..."
SIGN=(codesign --force --timestamp --options runtime
      --entitlements entitlements.plist -s "$SIGN_IDENTITY")
count=0
while IFS= read -r -d '' f; do
    if file -b "$f" | grep -q "Mach-O"; then
        if ! out="$("${SIGN[@]}" "$f" 2>&1)"; then
            echo "$out" >&2
            exit 1
        fi
        count=$((count + 1))
    fi
done < <(find "$APP/Contents" -type f -print0)
echo "Signed $count binaries."
for fw in "$APP"/Contents/Frameworks/*.framework; do
    [ -d "$fw" ] && "${SIGN[@]}" "$fw"
done
"${SIGN[@]}" "$APP"
codesign --verify --deep --strict "$APP"
echo "Signature OK."

# 3. Notarize
echo ""
echo "Notarizing (usually 1–5 minutes)..."
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"
SUBMIT_OUT="$(xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait 2>&1)"
echo "$SUBMIT_OUT"
if ! grep -q "status: Accepted" <<< "$SUBMIT_OUT"; then
    SUBMISSION_ID="$(sed -n 's/^ *id: //p' <<< "$SUBMIT_OUT" | head -1)"
    echo "" >&2
    echo "=== Notarization failed ===" >&2
    if [ -n "$SUBMISSION_ID" ]; then
        xcrun notarytool log "$SUBMISSION_ID" --keychain-profile "$NOTARY_PROFILE" >&2 || true
    fi
    rm -f "$ZIP"
    exit 1
fi

# 4. Staple the ticket to the app, check Gatekeeper accepts it, re-zip
xcrun stapler staple "$APP"
spctl -a -vv "$APP"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"

echo ""
echo "=== Release ready ==="
echo "Zip: $SCRIPT_DIR/$ZIP ($(du -h "$ZIP" | cut -f1))"
echo ""
echo "Publish it at https://github.com/gyndok/astros-menubar/releases/new"
echo "(tag v${VERSION}, target main), or with the GitHub CLI:"
echo "  gh release create v${VERSION} \"$ZIP\" --target main --title \"Astros Menu Bar ${VERSION}\" --notes-file NOTES.md"
