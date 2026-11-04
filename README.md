# Tune — VALORANT video-settings manager

Save your VALORANT **video** settings once, then apply them to another account on the same PC.
Small, local, portable Windows app. Not affiliated with Riot Games.

> **Each person keeps their own data.** Tune is 100% local — no server, no accounts, no uploads.
> Your profiles live only on your PC. You never see anyone else's settings and they never see yours.

Two clear tabs: **Settings** (your signed-in account and its saved profile) and **Accounts**
(switch accounts, browse and apply your saved profiles). The numbers on the Settings tab
show your **saved** profile and change only when you press Save — the game writing its own
file never changes them behind your back.

## What it does

- **Save** your current account's video settings as a named profile (works while VALORANT is open — it only reads files).
- **Apply** a saved profile onto another account, after a clear before/after review.
- **Switch account**: opens *your* Riot Client so you sign in yourself, or, if you turn it on for an account, switches in one click like TcNo Account Switcher (see below).
- **Share** a profile with a friend as a small file containing only video settings + a name you choose — no account info.

## What it does **not** do

No passwords are ever read or stored. No game-memory access, injection, overlays, input automation,
private Riot APIs or telemetry. Tune never closes VALORANT for you.

**One-click switching is opt-in.** Save an account's current sign-in (or import the ones TcNo Account
Switcher already saved) and Tune keeps a copy of Riot Client's own "Stay signed in" files for it, encrypted with Windows (DPAPI,
only readable by your Windows user on this PC). Switching closes Riot Client (never the game), puts
that copy back and starts Riot Client again. Anyone who could copy those files could sign in as you,
the same as with TcNo, so keep your PC account safe. *Help → Forget all saved sign-ins* deletes them.

## Supported settings

Transfers only these 12 keys from `GameUserSettings.ini`:

- **ScalabilityGroups**: ViewDistance, AntiAliasing, Shadow, PostProcess, Texture, Effects, Foliage, Shading, GlobalIllumination, Reflection quality (0–3)
- **ShooterGameUserSettings**: `bUseVSync` (True/False), `FrameRateLimit` (0–1000)

Mouse sensitivity is read for reference only and **never** applied. Resolution, display mode,
keybinds, crosshair and audio are left to you — Tune never touches them.

## Safety

- **Apply / Undo** require VALORANT and Riot Client to be closed, and re-check right before writing.
  (While VALORANT runs it holds settings in memory and writes them back on exit, which would undo the change.)
- A backup is written before every apply; writes are atomic; a file that changed since your review is rejected.
- Deleting a profile moves it to a local `deleted` folder; it never touches game files.
- The EXE is **unsigned** — Windows SmartScreen may warn on first run. Never disable antivirus to run it.

## Install

Download `Tune.exe` from [Releases](../../releases), or build it yourself (below). No installer, no admin rights.
Your data lives in `%LOCALAPPDATA%\PresetDesk`.

## Build from source

```powershell
python -m unittest test_capture test_reference test_desk   # run the tests
pip install -r requirements-build.txt
powershell -File build_v40.ps1                              # produces Tune.exe
```

Requires Python 3.13 with Tk. CI builds and tests every push on `windows-latest`
(see `.github/workflows/ci.yml`); tag a commit `vX.Y` to publish a Release.

## License

MIT — see [LICENSE](LICENSE). Bundled runtimes keep their own licenses; see
[THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).
