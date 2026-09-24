#!/usr/bin/env python3
"""
Houston Astros Menu Bar App.

Follow the Astros all season from your macOS menu bar.
Built with rumps for macOS menubar display.

This is the entry point (py2app and the LaunchAgent run this file); the
app itself lives in the `sportsbar` package.
"""

import logging
from pathlib import Path

from sportsbar.app import AstrosMenuBarApp
from sportsbar.config import setup_logging
from sportsbar.system import install_launch_agent, terminate_other_instances

if __name__ == "__main__":
    setup_logging()
    terminate_other_instances()
    install_launch_agent(str(Path(__file__).resolve()))
    try:
        app = AstrosMenuBarApp()
        app.run()
    except Exception as error:
        logging.exception("Fatal app error: %s", error)
