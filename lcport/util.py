import os, sys, subprocess, hashlib, time, json, urllib.request, zipfile, tarfile, shutil
from . import config

class Step:
    """Context manager that prints a step banner and timing."""
    def __init__(self, name): self.name = name
    def __enter__(self):
        self.t = time.time(); log(f"==> {self.name}"); return self
    def __exit__(self, *a):
        log(f"    done in {time.time() - self.t:.0f}s")

def log(msg):
    print(msg, flush=True)

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
    return json.load(open(config.STATE)) if os.path.exists(config.STATE) else {}

def write_state(d):
    os.makedirs(config.SUPPORT, exist_ok=True); json.dump(d, open(config.STATE, "w"), indent=1)

def notify(title, text):
    subprocess.run(["osascript", "-e", f'display notification "{text}" with title "{title}"'], check=False)

def ask_folder(prompt):
    r = subprocess.run(["osascript", "-e", f'POSIX path of (choose folder with prompt "{prompt}")'], capture_output=True, text=True)
    return r.stdout.strip() or None

def dialog(text, buttons=("OK",), default=None, title="Lethal Company Port"):
    b = ", ".join(f'"{x}"' for x in buttons); d = f' default button "{default or buttons[-1]}"'
    r = subprocess.run(["osascript", "-e", f'display dialog "{text}" with title "{title}" buttons {{{b}}}{d}'], capture_output=True, text=True)
    return r.stdout.strip().replace("button returned:", "")
