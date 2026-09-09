"""Install/update a user-owned copy using native Omarchy configuration APIs."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "klaudworks.omadoro"
TARGET = Path.home() / ".config/omarchy/plugins" / PLUGIN


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def main():
    for executable in ("omarchy", "omarchy-shell", "python"):
        if not shutil.which(executable):
            raise RuntimeError("Required command not found: " + executable)
    run("python", "-c", "import dbus, gi; gi.require_version('GLibUnix', '2.0'); from gi.repository import GLib, GLibUnix")
    if ROOT == TARGET.resolve():
        raise RuntimeError("Run the installer from a separate checkout, outside the installed plugin directory")
    run("omarchy", "plugin", "validate", str(ROOT))
    config_path = Path.home() / ".config/omarchy/shell.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    saved = next((entry for section in ["left", "center", "right"]
                  for entry in config.get("bar", {}).get("layout", {}).get(section, [])
                  if entry.get("id") == PLUGIN), {})
    placement = next(((section, index) for section in ["left", "center", "right"]
                      for index, entry in enumerate(config.get("bar", {}).get("layout", {}).get(section, []))
                      if entry.get("id") == PLUGIN), None)
    if TARGET.is_symlink():
        raise RuntimeError("Refusing to overwrite a symlinked plugin")
    if TARGET.exists():
        if json.loads((TARGET / "manifest.json").read_text())["id"] != PLUGIN:
            raise RuntimeError("Unexpected plugin identity at destination")
        backup = Path("/tmp") / ("omadoro-backup-" + str(time.time_ns()))
        shutil.copytree(TARGET, backup)
        (backup / "saved-entry.json").write_text(json.dumps(saved, indent=2))
        print("Previous artifact and settings entry:", backup, flush=True)
        run("omarchy", "plugin", "disable", PLUGIN)
    TARGET.mkdir(parents=True, exist_ok=True)
    files = ["manifest.json", "Service.qml", "BarWidget.qml", "Dashboard.qml", "Settings.qml", "BreakOverlay.qml", "LICENSE"]
    for filename in files:
        shutil.copy2(ROOT / filename, TARGET / filename)
    for folder in ["adapters", "components", "model"]:
        shutil.copytree(ROOT / folder, TARGET / folder, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    run("omarchy", "plugin", "validate", str(TARGET))
    run("omarchy-shell", "shell", "rescanPlugins")
    for _ in range(30):
        discovered = run("omarchy-shell", "shell", "listPlugins")
        if PLUGIN in discovered:
            break
        time.sleep(.2)
    else:
        raise RuntimeError("Plugin copied, but discovery timed out")
    # enablePlugin accepts placement, not settings. Restore each saved field
    # through the native bar API before restarting the retained service.
    saved = dict(saved)
    saved.pop("meetingDetectionEnabled", None)
    saved.pop("meetingGraceSeconds", None)
    result = run("omarchy-shell", "shell", "enablePlugin", PLUGIN, "{}")
    if result not in ("ok", "true", ""):
        raise RuntimeError("Enable failed: " + result)
    for key, value in saved.items():
        if key == "id":
            continue
        result = run("omarchy-shell", "shell", "setBarWidget", PLUGIN, key, json.dumps(value), "{}")
        if result not in ("ok", "true", ""):
            raise RuntimeError("Could not restore setting " + key + ": " + result)
    if placement:
        run("omarchy", "bar", "move", PLUGIN, "--section", placement[0], "--index", str(placement[1]))
    run("omarchy", "restart", "shell")
    print("Installed", TARGET)
    print("Recovery: omarchy plugin disable " + PLUGIN)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print("Installation failed: " + (error.stderr or error.stdout or str(error)).strip(), file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, RuntimeError) as error:
        print("Installation failed: " + str(error), file=sys.stderr)
        sys.exit(1)
