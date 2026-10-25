"""Small dependency-free Markdown to HTML converter for mod READMEs and changelogs shown in the launcher.

Covers what Thunderstore READMEs use: ATX and setext headings, paragraphs, hard line breaks, **bold**, *italics*,
~~strike~~, `inline code`, fenced and indented code blocks, nested unordered / ordered lists (task boxes too),
[links](url), reference links, <autolinks>, bare URLs, ![images](url), blockquotes, horizontal rules and pipe tables.

Raw HTML: <br>, <img> and <a> are kept with their safe attributes only (http(s) / mailto / #anchor links, http(s) and
data:image sources; http images are upgraded to https). Tags that could run code or load content (script, style,
iframe, ...) are escaped so they show as text; every other tag is dropped and its text kept. Everything else is escaped.
"""
import html, re

_ESCAPED_TAGS = {"script", "style", "iframe", "frame", "frameset", "object", "embed", "applet", "form", "input", "button", "textarea",
                 "select", "option", "meta", "link", "base", "svg", "math", "noscript", "template", "audio", "video", "source", "canvas"}
_PH = re.compile(r"\x00(\d+)\x00")
_ENTITY = re.compile(r"&(#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);")


def esc(s):
    """Escape text for HTML, keeping character references such as &nbsp; and &#169; that READMEs write on purpose."""
    out, last = [], 0
    for m in _ENTITY.finditer(s):
        out.append(html.escape(s[last:m.start()], quote=True)); out.append(m.group(0)); last = m.end()
    out.append(html.escape(s[last:], quote=True)); return "".join(out)


def safe_url(url, image=False):
    u = html.unescape(url.strip()).replace(" ", "%20")
    low = u.lower()
    if image:
        if low.startswith("http://"): u = "https://" + u[7:]; low = u.lower()
        return u if low.startswith("https://") or low.startswith("data:image/") else None
    return u if low.startswith(("http://", "https://", "mailto:", "#")) else None


