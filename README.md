# Omadoro

A small work/break timer for Omarchy's built-in Quickshell bar. Work for **50 minutes**, take a **5-minute break**, and repeat. Uses your desktop theme and pauses work while you're idle.

| Timer | Break warning | Screen break |
| :---: | :---: | :---: |
| [<img src="docs/screenshots/timer.png" alt="Bar timer with Pause, Break now, and Settings" width="260">](docs/screenshots/timer.png) | [<img src="docs/screenshots/warning.png" alt="12-second break warning with a +5 min button" width="260">](docs/screenshots/warning.png) | [<img src="docs/screenshots/break.png" alt="Full-screen five-minute break with delayed skipping" width="260">](docs/screenshots/break.png) |

## Quickstart

For **Omarchy 4’s built-in bar**. Older Waybar setups aren’t supported.

```sh
omarchy plugin add https://github.com/klaudworks/omadoro.git --enable
```

Click the meditator in the bar, then **Break now** to try it. By default, **Escape** or **Skip** returns you to work.

## Highlights

- **A timer that fits your desktop.** Native theme colors, a compact bar countdown, and full-screen breaks.
- **Your own rhythm.** Set work and break durations, pause when needed, or add five more minutes.
- **A gentle heads-up.** A 15-second warning before your break, with optional postponement.
- **Idle-aware breaks.** Time away can count as rest. Stay Awake and video inhibitors are respected by default.
- **Optional authenticated locking — experimental.** Configure **Lock during breaks** to hand off to Omarchy’s lock screen before leaving your desk. Authentication is still required after the break ends. Suspend/resume and physical monitor changes have not been fully verified.

To update, run `omarchy plugin update klaudworks.omadoro`, then `omarchy restart shell` to reload the timer. Settings are preserved.

To disable:

```sh
omarchy plugin disable klaudworks.omadoro
```

To uninstall: `omarchy plugin remove klaudworks.omadoro`.
