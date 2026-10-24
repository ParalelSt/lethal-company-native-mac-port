#!/bin/zsh
# Maintainer script: rebuilds the prebuilt native shims. Needs Xcode CLT, brew opus, and the Facepunch release zips.
# Users never run this; the results are committed under prebuilt/.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; OUT="$HERE/../prebuilt"; TMP="$(mktemp -d)"
FP_UNI="${FP_UNI:?path to Facepunch.Steamworks 2.5.x Unity folder (redistributable_bin/osx/libsteam_api.dylib)}"
SDK="${SDK:?path to Facepunch 2.3.2 Generator/steam_sdk}"; mkdir -p "$TMP/include"; ln -s "$SDK" "$TMP/include/steam"
clang -O2 -arch arm64 -dynamiclib -fvisibility=hidden -I/opt/homebrew/opt/opus/include -o "$OUT/libopus.dylib" "$HERE/opus_shim.c" /opt/homebrew/opt/opus/lib/libopus.a -Wl,-install_name,@rpath/libopus.dylib -Wl,-exported_symbols_list,"$HERE/opus_exports.txt"
clang -O2 -arch arm64 -dynamiclib -fvisibility=hidden -o "$OUT/AudioPluginDissonance.bundle" "$HERE/audioplugin_dissonance_stub.c" -Wl,-install_name,@rpath/AudioPluginDissonance.bundle
cp "$FP_UNI/redistributable_bin/osx/libsteam_api.dylib" "$OUT/libsteam_api_real.dylib"; install_name_tool -id @loader_path/libsteam_api_real.dylib "$OUT/libsteam_api_real.dylib"
python3 "$HERE/gen_steam_flat.py" "$SDK" "$TMP/steam_flat.cpp"
cat >> "$TMP/steam_flat.cpp" <<'EOC'
extern "C" int SteamAPI_InitFlat(char *errmsg);
extern "C" bool SteamAPI_Init() { char m[1024]; return SteamAPI_InitFlat(m) == 0; }
ISteamGameSearch * SteamAPI_SteamGameSearch_v001() { return (ISteamGameSearch *)SteamInternal_FindOrCreateUserInterface(SteamAPI_GetHSteamUser(), "SteamMatchGameSearch001"); }
EOC
clang++ -std=c++11 -O2 -arch arm64 -dynamiclib -DSTEAM_API_EXPORTS -Wno-invalid-offsetof -I"$TMP/include" -I"$SDK" -o "$OUT/libsteam_api.dylib" "$TMP/steam_flat.cpp" -L"$OUT" -lsteam_api_real -Wl,-reexport-lsteam_api_real -Wl,-install_name,@loader_path/libsteam_api.dylib
for f in "$OUT"/*.dylib "$OUT"/*.bundle; do codesign --force --sign - "$f"; done
echo "prebuilt natives updated in $OUT"
