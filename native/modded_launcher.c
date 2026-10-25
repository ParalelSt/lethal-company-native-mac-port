/* Main executable of "Lethal Company Modded.app" (and so the Exe of Steam's "Lethal Company (Modded)" shortcut).
 * Steam injects its overlay with DYLD_INSERT_LIBRARIES; macOS drops DYLD_* for protected binaries (/bin/zsh, python),
 * so this tiny unprotected program sets up the BepInEx env itself (like `lcport play-modded`) and execs the game.
 * Paths come from Contents/Resources/launcher.json (written by lcport/install.py). Env knobs: LC_PROFILE (profile name),
 * LC_NO_OVERLAY=1 (no Steam overlay when not started by Steam), LC_LAUNCHER_TEST=1 (tests: skip `defaults` and Steam start).
 * Errors go to <support>/work/modded-launcher.log. Build: native/build.sh. */
#include <errno.h>
#include <ftw.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <pwd.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define APPID "1966720"
#define BUNDLE_ID "com.ZeekerssRBLX.Lethal-Company"
#define OVERLAY_REL "/Library/Application Support/Steam/Steam.AppBundle/Steam/Contents/MacOS/gameoverlayrenderer.dylib"

static FILE *logf;

static void say(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt); vfprintf(stderr, fmt, ap); va_end(ap); fputc('\n', stderr);
    if (logf) { va_start(ap, fmt); vfprintf(logf, fmt, ap); va_end(ap); fputc('\n', logf); fflush(logf); }
}
#define die(...) do { say("modded launcher error: " __VA_ARGS__); exit(1); } while (0)

static char *read_file(const char *path) {
    FILE *f = fopen(path, "rb"); if (!f) return NULL;
    char *buf = NULL; size_t len = 0, cap = 0, n;
    do {
        if (len + 4096 + 1 > cap) { cap = (cap + 4096) * 2; char *nb = realloc(buf, cap); if (!nb) { free(buf); fclose(f); return NULL; } buf = nb; }
        n = fread(buf + len, 1, 4096, f); len += n;
    } while (n > 0);
    fclose(f); buf[len] = 0; return buf;
}

static void put_utf8(char **o, char *end, unsigned cp) {
    unsigned char b[4]; int n;
    if (cp < 0x80) { b[0] = cp; n = 1; }
    else if (cp < 0x800) { b[0] = 0xC0 | cp >> 6; b[1] = 0x80 | (cp & 0x3F); n = 2; }
    else if (cp < 0x10000) { b[0] = 0xE0 | cp >> 12; b[1] = 0x80 | (cp >> 6 & 0x3F); b[2] = 0x80 | (cp & 0x3F); n = 3; }
    else { b[0] = 0xF0 | cp >> 18; b[1] = 0x80 | (cp >> 12 & 0x3F); b[2] = 0x80 | (cp >> 6 & 0x3F); b[3] = 0x80 | (cp & 0x3F); n = 4; }
    for (int i = 0; i < n && *o < end; i++) *(*o)++ = b[i];
}

static int hex4(const char *s, unsigned *v) {
    *v = 0;
    for (int i = 0; i < 4; i++) {
        char c = s[i]; unsigned d;
        if (c >= '0' && c <= '9') d = c - '0'; else if (c >= 'a' && c <= 'f') d = c - 'a' + 10; else if (c >= 'A' && c <= 'F') d = c - 'A' + 10; else return 0;
        *v = *v << 4 | d;
    }
    return 1;
}

