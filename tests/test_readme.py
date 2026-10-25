"""Markdown to HTML for mod READMEs, and `mods json-readme` with the network faked."""
import io, json, os, sys, tempfile, types, unittest, urllib.error
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try: import dnfile  # noqa: F401
except ImportError: sys.modules["dnfile"] = types.ModuleType("dnfile")
from lcport import config, mdhtml, mods

FIXTURE = """# Big Title
Some **bold**, *italic*, _also italic_, ~~gone~~ and `x < y` code.
Second line of the same paragraph.

Setext Heading
--------------

###### Tiny heading ######

```cs
if (a < b) { Debug.Log("<hi>"); }
```

    indented code & stuff

- one
- two with [a link](https://example.com/a?b=1&c=2)
  - nested *item*
- [x] done task

3. third
4. fourth

> quoted **text**
> more quote

***

![logo](http://cdn.example/logo.png "Logo")
[![badge](https://img.example/b.svg)](https://ci.example/)

| Name | Value |
|:-----|------:|
| a    | `1`   |
| b \\| c | 2 |

<script>alert('x')</script>
<p align="center"><img src="https://cdn.example/i.png" width="200" onerror="alert(1)"></p>
<a href="javascript:alert(1)">bad link</a> and <a href="https://ok.example">good link</a><br/>
<iframe src="https://evil.example"></iframe>
Visit https://thunderstore.io/c/lethal-company/ today. AT&T &copy; 2026
[ref link][docs]

[docs]: https://docs.example/start
<!-- hidden comment -->
"""


class MarkdownTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.h = mdhtml.to_html(FIXTURE)

    def has(self, *frags):
        for f in frags: self.assertIn(f, self.h)

    def test_headings(self):
        self.has("<h1>Big Title</h1>", "<h2>Setext Heading</h2>", "<h6>Tiny heading</h6>")

    def test_paragraph_and_emphasis(self):
        self.has("<p>Some <strong>bold</strong>, <em>italic</em>, <em>also italic</em>, <del>gone</del> and <code>x &lt; y</code> code.\nSecond line of the same paragraph.</p>")

    def test_code_blocks_escape(self):
        self.has('<pre><code class="language-cs">if (a &lt; b) { Debug.Log(&quot;&lt;hi&gt;&quot;); }</code></pre>', "<pre><code>indented code &amp; stuff</code></pre>")

    def test_lists(self):
        self.has('<ul><li>one</li><li>two with <a href="https://example.com/a?b=1&amp;c=2">a link</a>\n<ul><li>nested <em>item</em></li></ul></li><li>&#9745; done task</li></ul>',
                 '<ol start="3"><li>third</li><li>fourth</li></ol>')

    def test_blockquote_and_rule(self):
        self.has("<blockquote><p>quoted <strong>text</strong>\nmore quote</p></blockquote>", "<hr>")

    def test_images_and_links(self):
        self.has('<img src="https://cdn.example/logo.png" alt="logo">',  # http image upgraded to https
                 '<a href="https://ci.example/"><img src="https://img.example/b.svg" alt="badge"></a>',
                 '<a href="https://thunderstore.io/c/lethal-company/">https://thunderstore.io/c/lethal-company/</a> today.',
                 '<a href="https://docs.example/start">ref link</a>')
        self.assertNotIn("[docs]:", self.h)

    def test_table(self):
        self.has('<table><thead><tr><th style="text-align:left">Name</th><th style="text-align:right">Value</th></tr></thead>',
                 '<td style="text-align:left">b | c</td>', '<td style="text-align:right"><code>1</code></td>')

    def test_raw_html_is_escaped_or_sanitized(self):
        self.assertNotIn("<script", self.h); self.has("&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;")
        self.assertNotIn("<iframe", self.h); self.has("&lt;iframe src=&quot;https://evil.example&quot;&gt;&lt;/iframe&gt;")
        self.has('<img src="https://cdn.example/i.png" alt="" width="200">', '<a href="https://ok.example">good link</a><br>', "<a>bad link</a>")
        self.assertNotIn("onerror", self.h); self.assertNotIn("javascript:", self.h); self.assertNotIn("<p align", self.h)
        self.assertNotIn("hidden comment", self.h)
        self.has("AT&amp;T &copy; 2026")

    def test_document_has_dark_style_and_changelog(self):
        doc = mdhtml.document("<p>hi</p>", "<h2>1.0.0</h2>")
        for f in ("<!doctype html>", "background:#1f2229", "color:#e7e9ee", "a{color:#ff6a2a", "background:#2a2f3a", "font:13px", "padding:16px",
                  "img{max-width:100%", "Content-Security-Policy", "<p>hi</p>", "<h1>Changelog</h1>\n<h2>1.0.0</h2>"):
            self.assertIn(f, doc)
        self.assertNotIn("Changelog", mdhtml.document("<p>hi</p>", ""))