def _attrs(s):
    return {k.lower(): (v1 if v1 is not None else v2 if v2 is not None else v3)
            for k, v1, v2, v3 in re.findall(r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""", s)}


def img_tag(src, alt="", width=None):
    u = safe_url(src, image=True)
    if not u: return esc(alt)
    w = f' width="{esc(width)}"' if width and re.fullmatch(r"\d{1,4}%?", width) else ""
    return f'<img src="{esc(u)}" alt="{esc(alt)}"{w}>'


class _Inline:
    """Inline pass. Finished HTML pieces are parked as \\x00N\\x00 placeholders so later steps never touch them."""
    def __init__(self, refs): self.refs = refs; self.stash = []

    def keep(self, h): self.stash.append(h); return f"\x00{len(self.stash) - 1}\x00"

    def raw_tag(self, m):
        close, name, rest = m.group(1), m.group(2).lower(), m.group(3)
        if name == "br": return self.keep("<br>")
        if name == "img":
            a = _attrs(rest); return self.keep(img_tag(a.get("src", ""), a.get("alt", ""), a.get("width"))) if not close else ""
        if name == "a":
            if close: return self.keep("</a>")
            u = safe_url(_attrs(rest).get("href", "")); return self.keep(f'<a href="{esc(u)}">' if u else "<a>")
        if name in _ESCAPED_TAGS: return m.group(0)  # left in the text, so the escape step shows it literally
        return ""

    def link(self, text, url):
        u = safe_url(url); inner = self.finish(text)
        return self.keep(f'<a href="{esc(u)}">{inner}</a>' if u else inner)

    def image(self, alt, url): return self.keep(img_tag(url, alt))

    def ref(self, m, image):
        label = (m.group(2) or m.group(1)).strip().lower(); url = self.refs.get(label)
        if url is None: return m.group(0)
        return self.image(m.group(1), url) if image else self.link(m.group(1), url)

    def run(self, s):
        s = re.sub(r"(`+)(.+?)\1", lambda m: self.keep(f"<code>{esc(m.group(2).strip())}</code>"), s, flags=re.S)
        s = re.sub(r"<((?:https?://|mailto:)[^>\s]+)>", lambda m: self.link(m.group(1), m.group(1)), s)
        s = re.sub(r"<(/?)([A-Za-z][A-Za-z0-9]*)\b((?:[^>\"']|\"[^\"]*\"|'[^']*')*)/?>", self.raw_tag, s)
        target = r"\(\s*<?([^)\s>]*)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
        s = re.sub(r"!\[([^\]]*)\]" + target, lambda m: self.image(m.group(1), m.group(2)), s)
        s = re.sub(r"!\[([^\]]*)\]\[([^\]]*)\]", lambda m: self.ref(m, True), s)
        s = re.sub(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]" + target, lambda m: self.link(m.group(1), m.group(2)), s)
        s = re.sub(r"\[([^\]]+)\]\[([^\]]*)\]", lambda m: self.ref(m, False), s)
        return self.finish(s)

    def finish(self, s):
        """Escape what is left, then emphasis, bare URLs and hard breaks; finally put the parked pieces back."""
        s = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>~])", lambda m: self.keep(esc(m.group(1))), s)  # backslash escapes
        s = re.sub(r"(?<![\w/=\"'])(https?://[^\s<>\"'\x00]*[^\s<>\"'\x00.,:;!?)\]])", lambda m: self.keep(f'<a href="{esc(m.group(1))}">{esc(m.group(1))}</a>'), s)
        s = esc(s)
        s = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", s, flags=re.S)
        s = re.sub(r"(?<![\w])__(?=\S)(.+?)(?<=\S)__(?![\w])", r"<strong>\1</strong>", s, flags=re.S)
        s = re.sub(r"(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])", r"<em>\1</em>", s, flags=re.S)
        s = re.sub(r"(?<![\w])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w])", r"<em>\1</em>", s, flags=re.S)
        s = re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"<del>\1</del>", s, flags=re.S)
        s = re.sub(r"(?: {2,}|\\)\n", "<br>\n", s)
        while _PH.search(s): s = _PH.sub(lambda m: self.stash[int(m.group(1))], s)
        return s


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([^`\s]*)[^`]*$")
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
_HR = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_ITEM = re.compile(r"^( {0,12})([-*+]|\d{1,9}[.)])([ \t]+|$)(.*)$")
_QUOTE = re.compile(r"^ {0,3}> ?(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")
_REFDEF = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*<?(\S+?)>?(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*$")


def _cells(row):
    row = row.strip()
    if row.startswith("|"): row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"): row = row[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row)]


def _is_table(line, nxt): return "|" in line and nxt is not None and "|" in nxt and "-" in nxt and bool(_TABLE_SEP.match(nxt))


def _starts_block(line, nxt=None):
    return bool(_FENCE.match(line) or _HEADING.match(line) or _HR.match(line) or _QUOTE.match(line) or _ITEM.match(line)
                or _is_table(line, nxt))


def _blocks(lines, refs):
    out, i, para = [], 0, []
    inl = lambda s: _Inline(refs).run(s)
    def flush():
        if para:
            h = inl("\n".join(l.lstrip() for l in para).strip())
            if h.strip(): out.append(f"<p>{h}</p>")
            para.clear()
    while i < len(lines):
        line = lines[i]; nxt = lines[i + 1] if i + 1 < len(lines) else None
        if not line.strip(): flush(); i += 1; continue
        m = _FENCE.match(line)
        if m:
            flush(); fence = m.group(1); lang = re.sub(r"[^A-Za-z0-9_+-]", "", m.group(2)); body = []; i += 1
            while i < len(lines) and not re.match(r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$", lines[i]): body.append(lines[i]); i += 1
            i += 1
            cls = f' class="language-{lang}"' if lang else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(body))}</code></pre>"); continue
        if not para and line.startswith(("    ", "\t")) and not _ITEM.match(line):
            body = []
            while i < len(lines) and (lines[i].startswith(("    ", "\t")) or not lines[i].strip()):
                body.append(lines[i][4:] if lines[i].startswith("    ") else lines[i][1:]); i += 1
            while body and not body[-1].strip(): body.pop()
            out.append(f"<pre><code>{html.escape(chr(10).join(body))}</code></pre>"); continue
        if para and re.match(r"^ {0,3}(=+|-+)\s*$", line):  # setext heading underline
            lvl = 1 if line.strip()[0] == "=" else 2; text = inl(" ".join(l.strip() for l in para)); para.clear()
            out.append(f"<h{lvl}>{text}</h{lvl}>"); i += 1; continue
        m = _HEADING.match(line)
        if m:
            flush(); lvl = len(m.group(1)); out.append(f"<h{lvl}>{inl((m.group(2) or '').strip())}</h{lvl}>"); i += 1; continue
        if _HR.match(line): flush(); out.append("<hr>"); i += 1; continue
        if _QUOTE.match(line):
            flush(); body = []
            while i < len(lines) and lines[i].strip() and (_QUOTE.match(lines[i]) or not _starts_block(lines[i])):
                q = _QUOTE.match(lines[i]); body.append(q.group(1) if q else lines[i]); i += 1
            out.append(f"<blockquote>{_blocks(body, refs)}</blockquote>"); continue
        if _is_table(line, nxt):
            flush(); head = _cells(line); aligns = []
            for c in _cells(nxt):
                aligns.append("center" if c.startswith(":") and c.endswith(":") else "right" if c.endswith(":") else "left" if c.startswith(":") else "")
            i += 2; rows = []
            while i < len(lines) and lines[i].strip() and "|" in lines[i]: rows.append(_cells(lines[i])); i += 1
            def row(cells, tag):
                tds = []
                for k in range(len(head)):
                    a = aligns[k] if k < len(aligns) else ""; st = f' style="text-align:{a}"' if a else ""
                    tds.append(f"<{tag}{st}>{inl(cells[k]) if k < len(cells) else ''}</{tag}>")
                return "<tr>" + "".join(tds) + "</tr>"
            body = "".join(row(r, "td") for r in rows)
            out.append(f"<table><thead>{row(head, 'th')}</thead>" + (f"<tbody>{body}</tbody>" if body else "") + "</table>"); continue
        m = _ITEM.match(line)
        if m and (not para or m.group(2)[0] in "-*+" or m.group(2)[:-1] == "1"):
            flush(); i = _list(lines, i, refs, out); continue
        if not para and _REFDEF.match(line): i += 1; continue  # definitions were collected up front
        para.append(line); i += 1
    flush()
    return "\n".join(out)


def _list(lines, i, refs, out):
    """One list starting at lines[i]; nested lists and continuation paragraphs are parsed recursively. Returns the next index."""
    first = _ITEM.match(lines[i]); base = len(first.group(1)); ordered = first.group(2)[0].isdigit()
    items, loose = [], False
    while i < len(lines):
        m = _ITEM.match(lines[i])
        if not m or len(m.group(1)) != base or m.group(2)[0].isdigit() != ordered: break
        width = len(m.group(1)) + len(m.group(2)) + max(1, min(len(m.group(3)), 4)); body = [m.group(4)]; i += 1
        while i < len(lines):
            l = lines[i]
            if not l.strip():
                j = i
                while j < len(lines) and not lines[j].strip(): j += 1
                if j < len(lines) and (len(lines[j]) - len(lines[j].lstrip(" ")) >= width):
                    body.extend([""] * (j - i)); i = j; loose = loose or not _ITEM.match(lines[j]); continue
                break
            ind = len(l) - len(l.lstrip(" ")); mi = _ITEM.match(l)
            if ind >= width or (mi and len(mi.group(1)) > base): body.append(l[min(ind, width):]); i += 1; continue
            if mi or _starts_block(l): break
            body.append(l.strip()); i += 1  # lazy continuation line
        items.append(body)
        if i < len(lines) and not lines[i].strip():
            j = i
            while j < len(lines) and not lines[j].strip(): j += 1
            mj = _ITEM.match(lines[j]) if j < len(lines) else None
            if mj and len(mj.group(1)) == base and mj.group(2)[0].isdigit() == ordered: loose = True; i = j; continue
            break
    lis = []
    for body in items:
        task = re.match(r"^\[([ xX])\]\s+", body[0]) if body else None
        if task: body = [("&#9745; " if task.group(1) != " " else "&#9744; ") + body[0][task.end():]] + body[1:]
        h = _blocks(body, refs)
        if not loose: h = re.sub(r"^<p>(.*?)</p>", r"\1", h, count=1, flags=re.S)
        lis.append(f"<li>{h}</li>")
    start = int(first.group(2)[:-1]) if ordered else 1
    tag = "ol" if ordered else "ul"; attr = f' start="{start}"' if ordered and start != 1 else ""
    out.append(f"<{tag}{attr}>" + "".join(lis) + f"</{tag}>")
    return i


def to_html(md):
    """Markdown text -> HTML fragment."""
    if not md: return ""
    text = re.sub(r"<!--.*?-->", "", md.replace("\r\n", "\n").replace("\r", "\n"), flags=re.S)
    lines = text.expandtabs(4).split("\n")
    refs = {}
    for l in lines:
        m = _REFDEF.match(l)
        if m: refs.setdefault(m.group(1).strip().lower(), m.group(2))
    return _blocks(lines, refs)


STYLE = """
html{background:#1f2229}
body{margin:0;padding:16px;background:#1f2229;color:#e7e9ee;font:13px/1.55 -apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif;word-wrap:break-word}
a{color:#ff6a2a;text-decoration:none}a:hover{text-decoration:underline}
h1,h2,h3,h4,h5,h6{margin:1.1em 0 .45em;line-height:1.3;color:#fff}
h1{font-size:20px;padding-bottom:.25em;border-bottom:1px solid #2b303a}h2{font-size:17px;padding-bottom:.2em;border-bottom:1px solid #2b303a}
h3{font-size:15px}h4{font-size:13.5px}h5,h6{font-size:13px;color:#9aa0ad}
body>:first-child{margin-top:0}
p,ul,ol,blockquote,pre,table{margin:0 0 .8em}
ul,ol{padding-left:1.6em}li{margin:.15em 0}li>ul,li>ol{margin:.15em 0}
img{max-width:100%;height:auto;border-radius:4px;vertical-align:middle}
code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;background:#2a2f3a;padding:.12em .35em;border-radius:4px}
pre{background:#2a2f3a;padding:10px 12px;border-radius:6px;overflow:auto}pre code{background:none;padding:0}
blockquote{margin-left:0;padding:.1em 0 .1em 12px;border-left:3px solid #3a4150;color:#9aa0ad}
hr{border:0;border-top:1px solid #2b303a;margin:1.2em 0}
table{border-collapse:collapse;display:block;overflow:auto;max-width:100%}
th,td{border:1px solid #2b303a;padding:5px 9px}th{background:#2a2f3a;font-weight:600}
del{color:#9aa0ad}
.changelog{margin-top:1.6em;padding-top:.4em;border-top:1px solid #2b303a}
"""


def document(readme_html, changelog_html=""):
    """Full dark HTML page: the README, then a "Changelog" section when there is one. No script can run (CSP)."""
    body = readme_html
    if changelog_html: body += f'\n<section class="changelog"><h1>Changelog</h1>\n{changelog_html}\n</section>'
    return ("<!doctype html><html><head><meta charset=\"utf-8\">"
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; img-src https: data:; style-src 'unsafe-inline'\">"
            "<meta name=\"viewport\" content=\"width=device-width\">"
            f"<style>{STYLE}</style></head><body>\n{body}\n</body></html>")
