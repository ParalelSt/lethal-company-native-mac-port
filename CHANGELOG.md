# Changelog

All notable changes to the launcher and build kit. Each GitHub release uses the matching section as its notes.
Format: [Keep a Changelog](https://keepachangelog.com). Versions follow the launcher, not the game.

## [Unreleased]

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
