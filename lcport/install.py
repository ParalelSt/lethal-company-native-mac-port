"""Install the built app into ~/Applications with the game's icon, plus the modded launcher."""
import os, shutil, struct, io, glob, subprocess
from . import config, thirdparty
from .util import run, log, Step

def extract_icon(game_dir, out_png):
    import pefile
    from PIL import Image
    exe = glob.glob(os.path.join(game_dir, "*.exe"))
    exe = [e for e in exe if not os.path.basename(e).startswith("UnityCrashHandler")]
    if not exe: return False
    pe = pefile.PE(exe[0])
    def entries(rtype):
        for e in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if e.id == rtype:
                for name in e.directory.entries:
                    for lang in name.directory.entries:
                        d = lang.data.struct; yield name.id, pe.get_data(d.OffsetToData, d.Size)
    icons = dict(entries(3)); best = None
    for gid, g in entries(14):
        n = struct.unpack_from("<H", g, 4)[0]
        for i in range(n):
            w, h, cc, r, planes, bpp, size, iid = struct.unpack_from("<BBBBHHIH", g, 6 + i * 14)
            w = w or 256; h = h or 256
            if best is None or w * h > best[0]: best = (w * h, w, h, bpp, iid)
    if not best: return False
    _, w, h, bpp, iid = best; data = icons[iid]
    if data[:8] == b"\x89PNG\r\n\x1a\n": img = Image.open(io.BytesIO(data))
    else:
        ico = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, bpp, len(data), 22) + data
        img = Image.open(io.BytesIO(ico))
    img.convert("RGBA").save(out_png); return True

def make_icns(png, icns):
    tmp = os.path.join(config.WORK, "icon.iconset"); shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    for s in (16, 32, 128, 256, 512):
        run(["sips", "-z", str(s), str(s), png, "--out", os.path.join(tmp, f"icon_{s}x{s}.png")], capture=True)
        run(["sips", "-z", str(s * 2), str(s * 2), png, "--out", os.path.join(tmp, f"icon_{s}x{s}@2x.png")], capture=True)
    run(["iconutil", "-c", "icns", tmp, "-o", icns])

def reset_window_state():
    subprocess.run(["defaults", "write", config.BUNDLE_ID, "ApplePersistenceIgnoreState", "-bool", "true"], check=False)
    shutil.rmtree(os.path.expanduser(f"~/Library/Saved Application State/{config.BUNDLE_ID}.savedState"), ignore_errors=True)

def install_app(built_app, game_dir):
    with Step(f"install {config.APP_DST}"):
        if os.path.exists(config.APP_DST): shutil.rmtree(config.APP_DST)
        shutil.copytree(built_app, config.APP_DST, symlinks=True)
        png = os.path.join(config.WORK, "icon.png")
        try:
            if extract_icon(game_dir, png): make_icns(png, os.path.join(config.APP_DST, "Contents", "Resources", "PlayerIcon.icns"))
        except Exception as e: log(f"    icon skipped: {e}")
        open(os.path.join(config.APP_DST, "Contents", "MacOS", "steam_appid.txt"), "w").write(str(config.APPID))
        reset_window_state()
        run(["xattr", "-dr", "com.apple.quarantine", config.APP_DST], check=False, capture=True)
        run(["codesign", "--force", "--deep", "--sign", "-", config.APP_DST], capture=True)
        run(["/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister", "-f", config.APP_DST], check=False, capture=True)

def install_modded_launcher():
    with Step(f"install {config.MODDED_DST}"):
        a = config.MODDED_DST; shutil.rmtree(a, ignore_errors=True)
        os.makedirs(os.path.join(a, "Contents", "MacOS")); os.makedirs(os.path.join(a, "Contents", "Resources"))
        py = os.path.join(config.SUPPORT, "venv", "bin", "python")
        open(os.path.join(a, "Contents", "MacOS", "launch"), "w").write(f'#!/bin/zsh\ncd "{config.KIT}" && exec "{py}" -m lcport play-modded "${{LC_PROFILE:-Default}}"\n')
        os.chmod(os.path.join(a, "Contents", "MacOS", "launch"), 0o755)
        icns = os.path.join(config.APP_DST, "Contents", "Resources", "PlayerIcon.icns")
        if os.path.exists(icns): shutil.copy2(icns, os.path.join(a, "Contents", "Resources", "PlayerIcon.icns"))
        open(os.path.join(a, "Contents", "Info.plist"), "w").write(f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>{config.APP_NAME} Modded</string>
  <key>CFBundleDisplayName</key><string>{config.APP_NAME} Modded</string>
  <key>CFBundleIdentifier</key><string>com.lethalcompanymac.modded</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>CFBundleIconFile</key><string>PlayerIcon.icns</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSMicrophoneUsageDescription</key><string>Lethal Company uses the microphone for in-game voice chat.</string>
</dict></plist>''')
        run(["codesign", "--force", "--deep", "--sign", "-", a], capture=True)
        run(["/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister", "-f", a], check=False, capture=True)
