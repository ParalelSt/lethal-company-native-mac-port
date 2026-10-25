# Lethal Company for macOS

Builds a native Apple-silicon version of Lethal Company from the copy you own on Steam. No Wine. Online play with
Windows players, Steam presence, voice chat and BepInEx mods all work.

The repository contains **no game files**. You bring the game; the launcher turns it into a Mac app on your machine.

## You need
- A Mac with Apple silicon and about 25 GB free during the build.
- Steam installed and signed in to an account that owns Lethal Company (the launcher checks).
- Unity Hub installed and signed in once (free Personal licence). The launcher installs the exact editor version itself.
- The `Lethal Company` folder from a Windows Steam install (Steam > Lethal Company > Manage > Browse local files), copied to the Mac.

## Do
1. Download this repository and unzip it.
2. Right-click `Lethal Company Port.app` > Open, then click **Build / Update** and choose your `Lethal Company` folder.
3. Wait (about an hour the first time, mostly shader compilation). Then launch **Lethal Company** from Spotlight. Keep Steam running.

Same thing from a terminal: `python3 -m lcport build "/path/to/Lethal Company"`, then `python3 -m lcport play`.

## What happens during a build
1. Steam confirms the signed-in account owns the game.
2. AssetRipper extracts the game's scenes, assets and code into a Unity project.
3. Windows-only pieces are replaced: Unity packages are restored from the real registry, Steamworks gets a Mac
   compatibility layer, voice and Opus audio get Mac plugins, and a few effects whose shader sources do not survive a
   compiled build get hand-written replacements.
4. Unity compiles every shader for Metal and builds the app.
5. The game's original code assemblies are placed back into the app so mods see exactly the code they were written for.
6. The app is installed into Applications with the game's icon, together with a **Lethal Company Modded** launcher.

## Mods
`python3 -m lcport mods import <profile> <thunderstore-profile-code>` installs a mod list; `mods install`, `mods search`,
`mods update` and `mods audit` also exist. Profiles use the same layout as r2modman. Every install prints an audit:
mods that work as-is, mods whose Windows-only bundle shaders are remapped automatically at runtime, and mods that need
porting work. Launch with **Lethal Company Modded**.

## Updates
`python3 -m lcport check-update` compares Steam's public build with the one you built from. When the game updates,
copy the new Windows folder over and run Build / Update again.

## Known gaps
Five custom shaders (water, grass, fur, hologram, blob) and the posterize screen effect are approximations; VFX Graph
particle effects do not render; voice chat uses a pass-through audio plugin without noise suppression. Mods that ship
Windows native code do not work.

## Legal
Tooling is MIT-licensed (LICENSE). Lethal Company belongs to Zeekerss; this project is not affiliated. You must own the
game and must not redistribute the built app. See THIRD_PARTY.md for bundled and downloaded components.
