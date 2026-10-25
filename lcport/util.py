import os, re, sys, subprocess, hashlib, time, json, urllib.request, zipfile, tarfile, shutil, contextlib
from . import config

def log(msg):
    print(msg, flush=True)

# Control lines for the native launcher. It reads them from stdout, drives its status label and progress bar with
# them and leaves them out of the log: "##status <text>", "##progress <0-100>", "##done <text>", "##fail <text>".
def status(text): log(f"##status {text}")
def progress(pct): log(f"##progress {max(0, min(100, int(round(pct))))}")
def done(text): log(f"##done {text}")
def fail(text): log(f"##fail {text}")

_scope = None  # active progress_steps scope: {"total": n, "index": i, "depth": nesting of open Steps}

@contextlib.contextmanager
def progress_steps(total):
    """Number the top-level Steps inside the block: each prints "##status <title> (i/total)" and "##progress" lines.
    Nested scopes (full_build inside cmd_build) join the outer one, whose total already counts their steps."""
    global _scope
    if _scope is not None: yield; return
    _scope = {"total": max(1, total), "index": 0, "depth": 0}
    try: yield
    finally: _scope = None

def human(name):
    """Step title for people: no trailing "(...)" aside, first letter upper case."""
    t = re.sub(r"\s*\([^()]*\)$", "", name).strip() or name
    return t[:1].upper() + t[1:]

class Step:
    """Context manager that prints a step banner and timing, plus "##status" (and, inside progress_steps, "##progress")."""
    def __init__(self, name, status=None): self.name = name; self.title = status or human(name); self.top = False
    def __enter__(self):
        self.t = time.time(); log(f"==> {self.name}")
        sc = _scope
        if sc is None: status(self.title); return self
        self.top = sc["depth"] == 0; sc["depth"] += 1
        if self.top: sc["index"] += 1
        status(f"{self.title} ({min(sc['index'], sc['total'])}/{sc['total']})")
        if self.top: progress((sc["index"] - 1) * 100 / sc["total"])
        return self
    def __exit__(self, *a):
        log(f"    done in {time.time() - self.t:.0f}s")
        sc = _scope
        if sc is None: return
        sc["depth"] = max(0, sc["depth"] - 1)
        if self.top and a[0] is None: progress(sc["index"] * 100 / sc["total"])

def run(cmd, cwd=None, env=None, check=True, capture=False, timeout=None):
    e = dict(os.environ); e.update(env or {})
    r = subprocess.run(cmd, cwd=cwd, env=e, text=True, capture_output=capture, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"command failed ({r.returncode}): {' '.join(str(c) for c in cmd)}\n{(r.stderr or '')[-2000:] if capture else ''}")
    return r

def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

def download(url, name=None, force=False):
    os.makedirs(config.CACHE, exist_ok=True)
    name = name or url.rsplit("/", 1)[-1]
    p = os.path.join(config.CACHE, name)
    if os.path.exists(p) and not force: return p
    log(f"    downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "lcport"})
    with urllib.request.urlopen(req, timeout=120) as r, open(p + ".part", "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(p + ".part", p); return p

def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "lcport"})
    with urllib.request.urlopen(req, timeout=60) as r: return json.load(r)

def extract(archive, dest, strip=0):
    os.makedirs(dest, exist_ok=True)
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as z: z.extractall(dest)
    elif archive.endswith((".tgz", ".tar.gz", ".tar.xz")):
        with tarfile.open(archive) as t:
            if strip == 0: t.extractall(dest)
            else:
                for m in t.getmembers():
                    parts = m.name.split("/")[strip:]
                    if not parts: continue
                    m.name = "/".join(parts); t.extract(m, dest)
    else: raise ValueError(archive)
    return dest

def read_state():
    if not os.path.exists(config.STATE): return {}
    with open(config.STATE) as f: return json.load(f)

def write_state(d):
    os.makedirs(config.SUPPORT, exist_ok=True)
    with open(config.STATE, "w") as f: json.dump(d, f, indent=1)

def notify(title, text):
    subprocess.run(["osascript", "-e", f'display notification "{text}" with title "{title}"'], check=False)

def ask_folder(prompt):
    r = subprocess.run(["osascript", "-e", f'POSIX path of (choose folder with prompt "{prompt}")'], capture_output=True, text=True)
    return r.stdout.strip() or None

def dialog(text, buttons=("OK",), default=None, title="Lethal Company Port"):
    b = ", ".join(f'"{x}"' for x in buttons); d = f' default button "{default or buttons[-1]}"'
    r = subprocess.run(["osascript", "-e", f'display dialog "{text}" with title "{title}" buttons {{{b}}}{d}'], capture_output=True, text=True)
    return r.stdout.strip().replace("button returned:", "")
