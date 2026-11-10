"""Build covers.css: sharper cover images (+ a few theme extras) for one MyAnimeList user's list.

MAL's list page shows 192x272 JPG covers. This writes one CSS rule per list entry that
points the card at MAL's own CDN in a larger WebP size instead. Only the user's own
entries are included, so the file stays small (~100 bytes per entry).

Usage: python generate.py [username] [output]   (stdlib only)
"""
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

USER = sys.argv[1] if len(sys.argv) > 1 else "_HyZer"
OUT = sys.argv[2] if len(sys.argv) > 2 else "covers.css"
SIZE = "r/320x452"  # ~1.5x the 210x300 card; ~21 KB WebP. Use "" (original l-size) for full 2x.
PAGE = 300  # MAL's load.json page size
UPDATED_DAYS = 7  # entries changed within this many days get an "UPDATED" chip (anime only: manga has no updated_at)

# Theme extras that live here instead of the MAL custom CSS (which is near MAL's length cap).
# They only rely on markup MAL always renders, plus --updated set per entry below.
EXTRA_CSS = """/* status stripe along the bottom of each cover (ALL view) */
.data.image::before{content:"";position:absolute;left:0;right:0;bottom:0;z-index:2;height:3px;background:hsl(var(--statusColor,var(--accent)));opacity:0}
[data-query*='"status":7'] .data.image::before{opacity:.95}
.list-item:has(.data.status:is(.watching,.reading)){--statusColor:var(--current)}
.list-item:has(.data.status.completed){--statusColor:var(--completed)}
.list-item:has(.data.status.onhold){--statusColor:var(--paused)}
.list-item:has(.data.status.dropped){--statusColor:var(--dropped)}
.list-item:has(.data.status[class*="planto"]){--statusColor:var(--planned)}
/* dim Plan-to-watch covers in the ALL view so watched entries stand out; full colour on hover */
.data.image{transition:filter calc(var(--timeItem)*2) var(--bezierFast)}
[data-query*='"status":7'] .list-item:not(:hover):has(.data.status[class*="planto"]) .data.image{filter:saturate(.3) brightness(.62)}
/* UPDATED chip under the #number for recently changed entries */
.data.image::after{content:var(--updated,none);position:absolute;top:33px;left:12px;z-index:2;padding:1px 6px;background:hsl(var(--accent));border-radius:3px;box-shadow:0 1px 4px hsla(0,0%,0%,50%);color:hsl(var(--bg));font:bold 9.5px/14px var(--font);letter-spacing:1px}
/* list stats above the footer: highlight on hover like the copyright line */
#footer-block{pointer-events:none}
#footer-block #copyright{pointer-events:auto}
.list-unit .list-stats{transition:color var(--timeText) var(--bezierFast)}
.list-unit .list-stats:hover{color:hsla(var(--text),100%)}"""


def fetch(kind, offset):
    url = f"https://myanimelist.net/{kind}list/{USER}/load.json?offset={offset}&status=7"
    req = urllib.request.Request(url, headers={"User-Agent": "mal-covers (github.com/HaydarRizaldy/mal-covers)"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # MAL rate-limits / 5xx now and then
            if attempt == 3:
                raise
            print(f"retry {kind} {offset}: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))


def entries(kind):
    out, offset = [], 0
    while True:
        page = fetch(kind, offset)
        out += page
        if len(page) < PAGE:
            return out
        offset += PAGE
        time.sleep(2)


def hd(path):
    # https://cdn.myanimelist.net/r/192x272/images/anime/1779/143584.jpg?s=... -> .../r/320x452/images/anime/1779/143584.webp
    m = re.search(r"/images/(anime|manga)/(\d+)/(\d+)\.(?:jpg|jpeg|png|webp)", path or "")
    if not m:
        return None  # no cover on MAL (placeholder) -> leave MAL's default
    base = f"https://cdn.myanimelist.net/{SIZE + '/' if SIZE else ''}images/{m[1]}/{m[2]}/{m[3]}"
    return base + (".webp" if SIZE else "l.webp")


def main():
    rules, updated = [], []
    cutoff = time.time() - UPDATED_DAYS * 86400
    for kind in ("anime", "manga"):
        items = entries(kind)
        for it in sorted(items, key=lambda i: i[f"{kind}_id"]):
            link = f'.data.image a[href^="/{kind}/{it[kind + "_id"]}/"]'
            url = hd(it.get(f"{kind}_image_path"))
            if url:
                rules.append(f"{link}{{background-image:url({url})}}")
            if (it.get("updated_at") or 0) > cutoff:
                updated.append(f'.list-item:has({link}){{--updated:"UPDATED"}}')
        print(f"{kind}: {len(items)} entries", file=sys.stderr)

    css = (
        '@charset "UTF-8";\n'
        f"/* Sharper covers for MAL user {USER} - {len(rules)} entries, built "
        f"{datetime.now(timezone.utc):%Y-%m-%d} by github.com/HaydarRizaldy/mal-covers */\n"
        + "\n".join(rules) + "\n"
        + EXTRA_CSS + "\n"
        + "".join(u + "\n" for u in updated)
    )
    old = open(OUT, encoding="utf-8").read() if __import__("os").path.exists(OUT) else ""
    # ignore the header comment (it holds the build date) when deciding whether anything changed
    body = lambda s: [l for l in s.splitlines() if not l.startswith("/*")]
    if body(old) == body(css):
        print("no change", file=sys.stderr)
        return
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(css)
    print(f"wrote {OUT}: {len(rules)} rules, {len(css)} bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
