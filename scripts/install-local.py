"""Install/update a user-owned copy using native Omarchy configuration APIs."""
import ctypes
import json
import os
import stat
import tempfile
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


def check_tree(path):
    """Never traverse links or accept device nodes, sockets, or FIFOs."""
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise RuntimeError("Refusing symlink: " + str(path))
    if stat.S_ISDIR(mode):
        for child in path.iterdir():
            check_tree(child)
    elif not stat.S_ISREG(mode):
        raise RuntimeError("Refusing non-regular file: " + str(path))


def prepare_parent():
    # Installation is only supported in a user-owned, non-shared directory.
    home = Path.home()
    current = home
    for part in (None, *TARGET.parent.relative_to(home).parts):
        if part is not None:
            current /= part
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise RuntimeError("Refusing symlink or non-directory destination: " + str(current))
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise RuntimeError("Destination must be user-owned and not writable by others: " + str(current))


def exchange(left, right):
    """Linux renameat2 swaps directories atomically, even when nonempty."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(left), -100, os.fsencode(right), 2):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def activate(saved, placement):
    run("omarchy-shell", "shell", "rescanPlugins")
    for _ in range(30):
        discovered = run("omarchy-shell", "shell", "listPlugins")
        if PLUGIN in discovered:
            break
        time.sleep(.2)
    else:
        raise RuntimeError("Plugin copied, but discovery timed out")
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
    prepare_parent()
    updating = TARGET.exists() or TARGET.is_symlink()
    if updating:
        check_tree(TARGET)
        if json.loads((TARGET / "manifest.json").read_text())["id"] != PLUGIN:
            raise RuntimeError("Unexpected plugin identity at destination")
    # Same filesystem as TARGET, with unpredictable name and mode 0700.
    holder = Path(tempfile.mkdtemp(prefix=".omadoro-install-", dir=TARGET.parent))
    staged = holder / "plugin"
    published = False
    disabled = False
    keep_backup = False
    try:
        staged.mkdir(mode=0o700)
        files = ["manifest.json", "Service.qml", "BarWidget.qml", "Dashboard.qml", "Settings.qml", "BreakOverlay.qml", "LICENSE"]
        for name in files + ["adapters", "components", "model"]:
            source = ROOT / name
            check_tree(source)
            if source.is_dir():
                shutil.copytree(source, staged / name, symlinks=True,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(source, staged / name, follow_symlinks=False)
        check_tree(staged)
        run("omarchy", "plugin", "validate", str(staged))
        (holder / "saved-entry.json").write_text(json.dumps(saved, indent=2))
        if updating:
            check_tree(TARGET)
            disabled = True
            run("omarchy", "plugin", "disable", PLUGIN)
            exchange(staged, TARGET)
        else:
            staged.rename(TARGET)
        published = True
        migrated = dict(saved)
        migrated.pop("meetingDetectionEnabled", None)
        migrated.pop("meetingGraceSeconds", None)
        activate(migrated, placement)
        keep_backup = updating
    except Exception:
        if published:
            # Restore the artifact before attempting any desktop recovery.
            try:
                if updating:
                    exchange(staged, TARGET)
                else:
                    TARGET.rename(staged)
            except Exception as rollback_error:
                keep_backup = True
                raise RuntimeError("Artifact rollback failed; recovery files retained at " + str(holder)) from rollback_error
        if disabled or published:
            try:
                if updating and placement:
                    activate(saved, placement)
                else:
                    run("omarchy", "plugin", "disable", PLUGIN)
                    run("omarchy-shell", "shell", "rescanPlugins")
                    run("omarchy", "restart", "shell")
            except Exception as recovery_error:
                keep_backup = True
                raise RuntimeError("Artifact restored, but desktop recovery failed; settings retained at " + str(holder)) from recovery_error
        raise
    finally:
        if keep_backup:
            print("Recovery files (previous plugin after success):", holder, flush=True)
        else:
            shutil.rmtree(holder)
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
