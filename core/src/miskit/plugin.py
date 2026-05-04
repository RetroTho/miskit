import json
import subprocess
import sys
import urllib.request
from importlib.metadata import entry_points


_REPO = "https://github.com/RetroTho/miskit"
_API = "https://api.github.com/repos/RetroTho/miskit/contents/plugins"


def install(name):
    if name.startswith("https://") or name.startswith("http://"):
        url = f"git+{name}"
    elif name.startswith("/") or name.startswith(".") or name.startswith("~"):
        url = name
    else:
        url = f"git+{_REPO}#subdirectory=plugins/{name}"
    subprocess.run(
        [sys.executable, "-m", "pip", "install", url],
        check=True,
    )


def remove(name):
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", f"miskit-{name}"],
        check=True,
    )


def run_setup(name):
    from miskit.provider import load_provider
    provider = load_provider(name)
    setup = getattr(provider, "setup", None)
    if not callable(setup):
        raise ValueError(f"{name} does not have a setup command.")
    setup()


def list_available(write=print):
    with urllib.request.urlopen(_API, timeout=10) as response:
        entries = json.loads(response.read().decode("utf-8"))
    plugins = sorted(e["name"] for e in entries if e["type"] == "dir")
    if not plugins:
        write("No plugins available.")
        return
    for name in plugins:
        write(f"  {name}")


def list_installed(write=print):
    groups = ["miskit.providers", "miskit.channels"]
    plugins = sorted(
        (ep for group in groups for ep in entry_points(group=group)),
        key=lambda ep: ep.name,
    )
    if not plugins:
        write("No plugins installed.")
        return
    for ep in plugins:
        write(f"  {ep.name}")
