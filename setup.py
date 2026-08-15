from setuptools import setup

APP = ["astros_menubar.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "LSUIElement": True,
        "CFBundleName": "Astros Menu Bar",
        "CFBundleDisplayName": "Astros Menu Bar",
        "CFBundleIdentifier": "com.gyndok.astros-menubar",
        "CFBundleVersion": "1.1.0",
        "CFBundleShortVersionString": "1.1.0",
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
