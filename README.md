<p align="center">
  <img src="assets/icon.png" width="120" alt="LoLCustomRPC Logo">
</p>

<h1 align="center">LoLCustomRPC</h1>

<p align="center">
  Custom Discord Rich Presence for League of Legends
</p>

<p align="center">
  <img src="https://img.shields.io/github/v/release/Katlicia/LOLCustomRPC?style=flat-square" alt="Release">
  <img src="https://img.shields.io/github/license/Katlicia/LOLCustomRPC?style=flat-square" alt="License">
  <img src="https://img.shields.io/github/issues/Katlicia/LOLCustomRPC?style=flat-square" alt="Issues">
  <img src="https://img.shields.io/github/downloads/Katlicia/LOLCustomRPC/total?style=flat-square" alt="Downloads">
</p>

---

## What is it?

LoLCustomRPC shows your League of Legends game status on Discord — champion, KDA, rank, role, queue type and more. It runs in the background as a tray icon and updates automatically.

## Features

- Live game status — champion, KDA, role, queue type, game mode
- Lobby & champion select detection
- Rank display (Iron → Challenger) with localized tier names
- Summoner name, tag, and level display
- 16 language support with official LoL localizations
- Auto-update — checks GitHub Releases on startup and installs with one click
- Minimal system tray footprint
- Start with Windows option

## Preview


## Installation

1. Download the latest `LoLCustomRPC.exe` from [Releases](https://github.com/Katlicia/LOLCustomRPC/releases/latest)
2. Run the exe — no installation needed
3. Open League of Legends
4. Discord will show your status automatically

## Settings

Open the settings window to customize:

- **Display** — toggle nick, tag, rank, level, KDA, role; choose logo
- **General** — start with Windows, start minimized, auto update, language
- **Updates** — check for updates manually, view release notes

## Building from Source

**Requirements:** Python 3.10+

```bash
git clone https://github.com/Katlicia/LOLCustomRPC.git
cd LOLCustomRPC
pip install -r requirements.txt
python main.py
```

**Build exe:**

```bash
pip install pyinstaller
pyinstaller LoLCustomRPC.spec
```

The output will be at `dist/LoLCustomRPC.exe`.

## Reporting a Bug

Click the bug icon in the top-right corner of the app, or open an issue directly at [GitHub Issues](https://github.com/Katlicia/LOLCustomRPC/issues/new).

## License

MIT
