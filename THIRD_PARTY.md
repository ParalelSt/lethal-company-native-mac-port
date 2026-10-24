# Third-party components

Shipped in `prebuilt/` (built by `native/build.sh`, sources in `native/` and `tools/`):
- libopus (BSD-3) statically linked into `libopus.dylib` together with this project's Dissonance ctl wrappers.
- `libsteam_api_real.dylib`: Valve Steamworks redistributable from the Facepunch.Steamworks 2.5.x release (MIT repository; Valve Steamworks SDK terms apply). `libsteam_api.dylib` is this project's SDK-1.49 compatibility layer generated from the Steamworks SDK header snapshot in the Facepunch.Steamworks repository.
- `Facepunch.Steamworks.Posix.dll` (+meta) and the `Facepunch.Steamworks.Win64.dll` type-forwarding facade: Facepunch.Steamworks 2.3.2, MIT.
- `MacShaderFix.dll`: this project (MIT), built against BepInEx 5 (LGPL-2.1) and Unity assemblies.
- `AudioPluginDissonance.bundle`: this project's stand-in for the Dissonance Voice native plugin (not included).

Downloaded at build or first use (not stored in this repository):
- AssetRipper (GPL-3.0) run as a separate process. BepInEx and UnityDoorstop (LGPL-2.1). Discord Game SDK (Discord terms).
- Unity packages from Unity's package registry and the editor you install (Unity terms). Thunderstore mods (their own licences).

Python packages installed into a private virtual environment: UnityPy, dnfile, pefile, Pillow, vdf.
