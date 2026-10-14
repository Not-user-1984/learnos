#!/usr/bin/env python3
"""
web_research.py — конвейер быстрого ресёрча: Google → фильтр мусора → резолв
редиректов → чтение страниц → чистый текст/дайджест.

Подкоманды:
  probe                          — доступность поисковиков (DNS/сеть)
  search "запрос" [опции]        — батч-поиск Google, фильтр, резолв URL
  read URL [URL...] [опции]      — скачать страницы, вытащить чистый текст
  research "тема" [опции]        — полный цикл: search → отбор → read → дайджест

Профиль браузера — общий с browser_pilot (_default): тёплые cookies Google
(пройденная капча) живут там. При капче: web_research.py search "..." --gui

Выход: markdown/json в stdout. Не зависит от памяти нейронки — только тулзы.
"""
import argparse, json, os, re, sys, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ---------------------------------------------------------------- константы
PROFILE = Path.home() / ".config/opencode/browser_profiles/_default"

JUNK_DOMAINS = (
    "pinterest", "quora", "facebook", "tiktok", "instagram", "coursehero",
    "geeksforgeeks", ".pw/", "slideshare", "scribd", "answers.yahoo",
    "wikihow", "reddit.com/r/", "medium.com/tag",
)
AI_STUB = ("Ответ в режиме ИИ", "AI Overview", "Ответы от ИИ")
# домены с репутацией (тех/доки/официальные) — плюс к скору
GOOD_DOMAINS = (
    "kubernetes.io", "github.com", "docs.", "/documentation", "cncf.io",
    "habr.com", "stackoverflow.com", "oreilly.com", "redhat.com", "docker.com",
    "learnk8s.io", "killercoda.com", "kodekloud.com", "collabnix", "ajeetraina",
    ".dev/", "nginx.org", "postgresql.org", "fastapi", "python.org",
)

DEFAULT_ASPECTS_EN = ["{q}", "{q} official documentation", "{q} best practices guide", "{q} 2026 new features"]
DEFAULT_ASPECTS_RU = ["{q}", "{q} руководство документация", "{q} лучшие практики", "{q} 2026 что нового"]

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


# ---------------------------------------------------------------- браузер
CDP_URL = "http://localhost:9222"


