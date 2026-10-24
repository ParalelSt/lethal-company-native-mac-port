"""Public third-party downloads used at build time. No compiler or .NET needed: shims and helpers ship prebuilt."""
import os, shutil
from . import config
from .util import run, download, extract

TP = os.path.join(config.WORK, "thirdparty")
PREBUILT = os.path.join(config.KIT, "prebuilt")

def assetripper():
    d = os.path.join(TP, "assetripper"); exe = os.path.join(d, "AssetRipper.GUI.Free")
    if not os.path.exists(exe):
        extract(download(f"https://github.com/AssetRipper/AssetRipper/releases/download/{config.ASSETRIPPER_TAG}/AssetRipper_mac_arm64.tar.xz"), d)
        run(["xattr", "-dr", "com.apple.quarantine", d], check=False)
        os.chmod(exe, 0o755)
    return exe

def bepinex():
    d = os.path.join(TP, "bepinex")
    if not os.path.exists(os.path.join(d, "libdoorstop.dylib")):
        extract(download(f"https://github.com/BepInEx/BepInEx/releases/download/v{config.BEPINEX_TAG}/BepInEx_macos_universal_{config.BEPINEX_TAG}.zip"), d)
        run(["xattr", "-dr", "com.apple.quarantine", d], check=False)
    return d

def discord_sdk():
    d = os.path.join(TP, "discord"); dylib = os.path.join(d, "lib", "aarch64", "discord_game_sdk.dylib")
    if not os.path.exists(dylib):
        extract(download(f"https://dl-game-sdk.discordapp.net/{config.DISCORD_SDK}/discord_game_sdk.zip"), d)
    return dylib

def natives():
    """Mac native plugins for the Unity project: prebuilt shims + downloaded Discord SDK."""
    d = os.path.join(config.WORK, "natives"); os.makedirs(d, exist_ok=True)
    for f in ("libsteam_api.dylib", "libsteam_api_real.dylib", "libopus.dylib", "AudioPluginDissonance.bundle"):
        shutil.copy2(os.path.join(PREBUILT, f), os.path.join(d, f))
    shutil.copy2(discord_sdk(), os.path.join(d, "discord_game_sdk.dylib"))
    return d

def unity_package(name, version):
    """Download a Unity registry package tarball (for script GUIDs) and return its extracted dir."""
    d = os.path.join(TP, "packages", f"{name}@{version}")
    if os.path.isdir(os.path.join(d, "package.json")) or os.path.exists(os.path.join(d, "package.json")): return d
    from .util import http_json
    meta = http_json(f"https://packages.unity.com/{name}")
    url = meta["versions"][version]["dist"]["tarball"]
    extract(download(url, f"{name}-{version}.tgz"), d, strip=1)
    return d
