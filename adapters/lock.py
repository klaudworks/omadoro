"""Request Omarchy's authenticated session lock and verify compositor coverage.

This helper never unlocks the session or handles authentication credentials.
"""
import json
import subprocess
import sys
import time


def run(*command):
    return subprocess.run(command, check=True, capture_output=True, text=True,
                          timeout=3).stdout.strip()


def lock_session():
    # The system command also locks the password manager and stops screensavers.
    # Its exit status alone does not prove the compositor has secured the session.
    run("omarchy", "system", "lock")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = json.loads(run("omarchy-shell", "lock", "status"))
        if not isinstance(status, dict):
            raise RuntimeError("Invalid session-lock status")
        if status.get("secure") is True:
            return
        if status.get("passwordPam") is False:
            raise RuntimeError("Omarchy password authentication is unavailable")
        time.sleep(0.1)
    raise RuntimeError("The compositor did not confirm a secure session lock")


def main():
    try:
        lock_session()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print("Could not confirm locking. Lock the desktop manually before leaving.", file=sys.stderr)
        print(str(error), file=sys.stderr)
        return 1
    print("secure", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