/* Tolerant lookup of a string value "key": "value" anywhere in a JSON text (no JSON library). 1 if found. */
static int json_str(const char *buf, const char *key, char *out, size_t size) {
    char pat[128]; snprintf(pat, sizeof pat, "\"%s\"", key);
    for (const char *p = buf ? strstr(buf, pat) : NULL; p; p = strstr(p + 1, pat)) {
        const char *s = p + strlen(pat);
        while (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r') s++;
        if (*s++ != ':') continue;
        while (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r') s++;
        if (*s++ != '"') continue;
        char *o = out, *end = out + size - 1;
        while (*s && *s != '"' && o < end) {
            if (*s != '\\') { *o++ = *s++; continue; }
            char c = *++s; s++;
            if (c == 'u') {
                unsigned cp, lo;
                if (!hex4(s, &cp)) break;
                s += 4;
                if (cp >= 0xD800 && cp < 0xDC00 && s[0] == '\\' && s[1] == 'u' && hex4(s + 2, &lo) && lo >= 0xDC00 && lo < 0xE000) { cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00); s += 6; }
                put_utf8(&o, end, cp);
            } else *o++ = c == 'n' ? '\n' : c == 't' ? '\t' : c == 'r' ? '\r' : c == 'b' ? '\b' : c == 'f' ? '\f' : c;
        }
        if (*s != '"') continue;  /* truncated or malformed: try the next occurrence */
        *o = 0; return 1;
    }
    return 0;
}

static int exists(const char *p) { struct stat st; return stat(p, &st) == 0; }
static void mkdirs(const char *path) {
    char tmp[PATH_MAX]; snprintf(tmp, sizeof tmp, "%s", path);
    for (char *p = tmp + 1; *p; p++) if (*p == '/') { *p = 0; mkdir(tmp, 0755); *p = '/'; }
    mkdir(tmp, 0755);
}
static int rm_entry(const char *p, const struct stat *st, int flag, struct FTW *ftw) { (void)st; (void)flag; (void)ftw; remove(p); return 0; }

int main(int argc, char **argv) {
    char exe[PATH_MAX], real[PATH_MAX], contents[PATH_MAX], path[PATH_MAX];
    char kit[PATH_MAX] = "", support[PATH_MAX] = "", app[PATH_MAX] = "", bepinex[PATH_MAX] = "", profile[512] = "";
    uint32_t sz = sizeof exe;
    const char *home = getenv("HOME");
    if (!home || !*home) { struct passwd *pw = getpwuid(getuid()); home = pw ? pw->pw_dir : "/"; }

    /* <bundle>/Contents/MacOS/<exe> -> <bundle>/Contents */
    if (_NSGetExecutablePath(exe, &sz) != 0 || !realpath(exe, real)) die("cannot resolve the launcher's own path");
    snprintf(contents, sizeof contents, "%s", real);
    for (int i = 0; i < 2; i++) { char *slash = strrchr(contents, '/'); if (slash) *slash = 0; }
    snprintf(path, sizeof path, "%s/Resources/launcher.json", contents);
    char *cfg = read_file(path);
    json_str(cfg, "kit", kit, sizeof kit);
    if (!json_str(cfg, "support", support, sizeof support)) snprintf(support, sizeof support, "%s/Library/Application Support/LethalCompanyMac", home);
    if (!json_str(cfg, "app", app, sizeof app)) snprintf(app, sizeof app, "%s/Applications/Lethal Company.app", home);
    if (!json_str(cfg, "bepinex", bepinex, sizeof bepinex)) snprintf(bepinex, sizeof bepinex, "%s/work/thirdparty/bepinex", support);
    free(cfg);

    char work[PATH_MAX], gamelog[PATH_MAX];
    snprintf(work, sizeof work, "%s/work", support); mkdirs(work);
    snprintf(path, sizeof path, "%s/modded-launcher.log", work); logf = fopen(path, "w");
    snprintf(gamelog, sizeof gamelog, "%s/player-modded.log", work);

    /* profile: LC_PROFILE, else the one last chosen in the launcher (state.json "modded_profile"), else Default */
    const char *envp = getenv("LC_PROFILE");
    if (envp && *envp) snprintf(profile, sizeof profile, "%s", envp);
    else {
        snprintf(path, sizeof path, "%s/state.json", support);
        char *st = read_file(path);
        if (!json_str(st, "modded_profile", profile, sizeof profile) || !*profile) snprintf(profile, sizeof profile, "Default");
        free(st);
    }

    char preloader[PATH_MAX], doorstop[PATH_MAX], game[PATH_MAX], overlay[PATH_MAX];
    snprintf(preloader, sizeof preloader, "%s/profiles/%s/BepInEx/core/BepInEx.Preloader.dll", support, profile);
    snprintf(doorstop, sizeof doorstop, "%s/libdoorstop.dylib", bepinex);
    snprintf(game, sizeof game, "%s/Contents/MacOS/Lethal Company", app);
    snprintf(overlay, sizeof overlay, "%s" OVERLAY_REL, home);
    int test = getenv("LC_LAUNCHER_TEST") && !strcmp(getenv("LC_LAUNCHER_TEST"), "1");
    int by_steam = getenv("SteamGameId") != NULL;  /* Steam sets it on what it starts */
    setenv("LC_DIRECT_LAUNCH", "1", 1);

    if (!exists(game)) die("the game is not built (missing %s). Open the Lethal Company Port launcher and build it.", game);
    if (!exists(preloader) || !exists(doorstop)) {
        /* first modded run: let the kit download BepInEx and create the profile (no overlay through Steam this once) */
        say("profile %s or BepInEx not set up yet (%s / %s); handing over to lcport play-modded", profile, preloader, doorstop);
        snprintf(path, sizeof path, "%s/venv/bin/python", support);
        if (*kit && exists(path) && chdir(kit) == 0) {
            char *pargv[] = {path, "-m", "lcport", "play-modded", profile, NULL};
            execv(path, pargv);
        }
        die("profile %s is not set up (missing %s or %s) and the kit could not be started (%s). Run: lcport play-modded %s",
            profile, preloader, doorstop, strerror(errno), profile);
    }

    /* same as install.reset_window_state(): no restored window frame from an older resolution */
    if (!test) system("defaults write " BUNDLE_ID " ApplePersistenceIgnoreState -bool true");
    snprintf(path, sizeof path, "%s/Library/Saved Application State/" BUNDLE_ID ".savedState", home);
    nftw(path, rm_entry, 16, FTW_DEPTH | FTW_PHYS);
    /* started from Finder: the game needs a running Steam client (what steam.ensure_running() does) */
    if (!by_steam && !test)
        system("pgrep -xq steam_osx || { open -ga Steam; i=0; while [ $i -lt 60 ] && ! pgrep -xq steam_osx; do sleep 1; i=$((i+1)); done; sleep 8; }");

    setenv("DOORSTOP_ENABLED", "1", 1);
    setenv("DOORSTOP_TARGET_ASSEMBLY", preloader, 1);
    setenv("DOORSTOP_IGNORE_DISABLED_ENV", "0", 1);
    /* Steam sets SteamAppId/SteamGameId/SteamOverlayGameId to the SHORTCUT's app id when it starts this bundle, but the
     * game must initialise the Steam API as Lethal Company, so SteamAppId is always overwritten. SteamGameId and
     * SteamOverlayGameId stay as Steam set them (overlay/playtime keep the shortcut) and are only filled in when absent. */
    setenv("SteamAppId", APPID, 1); setenv("SteamGameId", APPID, 0); setenv("SteamOverlayGameId", APPID, 0);
    /* keep what Steam injected (its gameoverlayrenderer.dylib); started without it, add the overlay like steam.launch() */
    const char *dyld = getenv("DYLD_INSERT_LIBRARIES");
    const char *no_overlay = getenv("LC_NO_OVERLAY");
    size_t dlen = strlen(doorstop) + (dyld ? strlen(dyld) : 0) + strlen(overlay) + 2;
    char *ins = malloc(dlen);
    if (!ins) die("out of memory");
    if (dyld && *dyld) snprintf(ins, dlen, "%s:%s", doorstop, dyld);
    else if (exists(overlay) && !(no_overlay && !strcmp(no_overlay, "1"))) snprintf(ins, dlen, "%s:%s", doorstop, overlay);
    else snprintf(ins, dlen, "%s", doorstop);
    setenv("DYLD_INSERT_LIBRARIES", ins, 1);

    char **gargv = calloc(argc + 4, sizeof *gargv);
    if (!gargv) die("out of memory");
    int n = 0;
    gargv[n++] = game; gargv[n++] = "-logFile"; gargv[n++] = gamelog;
    for (int i = 1; i < argc; i++) if (strncmp(argv[i], "-psn_", 5) != 0) gargv[n++] = argv[i];
    say("launching %s with profile %s (started by %s), DYLD_INSERT_LIBRARIES=%s", game, profile, by_steam ? "Steam" : "Finder", ins);
    if (logf) { fclose(logf); logf = NULL; }
    execv(game, gargv);
    snprintf(path, sizeof path, "%s/modded-launcher.log", work); logf = fopen(path, "a");
    die("could not start %s: %s", game, strerror(errno));
}
