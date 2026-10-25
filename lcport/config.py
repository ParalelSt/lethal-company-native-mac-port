import os
APPID = 1966720
REPO = "ParalelSt/lethal-company-native-mac-port"      # GitHub repository used for launcher self-updates and releases
KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUPPORT = os.path.expanduser("~/Library/Application Support/LethalCompanyMac")
WORK = os.path.join(SUPPORT, "work")          # rip output, Unity project, downloads
CACHE = os.path.join(SUPPORT, "cache")        # downloaded archives
PROFILES = os.path.join(SUPPORT, "profiles")  # mod profiles
APP_NAME = "Lethal Company"
APP_DST = os.path.expanduser(f"~/Applications/{APP_NAME}.app")
MODDED_DST = os.path.expanduser(f"~/Applications/{APP_NAME} Modded.app")
BUNDLE_ID = "com.ZeekerssRBLX.Lethal-Company"
STATE = os.path.join(SUPPORT, "state.json")

# third-party components fetched at build time (all public downloads)
FACEPUNCH_TAG = "2.3.2"      # version the game ships (verified by md5 of its Facepunch.Steamworks.Win64.dll)
FACEPUNCH_UNIVERSAL_TAG = "2.5.2"  # provides a universal (x86_64+arm64) libsteam_api.dylib
ASSETRIPPER_TAG = "2.0.0"
BEPINEX_TAG = "5.4.23.6"
DISCORD_SDK = "3.2.1"
UNITY_VERSION = "2022.3.62f2"   # the game's Unity version; setup and check-unity use it until a build records the real one
UNITY_EDITORS = "/Applications/Unity/Hub/Editor"
