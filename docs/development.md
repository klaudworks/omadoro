# Development

The QML service owns the timer; the bar and overlays render its state. `model/` contains plain JavaScript tested with injected clocks. `adapters/desktop.py` supplies Linux monotonic/boottime clocks, logind sleep events, and Hyprland lock observations through a managed local process. No network service or timer history is involved.

## Local installation

From a separate checkout, run `python scripts/install-local.py`. This copies the runtime files into `~/.config/omarchy/plugins/klaudworks.omadoro`, enables the plugin, and restarts the shell. Repeat to update the local copy. The installer preserves settings and backs up the previous artifact and settings entry under `/tmp/omadoro-backup-*`; move backups elsewhere to retain them across cleanup or reboot. Local copies use this installer for updates; the public README uses Omarchy's git-managed installation instead.

## Checks

```sh
node tests/model.test.cjs
python -m unittest discover -s tests -p '*_test.py'
python -m py_compile adapters/*.py scripts/*.py
omarchy plugin validate .
python scripts/check-desktop.py  # optional: active, unlocked Hyprland session
```

Node and Python checks run in GitHub Actions. The desktop check needs `python-dbus` and `python-gobject`.

For QML lint with the installed shell's virtual `qs` import:

```sh
mkdir -p /tmp/omadoro-qml-imports
ln -sfn /usr/share/omarchy/shell /tmp/omadoro-qml-imports/qs
/usr/lib/qt6/bin/qmllint -I /tmp/omadoro-qml-imports *.qml components/*.qml adapters/*.qml
```

The installed host's style/bar-member and PanelWindow metadata produce lint diagnostics; lint is not a clean CI gate. Native plugin validation doesn't prove runtime behavior.

## Prototype limits

Current desktop baseline: Omarchy 4.0.3-1, Quickshell 0.3.1-1, and Hyprland 0.56.2-2. Real suspend/lock transitions, mixed-scale multi-monitor hotplug, and long-session resource use still need end-to-end verification. Model tests cover the corresponding state transitions but do not validate the compositor.

Lock detection uses Hyprland's `solitaryBlockedBy` monitor diagnostic. Unknown lock state freezes work and hides break surfaces. If timing or display coverage fails, the timer stops and releases its overlays. A break is not a security lock screen.

For a desktop smoke check, try Pause/Resume, +5 min, Reset, Settings, and Break now. With immediate skipping enabled, Escape should return to work. A one-minute work interval and a `0.1`-minute break exercise the automatic warning and return; restore your preferred durations afterward.

## Idle, locking, and logout

Omadoro observes inactivity separately from Omarchy's screensaver/lock service. Work pauses after the configured idle threshold (60 seconds by default); continuous absence, including that threshold period, counts toward a break. Returning after a full break's worth of absence resets the work interval while preserving manual pause intent.

The break overlay does not create an idle inhibitor or disable Omarchy’s screensaver, automatic lock, or suspend behavior. **Lock during breaks**, when enabled, explicitly locks at break start even if Stay Awake is active. An active break keeps counting while idle. When the adapter detects a lock or suspend, Omadoro hides its surfaces and counts that time toward the active break. On return, it shows any remaining break, or starts a fresh work interval if the break finished. It never unlocks the session.