def launch(gui=False):
    """Подключаемся к живому демону (CDP) или поднимаем новый контекст."""
    from patchright.sync_api import sync_playwright
    pw = sync_playwright().start()
    # 1) живой демон? — мгновенное подключение, тёплые cookies
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL, timeout=1500)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page._cdp_attached = True
        return pw, ctx, page
    except Exception:
        pass
    # 2) холодный запуск (как раньше)
    ctx = pw.chromium.launch_persistent_context(
        str(PROFILE), headless=not gui,
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return pw, ctx, page


def close(pw, ctx, page):
    """CDP-сессию не закрываем (демон должен жить), свой контекст — закрываем."""
    if getattr(page, "_cdp_attached", False):
        try:
            pw.stop()  # отключаемся, браузер продолжает жить
        except Exception:
            pass
    else:
        try:
            ctx.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


PLIST = Path.home() / "Library/LaunchAgents/com.radmipa.web-research-daemon.plist"
LABEL = "com.radmipa.web-research-daemon"


def daemon_start():
    """Поднять браузер-демон. Автостарт при логине — через LaunchAgent (см. SKILL.md)."""
    import subprocess, socket, time as _t
    def alive():
        s = socket.socket(); s.settimeout(1)
        ok = s.connect_ex(("localhost", 9222)) == 0
        s.close(); return ok
    if alive():
        print("Демон уже жив: localhost:9222")
        return
    if PLIST.exists():
        # LaunchAgent: поднимет сам (и KeepAlive воскресит при падении)
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
        subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST)], capture_output=True)
        for _ in range(20):
            if alive(): break
            _t.sleep(0.5)
        print("Демон поднят (LaunchAgent): localhost:9222" if alive() else "LaunchAgent не поднял порт — проверь /tmp/web_research_daemon.log")
        return
    # fallback: plist не установлен — обычный фоновый процесс
    code = (
        "from patchright.sync_api import sync_playwright\n"
        "pw = sync_playwright().start()\n"
        "ctx = pw.chromium.launch_persistent_context(\n"
        f"    {str(PROFILE)!r}, headless=True,\n"
        f"    args=['--remote-debugging-port=9222', '--disable-blink-features=AutomationControlled'],\n"
        ")\n"
        "import time\n"
        "while True:\n"
        "    time.sleep(3600)\n"
    )
    subprocess.Popen([sys.executable, "-c", code],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    _t.sleep(3)
    print("Демон поднят (фоновый процесс): localhost:9222" if alive() else "НЕ УДАЛОСЬ")


def daemon_stop():
    import subprocess
    if PLIST.exists():
        # bootout останавливает И отключает KeepAlive-воскрешение
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    subprocess.run(["pkill", "-f", "remote-debugging-port=9222"], capture_output=True)
    print("Демон остановлен (до следующего запуска/логина)")


def g_extract(page):
    # Устойчиво к A/B-вариантам Google: ищем goto/url-редирект или внешний http-анкор
    return page.eval_on_selector_all(
        "div.g, div.MjjYud, div.N54PNb",
        """els => els.map(e => {
            const links = Array.from(e.querySelectorAll('a[href]'));
            const a = links.find(x => x.href.includes('goto?') || x.href.includes('/url?'))
                    || links.find(x => /^https?:\\/\\//.test(x.href) && !x.href.includes('.google.'));
            const t = e.querySelector('h3, [role="heading"]');
            let snip = '';
            const s = e.querySelector('[data-sncf], .VwiC3b');
            if (s) snip = s.innerText.slice(0,200);
            else {
                const full = (e.innerText || '').split('\\n').filter(Boolean);
                snip = full.slice(2, 8).join(' ').slice(0, 200); // после title+url
            }
            return {url: a ? a.href : '', title: t ? t.innerText : '', snip: snip};
        }).filter(r => r.title && r.url).slice(0, 8)"""
    )


def is_junk(r):
    u, t = r["url"].lower(), r["title"]
    return any(j in u for j in JUNK_DOMAINS) or any(a in t for a in AI_STUB)


def score(r):
    s = 0
    u = r["url"].lower()
    if any(g in u for g in GOOD_DOMAINS): s += 3
    if re.search(r"20(2[4-9])", r["snip"]): s += 1   # свежесть в сниппете
    if u.startswith("https://"): s += 1
    return s


def cdp_alive():
    import socket
    sock = socket.socket(); sock.settimeout(1)
    ok = sock.connect_ex(("localhost", 9222)) == 0
    sock.close()
    return ok


def _one_search_worker(q, hl):
    """Отдельный поток: своё CDP-подключение к демону, своя вкладка."""
    from patchright.sync_api import sync_playwright
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL, timeout=3000)
        ctx = browser.contexts[0]
        page = ctx.new_page()
        try:
            url = "https://www.google.com/search?q=" + urllib.parse.quote(q) + f"&hl={hl}&num=10"
            try:
                page.goto(url, timeout=25000, wait_until="domcontentloaded")
            except Exception:
                pass
            try:
                page.wait_for_selector("h3, [role='heading']", timeout=5000)
            except Exception:
                pass
            time.sleep(0.4)
            if "/sorry/" in page.url:
                return {"captcha": True}
            res = g_extract(page)
            for r in res:
                r["q"] = q
            return {"captcha": False, "res": res}
        finally:
            try:
                page.close()  # анти-утечка вкладок в демоне
            except Exception:
                pass
    finally:
        pw.stop()


def _one_resolve_worker(r):
    from patchright.sync_api import sync_playwright
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL, timeout=3000)
        page = browser.contexts[0].new_page()
        try:
            try:
                page.goto(r["url"], timeout=12000, wait_until="commit")
                r["url"] = page.url
            except Exception:
                try: r["url"] = page.url
                except Exception: pass
        finally:
            try:
                page.close()  # анти-утечка вкладок в демоне
            except Exception:
                pass
    except Exception:
        pass
    finally:
        pw.stop()