class FakeResp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


INDEX = [{"name": "MoreCompany", "full_name": "notnotnotswipez-MoreCompany", "owner": "notnotnotswipez", "rating_score": 1, "is_deprecated": False,
          "categories": ["Mods"], "date_updated": "2026-09-30T12:00:00Z", "website_url": "",
          "versions": [{"version_number": v, "description": "More players", "downloads": 10, "icon": "", "website_url": "https://github.com/notnotnotswipez/MoreCompany",
                        "dependencies": []} for v in ("1.14.0", "1.13.3")]}]


class JsonReadmeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        for p in (mock.patch.object(config, "CACHE", self.tmp.name), mock.patch.object(mods, "index", lambda: INDEX)):
            p.start(); self.addCleanup(p.stop)
        self.calls = []

    def fake_urlopen(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req; self.calls.append(url)
        if url.endswith("/readme/"): return FakeResp(json.dumps({"markdown": "# MoreCompany\n\nUp to **50** players.\n"}).encode())
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    def run_main(self, *args):
        buf = io.StringIO()
        with mock.patch("urllib.request.urlopen", self.fake_urlopen), redirect_stdout(buf): mods.main(list(args))
        return json.loads(buf.getvalue())

    def test_readme_json_shape_and_cache(self):
        out = self.run_main("json-readme", "notnotnotswipez-MoreCompany")
        self.assertEqual(set(out), {"full_name", "version", "html", "changelog_html", "website", "updated"})
        self.assertEqual((out["full_name"], out["version"], out["updated"]), ("notnotnotswipez-MoreCompany", "1.14.0", "2026-09-30"))
        self.assertEqual(out["website"], "https://github.com/notnotnotswipez/MoreCompany")
        self.assertIn("<h1>MoreCompany</h1>", out["html"]); self.assertIn("<strong>50</strong>", out["html"]); self.assertTrue(out["html"].startswith("<!doctype html>"))
        self.assertEqual(out["changelog_html"], ""); self.assertNotIn("Changelog", out["html"])  # changelog 404 -> empty
        base = "https://thunderstore.io/api/experimental/package/notnotnotswipez/MoreCompany/1.14.0/"
        self.assertEqual(self.calls, [base + "readme/", base + "changelog/"])
        d = os.path.join(self.tmp.name, "readme")
        self.assertEqual(sorted(os.listdir(d)), ["notnotnotswipez-MoreCompany-1.14.0.changelog.md", "notnotnotswipez-MoreCompany-1.14.0.readme.md"])
        with open(os.path.join(d, "notnotnotswipez-MoreCompany-1.14.0.readme.md")) as f: self.assertIn("Up to **50** players", f.read())
        self.calls.clear()
        again = self.run_main("json-readme", "notnotnotswipez-MoreCompany")
        self.assertEqual(self.calls, []); self.assertEqual(again, out)  # second open: cache only, no network

    def test_unknown_package(self):
        out = self.run_main("json-readme", "Nobody-Nothing")
        self.assertEqual((out["error"], out["html"]), ("unknown", "")); self.assertEqual(self.calls, [])

    def test_network_failure_is_reported_not_cached(self):
        def down(req, timeout=None): raise urllib.error.URLError("offline")
        buf = io.StringIO()
        with mock.patch("urllib.request.urlopen", down), redirect_stdout(buf): mods.main(["json-readme", "notnotnotswipez-MoreCompany"])
        out = json.loads(buf.getvalue())
        self.assertEqual(out["html"], ""); self.assertIn("README unavailable", out["error"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "readme", "notnotnotswipez-MoreCompany-1.14.0.readme.md")))


if __name__ == "__main__": unittest.main()
