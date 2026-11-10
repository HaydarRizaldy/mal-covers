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
# Cards with a note get a "NOTES" label after their "#N"; hovering it shows the note.
# The label never changes on hover and the panel is drawn on a different element
# (.list-table-data::after, pointer-events:none), so nothing moves under the cursor.
NOTE_MAX = 400
NOTE_CSS = """.data.number::after{content:var(--noteLabel,none);margin-left:6px;color:hsl(var(--accent));font:bold 10px/15px var(--font);letter-spacing:1px;vertical-align:top}
.list-item .data.number:hover{opacity:1}
.list-table-data:has(.data.number:hover)::after{content:var(--note,none);position:absolute;top:34px;left:8px;z-index:40;width:194px;max-height:240px;overflow:hidden;padding:9px 12px 11px;background:hsla(var(--bgAlt),.97);border-left:2px solid hsl(var(--accent));border-radius:0 6px 6px 0;box-shadow:0 0 3.36px 1.68px hsla(0,0%,0%,50%);color:hsl(var(--text));font:normal 12px/16px var(--font);text-align:left;text-shadow:none;white-space:pre-wrap;overflow-wrap:break-word;direction:ltr;pointer-events:none}
[data-owner=""] .add-edit-more:not(:active):after{content:none}
[data-owner="1"] .data.number::after,[data-owner="1"] .list-table-data:has(.data.number:hover)::after{content:none}"""


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
                notes.append(f'.list-item:has({link}){{--noteLabel:"NOTES";--note:{css_string(note)}}}')
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
