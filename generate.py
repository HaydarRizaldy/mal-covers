"""Build covers.css: sharper cover images for one MyAnimeList user's anime + manga list.

MAL's list page shows 192x272 JPG covers. This writes one CSS rule per list entry that
points the card at MAL's own CDN in a larger WebP size instead. Only the user's own
entries are included, so the file stays small (~100 bytes per entry).

Usage: python generate.py [username] [output]   (stdlib only)
"""
import html
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


# Public list notes: MAL only shows notes to the logged-in owner, but load.json exposes them.
# Visitors: a NOTES button beside ADD / MORE (only on cards that have a note). Clicking it opens a
# read-only note panel styled like Brink's MORE panel; clicking the panel, MORE, or leaving the card closes it.
# No JS is possible in MAL custom CSS, so:
#  - the button is MAL's empty status cell (td.data.status, hidden by Brink) re-shown and labelled;
#  - "click to open, stay open" is a CSS latch: :active shows the panel instantly, and while the card is
#    hovered the transition back to hidden is delayed for a day; leaving the card hides it at once.
#    The latch hides with `collapse` and the resting state with `hidden` on purpose: if both used the same
#    value, the browser would keep the pending day-long transition when the mouse leaves (same end value).
#    No opacity fade: a click shorter than the fade would freeze it half-way.
# Owner (data-owner="1"): Brink already shows MAL's own NOTES button + inline editor (saves to MAL);
# we only enlarge its text to match.
NOTE_MAX = 400
NOTE_CSS = """[data-owner=""] .add-edit-more:not(:active):after{content:none}
[data-owner=""] .list-table .list-table-data .data.status{display:block;position:absolute;top:7.5px;left:66.5px;z-index:3;width:auto;height:auto;padding:0;background:none;cursor:pointer}
[data-owner=""] .data.status::before{content:var(--noteLabel,none);display:block;padding:4.5px;color:hsl(var(--text));font:12px/15px var(--font);letter-spacing:1px;text-transform:uppercase;transition:color var(--timeText) var(--bezierFast)}
[data-owner=""] .data.status:hover::before,[data-owner=""] .list-item:hover .list-table-data:has(.data.status:active) .data.status::before{color:hsl(var(--textLinkHov))}
[data-owner=""] .list-table-data::after{content:var(--note,none);position:absolute;left:0;top:37px;z-index:30;width:100%;height:calc(100% - 37px);padding:12px 15px;background:hsla(var(--bgAlt),.96);border-radius:6px 6px 0 0;box-shadow:0 0 3.36px 1.68px hsla(0,0%,0%,50%);-webkit-backdrop-filter:blur(var(--imageBlurHov));backdrop-filter:blur(var(--imageBlurHov));color:hsl(var(--text));font:14px/20px var(--font);text-align:left;text-shadow:none;white-space:pre-wrap;overflow:hidden;overflow-wrap:break-word;direction:ltr;cursor:pointer;visibility:hidden;transition:none}
[data-owner=""] .list-item:hover .list-table-data::after{visibility:collapse;transition:visibility 0s 86400s}
[data-owner=""] .list-item:hover .list-table-data:has(.data.status:active)::after{visibility:visible;transition:none}
[data-owner=""] .list-item:hover .list-table-data:active:not(:has(.data.status:active))::after{visibility:collapse;transition:none}
[data-owner="1"] .notes .text,[data-owner="1"] .notes textarea{font-size:14px;line-height:20px;max-height:255px}"""


def css_string(text):
    text = text.strip()
    if len(text) > NOTE_MAX:
        text = text[: NOTE_MAX - 1].rstrip() + "\u2026"
    text = text.replace("\\", "\\\\").replace('"', '\\"').replace("\r\n", "\n").replace("\r", "\n")
    return '"' + text.replace("\n", "\\A ") + '"'


def note_of(it):
    raw = it.get("editable_notes")
    if raw is None:  # fall back to the HTML-escaped field
        raw = html.unescape(it.get("notes") or "")
    return raw.strip()


def main():
    rules, notes = [], []
    for kind in ("anime", "manga"):
        items = entries(kind)
        for it in sorted(items, key=lambda i: i[f"{kind}_id"]):
            link = f'.data.image a[href^="/{kind}/{it[kind + "_id"]}/"]'
            url = hd(it.get(f"{kind}_image_path"))
            if url:
                rules.append(f"{link}{{background-image:url({url})}}")
            note = note_of(it)
            if note:
                notes.append(f'.list-item:has({link}){{--noteLabel:"Notes";--note:{css_string(note)}}}')
        print(f"{kind}: {len(items)} entries", file=sys.stderr)

    css = (
        '@charset "UTF-8";\n'
        f"/* Sharper covers + public notes for MAL user {USER} - {len(rules)} covers, {len(notes)} notes, built "
        f"{datetime.now(timezone.utc):%Y-%m-%d} by github.com/HaydarRizaldy/mal-covers */\n"
        + "\n".join(rules) + "\n"
        + (NOTE_CSS + "\n" + "\n".join(notes) + "\n" if notes else "")
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
