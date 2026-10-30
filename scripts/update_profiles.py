#!/usr/bin/env python3
"""Refresh profiles.json with public numbers from Google Scholar and ResearchGate.

Runs daily on GitHub Actions. Uses only the Python standard library.
If a site blocks the request or its layout changes, the previous values are kept,
so the website never shows broken or empty data.
"""
import json, re, html, datetime, urllib.request, urllib.error, pathlib, sys, time

SCHOLAR_ID = "fG0DAJgAAAAJ"
RG_URL = "https://www.researchgate.net/profile/Ashutosh-Dwivedi-9"
OUT = pathlib.Path(__file__).resolve().parent.parent / "profiles.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
                                               "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def text(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()

def scholar():
    page = fetch(f"https://scholar.google.com/citations?hl=en&user={SCHOLAR_ID}&view_op=list_works&sortby=pubdate&pagesize=100")
    if "gsc_rsb_std" not in page:
        raise RuntimeError("profile not returned (probably a CAPTCHA / rate limit)")
    stats = [int(x) for x in re.findall(r'class="gsc_rsb_std">(\d+)<', page)]
    if len(stats) < 6:
        raise RuntimeError("could not read citation table")
    labels = [(int(m.group(1)), int(m.group(2))) for m in re.finditer(r'class="gsc_g_t"[^>]*right:(\d+)px[^>]*>(\d{4})<', page)]
    by_year = {str(y): 0 for _, y in labels}
    for m in re.finditer(r'class="gsc_g_a"[^>]*right:(\d+)px[^>]*>.*?class="gsc_g_al">(\d+)<', page, re.S):
        right, n = int(m.group(1)), int(m.group(2))
        if labels:
            y = min(labels, key=lambda l: abs((right - 5) - l[0]))[1]
            by_year[str(y)] = n
    pubs = []
    for row in re.findall(r'<tr class="gsc_a_tr[^"]*"[^>]*>(.*?)</tr>', page, re.S):
        t = re.search(r'class="gsc_a_at[^"]*"[^>]*>(.*?)</a>', row, re.S)
        grays = re.findall(r'<div class="gs_gray">(.*?)</div>', row, re.S)
        c = re.search(r'class="gsc_a_ac[^"]*"[^>]*>(\d*)</a>', row)
        y = re.search(r'class="gsc_a_h gsc_a_hc[^"]*">(\d{4})?<', row)
        if not t:
            continue
        pubs.append({"title": text(t.group(1)), "authors": text(grays[0]) if grays else "",
                     "venue": re.sub(r",\s*\d{4}$", "", text(grays[1])) if len(grays) > 1 else "",
                     "year": int(y.group(1)) if y and y.group(1) else None,
                     "cited_by": int(c.group(1)) if c and c.group(1) else 0})
    photo = re.search(r'id="gsc_prf_pup-img"[^>]*src="([^"]+)"', page)
    return {"citations": stats[0], "citations_since": stats[1], "h_index": stats[2], "h_index_since": stats[3],
            "i10_index": stats[4], "i10_index_since": stats[5], "citations_by_year": by_year, "publications": pubs,
            "photo": html.unescape(photo.group(1)) if photo else None,
            "url": f"https://scholar.google.com/citations?user={SCHOLAR_ID}"}

def researchgate():
    page = fetch(RG_URL)
    def num(label):
        m = re.search(r'([\d.,]+)\s*(?:</[^>]+>\s*)*(?:<[^>]+>\s*)*' + label, page)
        return float(m.group(1).replace(",", "")) if m else None
    score, cites, h = num("Research Interest"), num("Citations"), num("h-index")
    items = re.search(r'Research\s*\((\d+)\)', page)
    if score is None and cites is None:
        raise RuntimeError("profile not returned (ResearchGate usually blocks automated requests)")
    return {"score": score, "citations": int(cites) if cites is not None else None, "h_index": int(h) if h is not None else None,
            "research_items": int(items.group(1)) if items else None, "url": RG_URL}

def main():
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    before = json.dumps(data, sort_keys=True)
    today = datetime.date.today().isoformat()
    for key, fn in (("scholar", scholar), ("researchgate", researchgate)):
        for attempt in range(2):
            try:
                new = fn()
                new["updated"] = today
                old = {k: v for k, v in data.get(key, {}).items() if k != "updated"}
                cmp = {k: v for k, v in new.items() if k != "updated"}
                data[key] = new if cmp != old else {**data.get(key, {}), **{"updated": data.get(key, {}).get("updated", today)}}
                print(f"{key}: ok")
                break
            except Exception as e:  # keep previous values
                print(f"{key}: not updated ({e})", file=sys.stderr)
                time.sleep(5)
    if json.dumps(data, sort_keys=True) != before:
        OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        print("profiles.json updated")
    else:
        print("no changes")

if __name__ == "__main__":
    main()
