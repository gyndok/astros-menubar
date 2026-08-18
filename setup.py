import re

from setuptools import setup

with open("astros_menubar.py", encoding="utf-8") as f:
    VERSION = re.search(r'APP_VERSION = "([^"]+)"', f.read()).group(1)

APP = ["astros_menubar.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "LSUIElement": True,
        "CFBundleName": "Astros Menu Bar",
        "CFBundleDisplayName": "Astros Menu Bar",
        "CFBundleIdentifier": "com.gyndok.astros-menubar",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
    },
    "packages": ["rumps", "requests", "yaml", "certifi"],
    "includes": [
        "rumps",
        "requests",
        "yaml",
        "certifi",
        "charset_normalizer",
        "idna",
        "urllib3",
    ],
}

setup(
    app=APP,
    name="Astros Menu Bar",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
