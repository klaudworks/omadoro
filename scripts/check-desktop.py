"""Run the read-only desktop adapter check in the active Hyprland session."""
import json
import os
from pathlib import Path
import select
import subprocess

helper = Path(__file__).resolve().parents[1] / "adapters/desktop.py"
environment = {"PATH": "/usr/bin:/bin"}
for name in ("HOME", "XDG_RUNTIME_DIR", "WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE",
             "OMARCHY_PATH", "DBUS_SESSION_BUS_ADDRESS", "DBUS_SYSTEM_BUS_ADDRESS"):
    value = os.environ.get(name)
    if value:
        environment[name] = value
process = subprocess.Popen(["/usr/bin/python3", str(helper)], env=environment,
                           stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
try:
    samples = []
    for _ in range(3):
        if not select.select([process.stdout], [], [], 5)[0]:
            raise RuntimeError("No clock sample within five seconds")
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("Helper exited: " + process.stderr.read())
        sample = json.loads(line)
        samples.append(sample)
        print(json.dumps(sample), flush=True)
    assert samples[-1]["monoMs"] > samples[0]["monoMs"]
    assert samples[-1]["bootMs"] > samples[0]["bootMs"]
    assert all(sample["locked"] is False for sample in samples), "Run while unlocked"
    assert all(sample["logindHealthy"] for sample in samples)
    process.stdin.close()
    assert process.wait(timeout=3) == 0
    diagnostic_errors = process.stderr.read()
    assert not diagnostic_errors, diagnostic_errors
    print("Clock sampling, unlocked observation, logind subscription, EOF cleanup: pass")
finally:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=3)
