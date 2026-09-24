"""macOS integration: single-instance handoff and the login LaunchAgent."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from AppKit import NSBundle, NSRunningApplication

from .config import CONFIG_DIR


LAUNCH_AGENT_LABEL = "com.gyndok.astros-menubar"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
BUNDLE_ID = "com.gyndok.astros-menubar"


def _bundle_executable() -> Optional[str]:
    """Path of the .app's main executable, or None when running from source."""
    try:
        bundle = NSBundle.mainBundle()
        if bundle.bundleIdentifier() == BUNDLE_ID:
            return str(bundle.executablePath())
    except Exception:
        pass
    return None


def terminate_other_instances() -> None:
    """If another copy of the bundled app is running, quit it — the newly
    launched copy wins. Makes replacing the app with a newer version a
    clean handoff instead of two menu bar items."""
    if _bundle_executable() is None:
        return  # running from source — never touch other processes
    try:
        import os
        me = os.getpid()
        for ra in NSRunningApplication.runningApplicationsWithBundleIdentifier_(BUNDLE_ID):
            if ra.processIdentifier() != me:
                logging.info("Terminating older instance (pid %s)", ra.processIdentifier())
                ra.terminate()
    except Exception as exc:
        logging.exception("terminate_other_instances failed: %s", exc)


def install_launch_agent(script: str) -> None:
    """Install (or repair) the LaunchAgent so the app starts on login.

    `script` is the entry-point script's path, used when running from source.
    """
    import sys
    bundle_exec = _bundle_executable()
    executable = bundle_exec or sys.executable

    if LAUNCH_AGENT_PATH.exists():
        if bundle_exec is None:
            return  # running from source — leave any custom agent alone
        # Rewrite the agent if it points somewhere stale (the app was
        # moved, e.g. Downloads → Applications, or replaced by an update
        # at a different path). Same path → nothing to do.
        try:
            import plistlib
            with LAUNCH_AGENT_PATH.open("rb") as f:
                existing = plistlib.load(f)
            args = existing.get("ProgramArguments", [])
            if args and args[0] == executable:
                return
            if any("astros_menubar.py" in str(a) for a in args):
                return  # source-based install (dev setup) — respect it
        except Exception:
            pass  # unreadable plist — rewrite it below
        subprocess.run(["launchctl", "unload", str(LAUNCH_AGENT_PATH)], check=False)

    # If inside a .app bundle, the executable IS the app
    if bundle_exec is not None:
        program_args = f"<string>{executable}</string>"
    else:
        program_args = f"<string>{executable}</string>\n        <string>{script}</string>"

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCH_AGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        {program_args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{CONFIG_DIR / "stdout.log"}</string>
    <key>StandardErrorPath</key>
    <string>{CONFIG_DIR / "stderr.log"}</string>
</dict>
</plist>
"""
    try:
        LAUNCH_AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAUNCH_AGENT_PATH.write_text(plist_content)
        subprocess.run(["launchctl", "load", str(LAUNCH_AGENT_PATH)], check=False)
        logging.info("LaunchAgent installed at %s", LAUNCH_AGENT_PATH)
    except Exception as exc:
        logging.exception("Failed to install LaunchAgent: %s", exc)