def do_search(query, aspects, top, gui, max_per_query=6):
    ru = bool(re.search(r"[а-яё]", query, re.I))
    templates = DEFAULT_ASPECTS_RU if ru else DEFAULT_ASPECTS_EN
    queries = [t.format(q=query) for t in (aspects or templates)][:5]
    hl = "ru" if ru else "en"

    raw, captcha = [], False
    parallel = cdp_alive() and not gui

    if parallel:
        # все аспекты — одновременно, каждое в своей вкладке через CDP
        with ThreadPoolExecutor(max_workers=min(5, len(queries))) as ex:
            for out in ex.map(lambda q: _one_search_worker(q, hl), queries):
                if out.get("captcha"):
                    captcha = True
                else:
                    raw.extend(out["res"][:max_per_query])
    else:
        pw, ctx, page = launch(gui)
        try:
            for q in queries:
                url = "https://www.google.com/search?q=" + urllib.parse.quote(q) + f"&hl={hl}&num=10"
                try:
                    page.goto(url, timeout=25000, wait_until="domcontentloaded")
                except Exception:
                    pass
                try:
                    page.wait_for_selector("h3, [role='heading']", timeout=5000)
                except Exception:
                    pass
                time.sleep(0.4)
                if "/sorry/" in page.url:
                    captcha = True
                    break
                for r in g_extract(page)[:max_per_query]:
                    r["q"] = q
                    raw.append(r)
        finally:
            close(pw, ctx, page)

    if captcha:
        print("⚠ Google CAPTCHA. Прогони: web_research.py search 'запрос' --gui "
              "(кликни капчу — cookies сохранятся в профиль).", file=sys.stderr)
        sys.exit(2)

    # фильтр мусора + дедуп точных дублей (до резолва — по полному raw-URL с токеном)
    seen_raw, clean = set(), []
    for r in raw:
        if is_junk(r): continue
        key = r["url"] + "|" + r["title"]
        if key in seen_raw: continue
        seen_raw.add(key)
        clean.append(r)

    # резолв google-редиректов с запасом (goto-токены уникальны — дедупить до нельзя)
    buffer = top + 6
    candidates = clean[:buffer]
    if any("/goto?" in r["url"] or "/url?" in r["url"] for r in candidates):
        todo = [r for r in candidates if "/goto?" in r["url"] or "/url?" in r["url"]]
        if cdp_alive():
            with ThreadPoolExecutor(max_workers=min(6, len(todo))) as ex:
                list(ex.map(_one_resolve_worker, todo))
        else:
            pw, ctx, page = launch(False)
            try:
                for r in todo:
                    try:
                        page.goto(r["url"], timeout=12000, wait_until="commit")
                        r["url"] = page.url
                    except Exception:
                        try: r["url"] = page.url
                        except Exception: pass
            finally:
                close(pw, ctx, page)

    # финал: дедуп по реальному URL + скор по домену + сортировка
    seen_real, final = set(), []
    for r in candidates:
        real = re.sub(r"https?://(www\.)?", "", r["url"]).split("?")[0].rstrip("/")
        if real in seen_real or real.startswith("google.com"): continue
        seen_real.add(real)
        r["score"] = score(r)
        final.append(r)
    final.sort(key=lambda r: -r["score"])
    return final[:top]


def fmt_md(items):
    out = [f"# Найдено {len(items)} ссылок (отфильтровано, отсортировано по скору)\n"]
    for i, r in enumerate(items, 1):
        out.append(f"{i}. **[{r['title']}]({r['url']})**  \n   _{r['snip'][:160]}_\n")
    return "\n".join(out)


# ---------------------------------------------------------------- чтение
def extract_text(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form",
                     "noscript", "iframe", "svg"]):
        tag.decompose()
    # выкидываем навигационную обвязку (sidebar/toc/breadcrumbs)
    for sel in ("[role='navigation']", ".sidebar", ".sphinxsidebar", ".toc", ".nav",
                ".breadcrumbs", ".headerlink", ".related", ".topless", "[aria-label]",
                ".wy-nav-side", ".footer", "#searchbox"):
        for t in soup.select(sel):
            t.decompose()
    main = (soup.find(attrs={"role": "main"}) or soup.find("article") or soup.find("main")
            or soup.find("div", class_="document") or soup.find("div", class_="td-content")
            or soup.find(attrs={"class": re.compile(r"(post-content|markdown-body|article-body)")})
            or soup.body or soup)
    text = main.get_text("\n", strip=True)
    # отрезаем длинные оглавления в начале (строки-ссылки без пробелов/пунктов меню)
    lines = text.split("\n")
    start = 0
    for i, ln in enumerate(lines[:80]):
        if len(ln) > 40 and ("¶" not in ln):  # первый содержательный абзац
            start = i
            break
    text = "\n".join(lines[start if start else 0:])
    return re.sub(r"\n{3,}", "\n\n", text)


def fetch_one(url, timeout=15):
    import requests
    try:
        resp = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "ru,en;q=0.8"},
                            timeout=timeout, allow_redirects=True)
        ctype = resp.headers.get("content-type", "")
        if resp.status_code == 200 and ("html" in ctype or "text" in ctype or not ctype):
            text = extract_text(resp.text)
            title = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.S | re.I)
            return {"url": url, "status": resp.status_code,
                    "title": title.group(1).strip()[:120] if title else "",
                    "text": text, "js_shell": len(text) < 700}
        return {"url": url, "status": resp.status_code, "title": "", "text": "", "js_shell": False}
    except Exception as e:
        return {"url": url, "status": 0, "title": f"ERR: {str(e)[:80]}", "text": "", "js_shell": False}


