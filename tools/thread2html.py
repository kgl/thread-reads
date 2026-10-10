#!/usr/bin/env python3
"""thread2html：把 X 推串整理成單檔 HTML（只用 Python 標準函式庫）。

子指令：fetch / translate / build / test / publish / all
詳見 tools/README.md。
"""
import argparse, base64, html as H, json, os, re, shutil, struct, subprocess, sys
import unicodedata, urllib.parse, urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
EXT = 'target="_blank" rel="noopener noreferrer"'
API = "https://api.x.com/2"
TWEET_FIELDS = "conversation_id,author_id,created_at,note_tweet,entities,attachments,referenced_tweets,in_reply_to_user_id"
MEDIA_FIELDS = "type,url,preview_image_url,variants,width,height,alt_text"


def die(msg):
    print("錯誤：" + msg, file=sys.stderr); sys.exit(1)


def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))


def save(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已寫入", p)


# ---------------------------------------------------------------- fetch
def tweet_id(s):
    m = re.search(r"(\d{8,})", s)
    if not m: die(f"看不出推文 id：{s}")
    return m.group(1)


def xget(path, params):
    tok = os.environ.get("X_BEARER_TOKEN")
    if not tok: die("需要環境變數 X_BEARER_TOKEN，或改用 --from-json")
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_pages_api(tid, archive):
    root = xget(f"/tweets/{tid}", {"tweet.fields": TWEET_FIELDS, "expansions": "author_id,attachments.media_keys",
                                    "media.fields": MEDIA_FIELDS, "user.fields": "username,name"})
    conv = root["data"].get("conversation_id", tid)
    user = root["includes"]["users"][0]["username"]
    pages, tok = [root], None
    endpoint = "/tweets/search/all" if archive else "/tweets/search/recent"
    while True:
        p = {"query": f"conversation_id:{conv} from:{user}", "max_results": 100, "tweet.fields": TWEET_FIELDS,
             "expansions": "attachments.media_keys", "media.fields": MEDIA_FIELDS,
             "start_time": root["data"]["created_at"]}
        if tok: p["next_token"] = tok
        r = xget(endpoint, p); pages.append(r)
        tok = r.get("meta", {}).get("next_token")
        if not tok: break
    return pages


def collect(pages):
    """把多頁 API 回應合併成 tweets/media/users 字典。接受 {data,includes} 或其串列。"""
    if isinstance(pages, dict): pages = [pages]
    tweets, media, users = {}, {}, {}
    for pg in pages:
        d = pg.get("data") or []
        for t in (d if isinstance(d, list) else [d]): tweets[t["id"]] = {**tweets.get(t["id"], {}), **t}
        inc = pg.get("includes", {})
        for m in inc.get("media", []): media[m["media_key"]] = m
        for u in inc.get("users", []): users[u["id"]] = u
        for t in inc.get("tweets", []): tweets.setdefault(t["id"], t)
    return tweets, media, users


def self_chain(tweets, root_id):
    root = tweets.get(root_id) or die(f"資料裡沒有根推文 {root_id}")
    author = root.get("author_id")
    kids = {}
    for t in tweets.values():
        if author and t.get("author_id", author) != author: continue
        for r in t.get("referenced_tweets", []) or []:
            if r["type"] == "replied_to": kids.setdefault(r["id"], []).append(t)
    chain, cur = [root], root
    while kids.get(cur["id"]):
        own = [k for k in kids[cur["id"]] if k.get("in_reply_to_user_id", author) == author or not author]
        if not own: break
        cur = min(own, key=lambda k: int(k["id"])); chain.append(cur)
    return chain, author


def expand_tco(u):
    try:
        out = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{redirect_url}", "-m", "15", u],
                             capture_output=True, text=True).stdout.strip()
        return out or u
    except Exception: return u


def download(url, dest):
    if dest.exists(): return True
    r = subprocess.run(["curl", "-sfL", "-m", "60", "-A", "Mozilla/5.0", "-o", str(dest), url])
    if r.returncode == 0 and dest.exists(): return True
    print("下載失敗", url, file=sys.stderr); dest.unlink(missing_ok=True); return False


