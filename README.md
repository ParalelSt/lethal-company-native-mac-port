# Lethal Company, native on macOS

Rebuilds Lethal Company as a native Apple-silicon macOS app (Metal, no Wine) from **your own Steam copy**.
Online play with Windows players, Steam presence, voice chat and BepInEx mods work. This repository contains
no game files: the launcher reads the Windows build you bought and produces the Mac app on your machine.

## What you need
1. **Steam** installed on the Mac and signed in to an account that owns Lethal Company (the launcher checks).
2. **Unity Hub** installed and signed in once (free Personal licence). The launcher installs the exact Unity editor the game needs (about 5 GB).
3. **Your Lethal Company folder** from a Windows Steam install. On the PC: Steam > Lethal Company > Manage > Browse local files, copy the whole `Lethal Company` folder to the Mac (USB stick, network share, anything).
4. About 25 GB of free disk during the build, 2 GB afterwards. The first build takes roughly an hour on an M1 Pro, mostly Unity compiling shaders.

## Use
- Download this repository (Code > Download ZIP, or `git clone`), unzip, then right-click **Lethal Company Port.app** > Open.
- Click **Build / Update** and pick your Lethal Company folder. Everything else is automatic.
- Afterwards **Lethal Company** and **Lethal Company Modded** are in your Applications folder and in Spotlight. Keep Steam running when you play.

Command line (same thing):
```
python3 -m lcport build "/path/to/Lethal Company"
python3 -m lcport play
python3 -m lcport mods import Default <thunderstore-profile-code>
python3 -m lcport mods audit Default
python3 -m lcport check-update
```

## Mods
`mods` is a small native Thunderstore mod manager using the r2modman profile layout (profile share codes work).
Every install prints an audit: mods that should work, mods whose Windows-only asset bundle shaders are remapped
at runtime by the bundled MacShaderFix plugin, and mods that need porting work (Windows native code).

## When the game updates
`check-update` compares Steam's public build with the one you built from. Update the Windows copy, copy the
folder again, run Build / Update.

## Known gaps
A few of the game's custom shaders (water, grass, fur, hologram, blob, the posterize screen effect) cannot be
recovered from a compiled build and are approximated; VFX Graph particle effects do not render; voice chat uses
a pass-through audio plugin (no noise suppression). Mods that ship Windows native libraries do not work.

## Legal
Tooling under the MIT licence (see LICENSE). Lethal Company is property of Zeekerss; this project is not affiliated.
You must own the game. Do not redistribute the built app. Third-party components are listed in THIRD_PARTY.md.