def browser_fetch(urls):
    """Fallback для JS-страниц: один браузер, по очереди.

    CDP-режим: обязательно закрываем свою вкладку по завершении — иначе она
    остаётся жить в демоне и копит RSS (ЯМ/onlinetrade+sw легко 100+ МБ/вкладка).
    """
    pw, ctx, page = launch(False)
    out = []
    try:
        for u in urls:
            try:
                page.goto(u, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass
            time.sleep(1.5)
            out.append({"url": u, "status": 200, "title": page.title()[:120],
                        "text": extract_text(page.content()), "js_shell": False})
    finally:
        if getattr(page, "_cdp_attached", False):
            try:
                page.close()  # демон живёт, вкладку — вон (анти-утечка)
            except Exception:
                pass
        close(pw, ctx, page)
    return out


# ---------------------------------------------------------------- команды
def cmd_probe(_):
    for h in ("yandex.ru", "google.com", "bing.com", "html.duckduckgo.com", "mojeek.com", "ecosia.org"):
        import socket
        try:
            ip = socket.gethostbyname(h); print(f"{h:24} ✓ {ip}")
        except Exception:
            print(f"{h:24} ✗ DNS FAIL")
    import subprocess
    dns = subprocess.run(["scutil", "--dns"], capture_output=True, text=True).stdout
    ns = re.findall(r"nameserver\[\d\] : (\S+)", dns)
    print(f"DNS: {', '.join(dict.fromkeys(ns))}  {'← корп. VPN (10.x) — поиск деградирует' if any(n.startswith('10.') for n in ns) else ''}")


def cmd_search(a):
    items = do_search(a.query, a.aspect, a.top, a.gui)
    print(json.dumps(items, ensure_ascii=False, indent=1) if a.json else fmt_md(items))


def cmd_read(a):
    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_one, u): u for u in a.urls}
        for f in as_completed(futs):
            r = f.result()
            if a.verbose: print(f"[{r['status']}] {r['url'][:90]}", file=sys.stderr)
            results.append(r)
    order = {u: i for i, u in enumerate(a.urls)}
    results.sort(key=lambda r: order.get(r["url"], 99))
    js = [r["url"] for r in results if r["js_shell"]]
    if js and not a.no_browser:
        if a.verbose: print(f"JS-шеллы, добираю браузером: {len(js)}", file=sys.stderr)
        results.extend(browser_fetch(js))
    for r in results:
        print(f"\n{'='*90}\nURL: {r['url']}\nTITLE: {r['title']}\n{'='*90}")
        print(r["text"][:a.max_chars] or "(пусто)")


def cmd_research(a):
    print(f"# Ресёрч: {a.query}\n", file=sys.stderr)
    t0 = time.time()
    items = do_search(a.query, a.aspect, a.top, a.gui)
    print(fmt_md(items), file=sys.stderr)
    urls = [r["url"] for r in items][:a.read]
    print(f"\nЧитаю топ-{len(urls)} страниц…\n", file=sys.stderr)
    pages = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_one, u): u for u in urls}
        for f in as_completed(futs):
            r = f.result(); pages.append(r)
            print(f"  [{r['status']}] {r['url'][:80]}", file=sys.stderr)
    order = {u: i for i, u in enumerate(urls)}
    pages.sort(key=lambda r: order.get(r["url"], 99))
    js = [r["url"] for r in pages if r["js_shell"]]
    if js:
        print(f"  JS-шеллы → браузер: {len(js)}", file=sys.stderr)
        pages.extend(browser_fetch(js))
    print(f"\nГотово за {time.time()-t0:.1f}с\n", file=sys.stderr)
    for r, meta in zip(pages, [m for m in items if m["url"] in urls] * 2):
        pass  # метаданные уже в pages
    for r in pages:
        print(f"\n{'#'*90}\n## {r['title']}\n{r['url']}\n{'#'*90}")
        print(r["text"][:a.max_chars] or "(пусто)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("probe").set_defaults(func=cmd_probe)

    d = sub.add_parser("daemon", aliases=[])
    da = d.add_subparsers(dest="daemon_cmd", required=True)
    da.add_parser("start").set_defaults(func=lambda a: daemon_start())
    da.add_parser("stop").set_defaults(func=lambda a: daemon_stop())

    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--aspect", action="append", help="свой шаблон аспекта (можно несколько)")
    s.add_argument("--top", type=int, default=8)
    s.add_argument("--json", action="store_true")
    s.add_argument("--gui", action="store_true", help="видимое окно (для капчи)")
    s.set_defaults(func=cmd_search)

    r_ = sub.add_parser("read")
    r_.add_argument("urls", nargs="+")
    r_.add_argument("--max-chars", type=int, default=6000)
    r_.add_argument("--no-browser", action="store_true")
    r_.add_argument("-v", "--verbose", action="store_true")
    r_.set_defaults(func=cmd_read)

    rsh = sub.add_parser("research")
    rsh.add_argument("query")
    rsh.add_argument("--aspect", action="append")
    rsh.add_argument("--top", type=int, default=8)
    rsh.add_argument("--read", type=int, default=4, help="сколько страниц читать")
    rsh.add_argument("--max-chars", type=int, default=4000)
    rsh.add_argument("--gui", action="store_true")
    rsh.set_defaults(func=cmd_research)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