def cmd_fetch(a):
    out = Path(a.out); media_dir = out / "media"; media_dir.mkdir(parents=True, exist_ok=True)
    tid = tweet_id(a.target)
    pages = load(a.from_json) if a.from_json else fetch_pages_api(tid, a.archive)
    tweets, media, users = collect(pages)
    chain, author = self_chain(tweets, tid)
    u = users.get(author, {})
    posts = []
    for i, t in enumerate(chain, 1):
        text = (t.get("note_tweet") or {}).get("text") or t.get("text", "")
        ents = ((t.get("note_tweet") or {}).get("entities") or {}).get("urls") or (t.get("entities") or {}).get("urls") or []
        urls = []
        for e in ents:
            exp = e.get("expanded_url") or ""
            if e.get("media_key") or re.search(rf"/status/{t['id']}/(photo|video)/", exp):
                text = text.replace(e["url"], ""); continue
            urls.append({"tco": e["url"], "expanded": exp or expand_tco(e["url"])})
        for tco in set(re.findall(r"https://t\.co/\w+", text)) - {x["tco"] for x in urls}:
            exp = expand_tco(tco)
            if re.search(rf"/status/{t['id']}/(photo|video)", exp): text = text.replace(tco, "")
            else: urls.append({"tco": tco, "expanded": exp})
        for x in urls: text = text.replace(x["tco"], x["expanded"])
        text = unicodedata.normalize("NFKC", text).strip()
        m = re.search(r"\[(\d+)/(?:n|\d+)\]\s*$", text)
        items = []
        for k, mk in enumerate((t.get("attachments") or {}).get("media_keys", []), 1):
            m_ = media.get(mk, {}); typ = m_.get("type")
            base = f"p{i:02d}_{k}"
            if typ == "photo" and m_.get("url"):
                ext = Path(urllib.parse.urlparse(m_["url"]).path).suffix or ".jpg"
                f = media_dir / (base + ext)
                if download(m_["url"], f): items.append({"type": "photo", "file": f"media/{f.name}", "url": m_["url"]})
            elif typ in ("video", "animated_gif"):
                vs = [v for v in m_.get("variants", []) if v.get("content_type") == "video/mp4"]
                vurl = max(vs, key=lambda v: v.get("bit_rate", 0))["url"] if vs else None
                item = {"type": typ, "video_url": vurl}
                frame = media_dir / (base + "_frame.jpg")
                if vurl and shutil.which("ffmpeg") and not frame.exists():
                    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(a.frame_sec), "-i", vurl,
                                    "-frames:v", "1", "-q:v", "3", str(frame)])
                if not frame.exists() and m_.get("preview_image_url"): download(m_["preview_image_url"], frame)
                if frame.exists(): item["file"] = f"media/{frame.name}"
                items.append(item)
        posts.append({"n": int(m.group(1)) if m else i, "id": t["id"], "url": f"https://x.com/i/status/{t['id']}",
                      "created_at": t.get("created_at"), "text": text, "urls": urls, "media": items})
    thread = {"source": {"id": tid, "url": f"https://x.com/i/status/{tid}", "created_at": chain[0].get("created_at"),
                         "author": {"id": author, "name": u.get("name"), "username": u.get("username")}},
              "posts": posts}
    save(out / "thread.json", thread)
    nums = [p["n"] for p in posts]
    print(f"共 {len(posts)} 則；編號 {nums[0]}～{nums[-1]}" + ("" if nums == sorted(nums) else "（順序異常，請檢查）"))


# ---------------------------------------------------------------- translate
def make_template(thread):
    return {"_說明": "填寫 title、meta、summary_html、takeaways、sections 與每則 zh。zh 是純文字，"
                     "程式碼或 prompt 用 ``` 包起來並保留原文。sections 用 n 分組。link_labels 可把網址換成可讀標籤。",
            "title": "", "meta": "", "summary_html": "", "takeaways": [], "footer_note": "作者對其他使用者的回覆未納入。",
            "hero": {"from_post": 1, "caption": ""},
            "sections": [{"title": "", "posts": [p["n"] for p in thread["posts"]]}],
            "link_labels": {u["expanded"]: "" for p in thread["posts"] for u in p["urls"]},
            "posts": [{"n": p["n"], "source_text": p["text"], "zh": "", "note": ""} for p in thread["posts"]]}


