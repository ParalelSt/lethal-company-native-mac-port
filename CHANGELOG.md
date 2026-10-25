# Changelog

All notable changes to the launcher and build kit. Each GitHub release uses the matching section as its notes.
Format: [Keep a Changelog](https://keepachangelog.com). Versions follow the launcher, not the game.

## [Unreleased]

### Added
- Add to Steam: registers the native and modded apps as Steam shortcuts so Play launches through Steam and the real Steam overlay works (`steam-shortcut`, launcher button).
- `net-fix` / `net-verify`: restore and check the original network prefab hashes in the installed app.
- Progress in the launcher: a plain-language status line and a progress bar for builds, mod installs and launches (the kit prints `##status` / `##progress` / `##done` / `##fail` lines).
- README section on getting the Windows copy of the game (SteamCMD on the Mac, a Windows PC, or Steam in a wrapper).
- `mods delete-profile <name>` and a profile dropdown on Home that switches, adds and removes profiles.
- Download percentage for mod installs: the kit streams each mod with byte progress and the Mods tab shows the status and bar in its bottom bar.

### Changed
- The modded app starts through a small native launcher instead of a shell script, so Steam's overlay reaches the game and the last chosen profile is used.
- Home tab: a Vanilla / Mods switch with one Play button, a 2x2 status grid with short hints, and smaller, lighter buttons everywhere.

### Fixed
- Joining Windows hosts: the native build carried regenerated NetworkObject hashes, so Netcode rejected the client without a reason. Builds now restore the original hashes after the Unity build.

## [0.1.0] - 2026-10-25

### Added
- Launcher app with Build / Update, Play and Play modded; menu-driven, no setup beyond Steam and Unity Hub.
- Full build pipeline: Steam ownership check, asset extraction, Unity package restore, Metal shader build, install
  to Applications with the game's icon.
- macOS replacements for Windows-only parts: Steamworks compatibility layer, Opus and voice-capture plugins,
  Discord SDK, replacement full-screen effects.
- Mod support: BepInEx, a native Thunderstore mod manager with profile share codes, a per-mod compatibility audit,
  and the MacShaderFix runtime plugin that remaps mod materials to Metal shaders.
- Game update detection against Steam's public build.

### Known issues
- Water, grass, fur, hologram, blob shaders and the posterize effect are approximations.
- VFX Graph particle effects do not render.
- FixPluginTypesSerialization (used by LethalLib and LethalLevelLoader) does not work yet.
- Voice chat has no noise suppression or echo cancellation.
