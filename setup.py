import re

from setuptools import setup

with open("sportsbar/config.py", encoding="utf-8") as f:
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
    # yaml is left out of "packages" (which copies whole directories) so the
    # excluded libyaml extension below really stays out; PyYAML falls back
    # to its pure-Python loader, which is all the app uses.
    "packages": ["sportsbar", "rumps", "requests", "certifi"],
    "includes": [
        "rumps",
        "requests",
        "yaml",
        "certifi",
        "charset_normalizer",
        "idna",
        "urllib3",
    ],
    # Modules py2app's import scan drags in that the app never uses: test
    # tooling, build tooling, GUI toolkits, and optional backends of
    # requests/urllib3. Several are arm64-only native code.
    "excludes": [
        # test and dev tooling
        "pytest", "_pytest", "pluggy", "iniconfig", "pygments", "py",
        # build/packaging tooling
        "setuptools", "pkg_resources", "pip", "wheel", "distutils",
        # scientific / GUI stacks
        "numpy", "tkinter", "_tkinter", "matplotlib", "PIL", "IPython",
        # optional requests/urllib3 backends
        "cryptography", "cffi", "_cffi_backend", "OpenSSL",
        "brotli", "brotlicffi", "zstandard", "socks", "chardet", "simplejson",
        # libyaml C extension (PyYAML works without it)
        "yaml._yaml", "_yaml",
    ],
}

setup(
    app=APP,
    name="Astros Menu Bar",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