def linkify(t, labels=None):
    for u, lab in (labels or {}).items():
        if lab: t = re.sub(rf'(?<!href="){re.escape(H.escape(u, quote=False))}', f'<a href="{u}" {EXT}>{H.escape(lab)}</a>', t)
    return re.sub(r'(?<!href=")(?<!">)(https?://[^\s<"）　]+)', lambda m: f'<a href="{m.group(1)}" {EXT}>{m.group(1)}</a>', t)


def zh_to_html(zh, labels):
    parts = re.split(r"```[a-zA-Z]*\n?(.*?)```", zh, flags=re.S)
    out = []
    for i, p in enumerate(parts):
        if i % 2: out.append("<pre>" + linkify(H.escape(p.strip("\n"), quote=False), labels) + "</pre>")
        elif p.strip(): out.append(linkify(H.escape(p.strip(), quote=False).replace("\n", "<br>"), labels))
    return "".join(out)


def llm_fill(template):
    key = os.environ.get("OPENAI_API_KEY") or die("需要 OPENAI_API_KEY（或改用 --template / --apply 由 agent 填寫）")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    prompt = ("把下面 JSON 範本填完後只回傳 JSON。每則 zh 為忠實的台灣繁體中文翻譯，技術名詞保留英文，"
              "程式碼與 prompt 用 ``` 包住並保留原文，不要編造。用「」引號，數字與中文間加半形空格。\n" +
              json.dumps(template, ensure_ascii=False))
    body = json.dumps({"model": model, "response_format": {"type": "json_object"},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(json.loads(r.read())["choices"][0]["message"]["content"])


def apply_filled(thread, f):
    by_n = {p["n"]: p for p in thread["posts"]}
    zh = {p["n"]: p for p in f["posts"]}
    missing = [n for n in by_n if not (zh.get(n) or {}).get("zh", "").strip()]
    if missing: die(f"以下編號沒有翻譯：{missing}")
    labels = {k: v for k, v in (f.get("link_labels") or {}).items() if v}
    hero = None; hp = (f.get("hero") or {}).get("from_post")
    secs = []
    for s in f["sections"]:
        ps = []
        for n in s["posts"]:
            src = by_n[n]; imgs = []
            for m in src["media"]:
                if not m.get("file"): continue
                if n == hp and hero is None:
                    hero = {"file": m["file"], "alt": "首推配圖", "caption_html": linkify(H.escape(f["hero"].get("caption") or ""), labels)
                            + (f'（<a href="{m["video_url"]}" {EXT}>觀看原影片 MP4</a>）' if m.get("video_url") else "")}
                    continue
                imgs.append(m["file"])
            note = H.escape(zh[n].get("note") or "")
            vids = [m["video_url"] for m in src["media"] if m.get("video_url") and n != hp]
            note += "".join(f' <a href="{v}" {EXT}>觀看影片 MP4</a>' for v in vids)
            ps.append({"n": n, "html": zh_to_html(zh[n]["zh"], labels), "images": imgs, "note_html": note.strip()})
        secs.append({"title": s["title"], "posts": ps})
    src = thread["source"]
    return {"lang": "zh-Hant-TW", "title": f["title"], "meta_html": H.escape(f.get("meta") or "") +
            f'・<a href="{src["url"]}" {EXT}>原推串</a>', "hero": hero, "summary_html": f.get("summary_html", ""),
            "takeaways_html": f.get("takeaways", []), "footer_note_html": H.escape(f.get("footer_note") or ""),
            "sections": secs}


def cmd_translate(a):
    d = Path(a.dir); thread = load(d / "thread.json")
    if a.template:
        save(d / "translate_template.json", make_template(thread))
        print("請填寫 translate_template.json，再執行：translate --apply", d / "translate_template.json"); return
    filled = load(a.apply) if a.apply else llm_fill(make_template(thread))
    if not a.apply: save(d / "translate_filled.json", filled)
    save(d / "translated.json", apply_filled(thread, filled))


# ---------------------------------------------------------------- build
def img_size(p):
    b = Path(p).read_bytes()
    if b[:8] == b"\x89PNG\r\n\x1a\n": return struct.unpack(">II", b[16:24])
    i = 2
    while i < len(b):
        if b[i] != 0xFF: i += 1; continue
        mk = b[i + 1]; ln = struct.unpack(">H", b[i + 2:i + 4])[0]
        if mk in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", b[i + 5:i + 9]); return w, h
        i += 2 + ln
    return None


def img_tag(path, alt, cls=""):
    p = Path(path); mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    wh = img_size(p); dims = f'width="{wh[0]}" height="{wh[1]}" ' if wh else ""
    c = f'class="{cls}" ' if cls else ""
    data = f'src="data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"'
    return f'<img {c}{dims}{data} alt="{alt}">' if cls else f'<img {dims}alt="{alt}" {data}>'


def plain(t): return H.unescape(re.sub(r"<[^>]+>", "", t.split("<pre>")[0]))


def build_html(tr, base):
    css = (TOOLS / "template_style.css").read_text(encoding="utf-8")
    js = (TOOLS / "template_script.js").read_text(encoding="utf-8")
    posts = [p for s in tr["sections"] for p in s["posts"]]
    toc = ['<a href="#summary">這套東西在講什麼</a>', '<a href="#takeaways">學習要點</a>', '<a href="#posts">推串正文</a>']
    toc += [f'<a class="sub" href="#p{p["n"]}">#{p["n"]} {H.escape(plain(p["html"])[:18])}…</a>' for p in posts]
    body = []
    for s in tr["sections"]:
        if s.get("title"): body.append(f'<h3 class="sec">{s["title"]}</h3>')
        for p in s["posts"]:
            body.append(f'<article id="p{p["n"]}"><h4>#{p["n"]}</h4><p>{linkify(p["html"])}</p>')
            for f in p.get("images", []): body.append(img_tag(base / f, f'第 {p["n"]} 則配圖'))
            if p.get("note_html"): body.append(f'<p class="note">{p["note_html"]}</p>')
            body.append('</article>')
    hero = ""
    if tr.get("hero"):
        hr = tr["hero"]; hero = img_tag(base / hr["file"], hr.get("alt", ""), "hero") + f'<p class="cap">{hr.get("caption_html", "")}</p>'
    tk = "".join(f"\n<li>{x}</li>" for x in tr.get("takeaways_html", []))
    return f'''<!doctype html><html lang="{tr.get("lang", "zh-Hant-TW")}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{H.escape(tr["title"], quote=False)}</title><style>{css}</style></head><body>
<button id="tg">☰ 目錄</button><div class="wrap"><nav id="toc"><b>目錄</b>{"".join(toc)}</nav><main>
<h1>{H.escape(tr["title"], quote=False)}</h1>
<p class="meta">{tr.get("meta_html", "")}</p>
{hero}
<h2 id="summary">這套東西在講什麼</h2><div class="card">{tr.get("summary_html", "")}</div>
<h2 id="takeaways">學習要點</h2><div class="card"><ul>{tk}</ul></div>
<h2 id="posts">推串正文</h2>{"".join(body)}
<p class="note">{tr.get("footer_note_html", "")}</p>
</main></div><script>{js}</script></body></html>'''


def cmd_build(a):
    src = Path(a.translated); out = Path(a.out or src.parent / "index.html")
    out.write_text(build_html(load(src), src.parent), encoding="utf-8")
    print(f"已輸出 {out}（{out.stat().st_size:,} bytes）")


# ---------------------------------------------------------------- test
def cmd_test(a):
    td = TOOLS / "test"
    if not (td / "node_modules" / "puppeteer-core").exists():
        subprocess.run(["npm", "install", "--silent"], cwd=td, check=True)
    chrome = a.chrome or os.environ.get("CHROME_PATH") or shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome: die("找不到 Chrome，請設定 CHROME_PATH 或 --chrome")
    r = subprocess.run(["node", str(td / "run.js"), str(Path(a.html).resolve()), chrome] + (["--shots", a.shots] if a.shots else []))
    sys.exit(r.returncode)


# ---------------------------------------------------------------- publish
def cmd_publish(a):
    html = Path(a.html); slug = a.slug
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug): die("slug 只能用小寫英數與連字號")
    dest = REPO / slug / "index.html"; dest.parent.mkdir(exist_ok=True)
    shutil.copyfile(html, dest)
    title = re.search(r"<title>(.*?)</title>", html.read_text(encoding="utf-8"), re.S).group(1)
    idx = REPO / "index.html"; s = idx.read_text(encoding="utf-8")
    if "<!-- LIST:START -->" not in s: die("根目錄 index.html 缺少 <!-- LIST:START --> / <!-- LIST:END --> 標記")
    a_, b_ = s.index("<!-- LIST:START -->") + len("<!-- LIST:START -->"), s.index("<!-- LIST:END -->")
    items = [l for l in s[a_:b_].strip().splitlines() if l.strip() and f'href="{slug}/"' not in l]
    note = f"（{H.escape(a.note)}）" if a.note else ""
    items.insert(0, f'<li><a href="{slug}/">{title}</a>{note}</li>')
    idx.write_text(s[:a_] + "\n" + "\n".join(items) + "\n" + s[b_:], encoding="utf-8")
    ident = []
    if not subprocess.run(["git", "-C", str(REPO), "config", "user.email"], capture_output=True, text=True).stdout.strip():
        me = subprocess.run(["gh", "api", "user", "--jq", '.login+" "+(.id|tostring)'], capture_output=True, text=True).stdout.split()
        if len(me) == 2: ident = ["-c", f"user.name={me[0]}", "-c", f"user.email={me[1]}+{me[0]}@users.noreply.github.com"]
    git = lambda *x: subprocess.run(["git", *ident, "-C", str(REPO), *x], check=True)
    git("add", f"{slug}/index.html", "index.html")
    if subprocess.run(["git", "-C", str(REPO), "diff", "--cached", "--quiet"]).returncode == 0:
        print("沒有變更，不需提交"); return
    git("commit", "-m", f"Publish {slug}")
    if not a.no_push: git("push", "origin", "HEAD:main")
    print(f"已發布：{slug}/ （GitHub Pages 約 1 分鐘後更新）")


# ---------------------------------------------------------------- all
def cmd_all(a):
    d = Path(a.out)
    cmd_fetch(argparse.Namespace(target=a.target, out=a.out, from_json=a.from_json, archive=a.archive, frame_sec=a.frame_sec))
    if a.apply: cmd_translate(argparse.Namespace(dir=a.out, template=False, apply=a.apply))
    elif os.environ.get("OPENAI_API_KEY"): cmd_translate(argparse.Namespace(dir=a.out, template=False, apply=None))
    else:
        cmd_translate(argparse.Namespace(dir=a.out, template=True, apply=None))
        print("沒有 OPENAI_API_KEY：請填寫範本後，以 --apply 重新執行 all，或依序執行 translate --apply / build / test / publish"); return
    cmd_build(argparse.Namespace(translated=str(d / "translated.json"), out=None))
    r = subprocess.run([sys.executable, __file__, "test", str(d / "index.html")])
    if r.returncode: die("測試沒有通過，未發布")
    if a.slug: cmd_publish(argparse.Namespace(html=str(d / "index.html"), slug=a.slug, note=a.note, no_push=a.no_push))


def main():
    ap = argparse.ArgumentParser(description="把 X 推串整理成單檔 HTML")
    sp = ap.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("fetch"); f.add_argument("target"); f.add_argument("--out", default="work")
    f.add_argument("--from-json"); f.add_argument("--archive", action="store_true", help="用 search/all（需完整存取權限）")
    f.add_argument("--frame-sec", type=float, default=3); f.set_defaults(fn=cmd_fetch)
    t = sp.add_parser("translate"); t.add_argument("--dir", default="work")
    g = t.add_mutually_exclusive_group(); g.add_argument("--template", action="store_true"); g.add_argument("--apply")
    t.set_defaults(fn=cmd_translate)
    b = sp.add_parser("build"); b.add_argument("translated"); b.add_argument("--out"); b.set_defaults(fn=cmd_build)
    te = sp.add_parser("test"); te.add_argument("html"); te.add_argument("--chrome"); te.add_argument("--shots")
    te.set_defaults(fn=cmd_test)
    p = sp.add_parser("publish"); p.add_argument("slug"); p.add_argument("--html", required=True); p.add_argument("--note")
    p.add_argument("--no-push", action="store_true"); p.set_defaults(fn=cmd_publish)
    al = sp.add_parser("all"); al.add_argument("target"); al.add_argument("--slug"); al.add_argument("--out", default="work")
    al.add_argument("--from-json"); al.add_argument("--apply"); al.add_argument("--archive", action="store_true")
    al.add_argument("--frame-sec", type=float, default=3); al.add_argument("--note"); al.add_argument("--no-push", action="store_true")
    al.set_defaults(fn=cmd_all)
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
