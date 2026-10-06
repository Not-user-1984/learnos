import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def main(query: str, limit: int = 5) -> dict:
    r = httpx.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers={"User-Agent": UA},
        timeout=15,
        follow_redirects=True,
    )
    if r.status_code != 200 or "result__a" not in r.text:
        return {"query": query, "count": 0, "results": [], "error": f"ddg status {r.status_code}, возможно анти-бот"}

    blocks = re.split(r'<div[^>]+class="[^"]*result[^"]*"', r.text)[1:]
    results = []
    for b in blocks:
        m = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', b)
        if not m:
            continue
        url, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        if "uddg=" in url:
            url = parse_qs(urlparse(url).query).get("uddg", [url])[0]
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', b, re.S)
        snippet = re.sub(r"<[^>]+>", "", sn.group(1)).strip() if sn else ""
        results.append({"title": unquote(title).strip(), "url": unquote(url), "snippet": snippet[:200]})
        if len(results) >= limit:
            break
    return {"query": query, "count": len(results), "results": results}
