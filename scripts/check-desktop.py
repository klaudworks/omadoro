"""Run the read-only desktop adapter check in the active Hyprland session."""
import json
from pathlib import Path
import select
import subprocess

helper = Path(__file__).resolve().parents[1] / "adapters/desktop.py"
process = subprocess.Popen(["python", str(helper)], stdin=subprocess.PIPE,
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
