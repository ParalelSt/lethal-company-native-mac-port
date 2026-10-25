# Lethal Company for macOS

Builds a native Apple-silicon version of Lethal Company from the copy you own on Steam. No Wine. Online play with
Windows players, Steam presence, voice chat and BepInEx mods all work.

The repository contains **no game files**. You bring the game; the launcher turns it into a Mac app on your machine.

## You need
- A Mac with Apple silicon and about 25 GB free during the build.
- Steam installed and signed in to an account that owns Lethal Company (the launcher checks).
- Unity Hub installed and signed in once (free Personal licence). The launcher installs the exact editor version itself.
- The `Lethal Company` folder from a Windows Steam install, copied to the Mac (see Getting the Windows copy below).

## Do
1. Download the latest launcher zip from the Releases page and unzip it (the launcher offers updates by itself afterwards).
2. Right-click `Lethal Company Port.app` > Open, then click **Build / Update** and choose your `Lethal Company` folder.
3. Wait (about an hour the first time, mostly shader compilation). Then launch **Lethal Company** from Spotlight. Keep Steam running.

Press Add to Steam once; after that Play starts the game through Steam so the Steam overlay works.

## Getting the Windows copy
The launcher needs the Windows version of Lethal Company from Steam, because there is no Mac version to download. You
must own the game on the Steam account you use. Three ways, best first.

**1. SteamCMD on the Mac (no Windows, no Wine)**
1. Install Valve's command line Steam: `brew install --cask steamcmd` (if the cask name differs on your machine, run
   `brew search steamcmd`).
2. Run `steamcmd +@sSteamCmdForcePlatformType windows +login YOUR_STEAM_NAME +app_update 1966720 validate +quit`.
   It asks for your password and Steam Guard code once.
3. The game lands in `~/Library/Application Support/Steam/steamapps/common/Lethal Company`, or under SteamCMD's own
   folder, which is its default on macOS. The exact folder is printed at the end of the download. Pick the folder that
   contains `Lethal Company.exe` in the launcher.

(We have not verified this path on every Mac.)

**2. A Windows PC with Steam**
1. Install the game there, right-click it in Steam, Manage, Browse local files.
2. Copy the whole `Lethal Company` folder to the Mac (USB stick, AirDrop, or a shared folder).
3. Pick that folder in the launcher.

**3. Steam for Windows inside a wrapper on the Mac (Porting Kit, Whisky or CrossOver)**
1. Install the Windows Steam client in the wrapper and download the game there.
2. Pick the folder inside the wrapper. For Porting Kit it looks like
   `~/Applications/<wrapper name>.app/Contents/SharedSupport/prefix/drive_c/Program Files (x86)/Steam/steamapps/common/Lethal Company`.

The launcher only reads that folder; it never changes it. You can delete it after the build if you want the space back
(the build keeps what it needs in `~/Library/Application Support/LethalCompanyMac`).

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
The launcher's Mods tab browses Thunderstore, installs and removes mods with one click, shows which ones work on the Mac, and keeps profiles. The same from a terminal: `python3 -m lcport mods import <profile> <thunderstore-profile-code>` installs a mod list; `mods install`, `mods search`,
`mods update` and `mods audit` also exist. Profiles use the same layout as r2modman. Every install prints an audit:
mods that work as-is, mods whose Windows-only bundle shaders are remapped automatically at runtime, and mods that need
porting work. Launch with **Lethal Company Modded**.

## Updates
The launcher checks for a newer launcher release on start; each release lists what was added, changed and removed (see CHANGELOG.md).
`python3 -m lcport check-update` compares Steam's public build with the one you built from. When the game updates,
copy the new Windows folder over and run Build / Update again.

## Known gaps
Five custom shaders (water, grass, fur, hologram, blob) and the posterize screen effect are approximations; VFX Graph
particle effects do not render; voice chat uses a pass-through audio plugin without noise suppression. Mods that ship
Windows native code do not work.

## Legal
Tooling is MIT-licensed (LICENSE). Lethal Company belongs to Zeekerss; this project is not affiliated. You must own the
game and must not redistribute the built app. See THIRD_PARTY.md for bundled and downloaded components.
