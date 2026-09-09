# Development

The QML service owns the timer; the bar and overlays render its state. `model/` contains plain JavaScript tested with injected clocks. `adapters/desktop.py` supplies Linux monotonic/boottime clocks, logind sleep events, and Hyprland lock observations through a managed local process. No network service or timer history is involved.

## Local installation

From a separate checkout, run `python scripts/install-local.py`. This copies the runtime files into `~/.config/omarchy/plugins/klaudworks.omadoro`, enables the plugin, and restarts the shell. Repeat to update the local copy. The installer preserves settings and backs up the previous artifact and settings entry under `/tmp/omadoro-backup-*`; move backups elsewhere to retain them across cleanup or reboot. Local copies use this installer for updates; the public README uses Omarchy's git-managed installation instead.

## Checks

```sh
node tests/model.test.cjs
python -m unittest discover -s tests -p '*_test.py'
python -m py_compile adapters/desktop.py scripts/*.py
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

Developed against Omarchy 4.0.0.alpha, Quickshell 0.3.1, and Hyprland 0.56.2. Real suspend/lock transitions, mixed-scale multi-monitor hotplug, and long-session resource use still need end-to-end verification. Model tests cover the corresponding state transitions but do not validate the compositor.

Lock detection uses Hyprland's `solitaryBlockedBy` monitor diagnostic. Unknown lock state freezes work and hides break surfaces. If timing or display coverage fails, the timer stops and releases its overlays. A break is not a security lock screen.

For a desktop smoke check, try Pause/Resume, +5 min, Reset, Settings, and Break now. With immediate skipping enabled, Escape should return to work. A one-minute work interval and a `0.1`-minute break exercise the automatic warning and return; restore your preferred durations afterward.

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