By default, `respectIdleInhibitors` is true: Omadoro respects compositor idle inhibitors and Omarchy’s Stay Awake setting when deciding whether inactivity counts as rest. The work timer continues during inhibition; this setting does not postpone scheduled breaks. Disable **Respect Stay Awake and video** to count input inactivity regardless. Video players must actually advertise an idle inhibitor for it to be respected. See [Quickshell’s IdleMonitor documentation](https://quickshell.org/docs/v0.3.0/types/Quickshell.Wayland/IdleMonitor/). Changing this preference resets accumulated idle credit.

Omarchy's normal idle service starts a screensaver and locks; it does not log out. An actual logout ends the shell and its managed helper. The next login starts a fresh timer according to autostart preferences. These interactions are based on the implementation and model tests; live screensaver/lock/suspend integration remains to be verified.

## Lock during breaks

**Experimental; desktop compatibility testing is incomplete.** The optional `lockOnBreak` preference defaults to false. It is snapshotted for each break. After the break surfaces are ready, the service requests `omarchy system lock` once. Omarchy owns authentication and the compositor session lock; Omadoro never creates a second session lock and never calls unlock. The normal Omarchy lock screen replaces the countdown while locked.

`adapters/lock.py` checks the host's `secure` status, not merely request acceptance. A failed command, invalid status, missing authentication, or confirmation timeout stops the timer with a message to lock manually. A service watchdog covers helper startup failure. Timer commands wait for the lock handshake; failures open the dashboard error panel. The normal system command also performs Omarchy's password-manager locking and screensaver cleanup.

Unlocking early returns to any remaining break and its skip policy, without another lock request for that break. Finishing the timer or disabling Omadoro never unlocks the desktop. A successful confirmation is a point-in-time observation, not a guarantee that later authentication or system changes cannot unlock it.

Before relying on this feature, verify on the target desktop: automatic and manual breaks; authentication before and after break expiry; a screensaver starting at the same time; Stay Awake and video inhibitors; suspend/resume; monitor attachment/removal; and shell restart while locked. Confirm there is no desktop exposure or immediate relock after successful authentication. Automated tests cover the request handshake and timer transitions, but the full desktop interaction matrix has not yet been verified.

## IPC and recovery

```sh
omarchy-shell omadoro status
omarchy-shell omadoro settings
omarchy-shell omadoro action pause
omarchy-shell omadoro action resume
```

Actions: `start`, `pause`, `resume`, `stop`, `break`, `add`, `reset`, `skip`. Work actions cannot bypass an active break's skip policy.

Disable with `omarchy plugin disable klaudworks.omadoro`. If the shell becomes unresponsive, run `omarchy restart shell` from another session. To roll back an update, disable the plugin, restore its directory from the installer's backup, rescan, and enable it again. The backup's `saved-entry.json` contains its prior settings; restore those selectively, without replacing unrelated shell configuration.

The meditation glyph is supplied by the desktop's existing Nerd Font; no font is bundled. Colors and UI components come from Omarchy.

### Desktop verification, 2026-09-09

Passed on the single built-in display: a 10-second break reached zero while the compositor remained securely locked; early authentication returned to the remaining break; skipping did not cause a second lock. These observations establish those paths only.

The screensaver was observed mapped before the subsequent lock request. The combined virtual-monitor test failed: an external-only monitor policy treated the headless test output as an external display and disabled the laptop panel. Removing that output left the shell reporting no real outputs and unable to create a lock surface; the user encountered a black screen and hard-rebooted. No core dump was recorded. The precise reason panel recovery failed remains unresolved. Do not repeat headless-output testing on such a configuration without an independently verified display recovery path.

Automatic break locking and autostart were disabled after the incident. Suspend/resume and physical hotplug remain unverified. Automated tests and the two passing lock checks do not establish readiness to rely on this feature.

A dedicated screensaver-to-lock repeat passed after explicit user confirmation, without monitor changes or suspend: the screensaver window was mapped, the compositor confirmed a secure lock, the 20-second break expired while still locked, and normal authentication returned to work. No timer error or remaining screensaver process was observed. Original preferences were restored and the timer left paused with automatic locking off. The user confirmed a clean transition; lock-screen display blanking woke normally on input. This does not establish the untested cases above.

Stay Awake and compositor idle inhibition passed dedicated checks with a five-second idle threshold. Stay Awake kept the work countdown running without idle credit. A focused normal test window established an inhibitor, independently verified by simultaneous input-only and inhibitor-aware monitors: with protection on, Omadoro kept counting work; with protection off, it detected inactivity and stopped the countdown after approximately five seconds. The initial layer-window fixture was inconclusive because the compositor did not honor its inhibitor. All settings and Stay Awake state were restored, the test window closed, and the timer left paused. This verifies the inhibitor mechanism, not every video player's integration.
