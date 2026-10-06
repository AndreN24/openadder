# OpenAdder

**Change the buttons, DPI and lighting of your Razer mouse. No Razer Synapse, no account, no internet.**

OpenAdder is a small, free program for Windows 10 and 11. It uses about 20 MB of memory.

![OpenAdder](docs/screenshot.png)

## What you can do

- Give any button a new job: a key combination, a mouse button, a media key, a DPI change, a profile change, or a program to start.
- Set up to 5 DPI stages and the polling rate.
- Change the colour, effect and brightness of the lights.
- Keep different setups as profiles, for example "Games" and "Work".

## Download

1. Open the [**Releases page**](../../releases/latest).
2. Download **`OpenAdder-…-Setup.exe`** and open it.
3. Follow the steps.

Windows can show **"Windows protected your PC"**. This is normal for new free programs. Click **More info**, then **Run anyway**.

No installation: download `OpenAdder-…-portable.zip`, right-click it, choose **Extract All**, and open `OpenAdder.exe`.

## How to use it

1. Close Razer Synapse if you have it.
2. Start OpenAdder. It finds your mouse by itself.
3. Click a button in the picture or in the list, and choose a new job.

DPI and lighting are saved on the mouse. Button changes work while OpenAdder runs. When you close the window, OpenAdder stays in the tray (next to the clock). Tick **Start with Windows** to start it automatically.

**Emergency:** if a button change makes the mouse hard to use, press **Ctrl + Alt + Shift + Esc**. All buttons go back to normal.

**Undo everything:** **Manage → Reset everything…**

## Supported mice

| Mouse | Status |
|---|---|
| DeathAdder V2 | Tested |
| DeathAdder V2 Mini, V2 Lite | Not tested yet |
| DeathAdder V3 (wired) | Not tested yet |
| DeathAdder Elite | Not tested yet |
| DeathAdder Essential (all versions) | Not tested yet |
| Cobra (wired) | Not tested yet |

Wireless mice are not supported yet.

**Do you have a mouse that is "not tested yet"?** Please try it. Then click **Manage → Copy mouse report** and paste the report into a [new issue](../../issues/new/choose). Tell us what works and what does not. The report contains no personal data.

## Questions

**"Mouse not found"**: plug the mouse in and close Razer Synapse. OpenAdder connects by itself.

**My buttons stopped working after a restart**: OpenAdder must run for button changes. Tick **Start with Windows**.

**A game ignores my button changes**: some anti-cheat software blocks changed input. DPI and lighting still work.

**Uninstall**: Windows **Settings → Apps → OpenAdder → Uninstall**. Your settings are in `%APPDATA%\OpenAdder`.

**Is it safe?** OpenAdder only talks to your mouse. It does not use the internet and collects no data. The code is open: anyone can check it here.

## For developers

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): how it works, how to build it, how to run the tests, and how to add a mouse.

## Credits and license

- [OpenRazer](https://github.com/openrazer/openrazer): mouse protocol and model data.
- [gpoulios/deathadderv2](https://github.com/gpoulios/deathadderv2): DPI stage format.
- [Snakecharmer](https://github.com/asavs/snakecharmer): outline of the mouse picture.

License: **GNU General Public License v2.0 or later** ([LICENSE](LICENSE)).

OpenAdder is not made by or connected to Razer Inc. "Razer", "DeathAdder" and "Cobra" are trademarks of Razer Inc.
