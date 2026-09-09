"""Read-only Linux clock/lifecycle adapter; one managed process, no files or audio.

Requires the target's existing python-dbus and python-gobject packages.
Hyprland's monitor LOCK diagnostic is sampled once a second on the supported
Omarchy baseline. Unknown lock state pauses desktop presentation.
"""

import json
import os
import signal
import socket
import sys
import time

import dbus
import gi
from dbus.mainloop.glib import DBusGMainLoop
gi.require_version("GLibUnix", "2.0")
from gi.repository import GLib, GLibUnix


def compositor_lock():
    """Return true/false/None, preserving the installed lock probe's uncertainty."""
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    if not runtime or not signature:
        return None
    path = f"{runtime}/hypr/{signature}/.socket.sock"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(0.25)
            client.connect(path)
            client.sendall(b"j/monitors")
            data = bytearray()
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > 1024 * 1024:
                    return None
        monitors = json.loads(data)
        blockers = [monitor.get("solitaryBlockedBy") for monitor in monitors]
        # Missing diagnostic fields are not evidence of an unlocked desktop.
        if any(not isinstance(value, list) for value in blockers):
            return None
        if any("LOCK" in value for value in blockers):
            return True
        if any("WORKSPACE" not in value for value in blockers):
            return False
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def main():
    DBusGMainLoop(set_as_default=True)
    loop = GLib.MainLoop()
    state = {"sleeping": None, "sleepSignals": 0, "logindHealthy": False,
             "lastSleepEvent": "none", "error": "", "lockTransitions": 0,
             "lastLockEvent": "none"}
    start_mono = time.monotonic_ns()
    start_boot = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    sequence = 0
    last_locked = None

    def emit(event="sample"):
        nonlocal sequence, last_locked
        sequence += 1
        # The socket query runs in this helper, never in the shell UI thread.
        locked = compositor_lock()
        if isinstance(locked, bool):
            if isinstance(last_locked, bool) and locked != last_locked:
                state["lockTransitions"] += 1
                state["lastLockEvent"] = "locked" if locked else "unlocked"
            last_locked = locked
        else:
            last_locked = None
        now_mono = time.monotonic_ns()
        now_boot = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        stay_awake = os.path.isfile(os.path.expanduser("~/.local/state/omarchy/indicators/stay-awake"))
        packet = dict(state, event=event, sequence=sequence, locked=locked, stayAwake=stay_awake,
                      monoMs=now_mono / 1_000_000, bootMs=now_boot / 1_000_000,
                      runElapsedMs=(now_mono - start_mono) / 1_000_000,
                      restElapsedMs=(now_boot - start_boot) / 1_000_000,
                      suspendElapsedMs=((now_boot - start_boot) - (now_mono - start_mono)) / 1_000_000)
        try:
            print(json.dumps(packet, separators=(",", ":")), flush=True)
        except BrokenPipeError:
            loop.quit()
            return False
        return True

    def sleep_event(sleeping):
        state.update(sleeping=bool(sleeping), sleepSignals=state["sleepSignals"] + 1,
                     lastSleepEvent="preparing" if sleeping else "resumed")
        emit("sleep")

    def owner_changed(name, old_owner, new_owner):
        if str(name) == "org.freedesktop.login1" and str(old_owner) != str(new_owner):
            state.update(logindHealthy=False, sleeping=None, error="logind owner changed; restart Omadoro")
            emit("unavailable")

    try:
        bus = dbus.SystemBus()
        bus.add_signal_receiver(sleep_event, signal_name="PrepareForSleep",
                                dbus_interface="org.freedesktop.login1.Manager",
                                bus_name="org.freedesktop.login1", path="/org/freedesktop/login1")
        bus.add_signal_receiver(owner_changed, signal_name="NameOwnerChanged",
                                dbus_interface="org.freedesktop.DBus", arg0="org.freedesktop.login1")
        obj = bus.get_object("org.freedesktop.login1", "/org/freedesktop/login1")
        props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        sleeping = props.Get("org.freedesktop.login1.Manager", "PreparingForSleep", timeout=2)
        state.update(sleeping=bool(sleeping), logindHealthy=True)
        bus.call_on_disconnection(lambda connection: (state.update(
            logindHealthy=False, sleeping=None, error="System bus disconnected"), emit("unavailable")))
    except dbus.DBusException as error:
        state["error"] = str(error.get_dbus_name())

    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: (loop.quit(), False)[1])
    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: (loop.quit(), False)[1])
    # EOF from the owning Process terminates the helper even if its UI vanishes.
    def parent_closed(fd, condition):
        if condition & (GLib.IO_HUP | GLib.IO_ERR) or not os.read(fd, 4096):
            loop.quit()
            return False
        return True
    GLib.io_add_watch(sys.stdin.fileno(), GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, parent_closed)
    emit("initial")
    GLib.timeout_add_seconds(1, emit)
    loop.run()


if __name__ == "__main__":
    main()
