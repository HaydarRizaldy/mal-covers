"""Build covers.css: sharper cover images (+ theme extras) for one MyAnimeList user's list.

MAL's list page shows 192x272 JPG covers. This writes one CSS rule per list entry that
points the card at MAL's own CDN in a larger WebP size instead. It also carries theme
extras (see EXTRA_CSS) and a few per-entry / per-list values that CSS can't compute:
"UPDATED" chips, your-score-vs-MAL, the list stats text and a score-distribution chart.

Note on the cascade: this file is @imported at the top of the MAL custom CSS, so on equal
specificity the theme wins. Overrides here therefore use a slightly more specific selector.

Usage: python generate.py [username] [output]   (stdlib only)
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

USER = sys.argv[1] if len(sys.argv) > 1 else "_HyZer"
OUT = sys.argv[2] if len(sys.argv) > 2 else "covers.css"
SIZE = "r/320x452"  # ~1.5x the 210x300 card; ~21 KB WebP. Use "" (original l-size) for full 2x.
PAGE = 300  # MAL's load.json page size
UPDATED_DAYS = 7  # entries changed within this many days get an "UPDATED" chip (anime only: manga has no updated_at)
# Bulk tag edit on 2026-11-10 bumped updated_at on ~212 entries; ignore changes up to the end of that run
# so the chip only marks real updates. (Harmless once 7 days have passed.)
UPDATED_NOT_BEFORE = 1794306500  # end of the bulk tag run (2026-11-10)
GEM_DIFF = 2.0  # your score this far above MAL's average turns the TOP RATED tab into "HIDDEN GEM"
UA = {"User-Agent": "mal-covers (github.com/HaydarRizaldy/mal-covers)"}

# Top-8 tags (by frequency in this list) -> validated dark categorical palette, fixed slot order
# (dataviz reference palette, dark column: worst adjacent CVD dE 8.4, normal-vision >= 15).
# Every tag also shows its name, so colour is never the only cue. Other tags stay neutral.
TAG_COLOURS = [("Romance", "#3987e5"), ("Comedy", "#d95926"), ("School", "#199e70"), ("Shounen", "#c98500"),
               ("Seinen", "#d55181"), ("Drama", "#008300"), ("Ecchi", "#9085e9"), ("Action", "#e66767")]
CHART_FILL = "hsl(243,32%,78%)"  # theme accent (Twilight Indigo lavender); single series -> single hue

# Theme extras that live here instead of the MAL custom CSS (which is near MAL's length cap).
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
[data-query*='"status":7'] .list-item:not(:hover):not(:focus-within):has(.data.status[class*="planto"]) .data.image{filter:saturate(.3) brightness(.62)}
/* UPDATED chip under the #number for recently changed entries */
.data.image::after{content:var(--updated,none);position:absolute;top:33px;left:12px;z-index:2;padding:1px 6px;background:hsl(var(--accent));border-radius:3px;box-shadow:0 1px 4px hsla(0,0%,0%,50%);color:hsl(var(--bg));font:bold 9.5px/14px var(--font);letter-spacing:1px}
/* your score vs MAL, in the hover info: "+2.6 above" / "MAL: 7.40" (per-entry --diff / --diffColor) */
body .data.mal_score::before{content:var(--diff,"") "MAL: ";color:hsl(var(--diffColor,var(--text)));white-space:pre-line}
/* PLANNED tab: show MAL score + season on the card face instead of the word "Planned" */
[data-query*='"status":6'] .list-item .data.score{display:none}
[data-query*='"status":6'] .list-item .data.mal_score,.anime[data-query*='"status":6'] .list-item .data.season{position:absolute;left:12px;z-index:10;max-width:calc(100% - 70px);margin:0;opacity:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-query*='"status":6'] .list-item .data.mal_score{bottom:12px}
.anime[data-query*='"status":6'] .list-item .data.season{bottom:29px}
.anime[data-query*='"status":6'] .list-item .data.title{padding-bottom:44px !important}
/* both stats lines (top + footer) show the SAME generated line: "Scores 1-10 [chart]  TV: ..., Episodes: ..."
   (refreshed daily). MAL's own footer text is hidden because it abbreviates "Eps", which CSS can't rewrite;
   its "More stats" link (the full table) stays, after the text. Both highlight on hover like the copyright. */
#footer-block{pointer-events:none}
#footer-block #copyright{pointer-events:auto}
body .list-unit .list-stats,body .list-unit .list-status-title .text{display:flex !important;flex-wrap:wrap;justify-content:center;align-items:center;row-gap:2px;height:auto;color:hsla(var(--text),40%);font-size:0 !important;line-height:16px;transition:color var(--timeText) var(--bezierFast)}
body .list-unit .list-stats:hover,body .list-unit .list-status-title .text:hover{color:hsla(var(--text),100%)}
body .list-unit .list-stats::before,body .list-unit .list-status-title .text::before{content:var(--chartLabel,none);margin-right:14px;padding-right:110px;background:var(--scoreChart) right center/100px 14px no-repeat;font:12px/16px var(--font);white-space:nowrap}
body .list-unit .list-stats::after,body .list-unit .list-status-title .text::after{content:var(--statsText,none);max-width:100%;font:12px/16px var(--font);text-align:center}
body .list-unit .list-stats>span:not(:has(>a.floatRightHeader)){display:none}
body .list-unit .list-stats>span:has(>a.floatRightHeader){order:2;margin-left:12px}
body .list-unit .list-stats a.floatRightHeader{display:inline;float:none;padding:0;color:inherit;font:12px/16px var(--font);white-space:nowrap}
body .list-unit .list-stats a.floatRightHeader:hover{color:hsl(var(--textLinkHov))}
/* the top copy sits under the tabs */
body .list-block{padding-top:88px}
body .list-unit .list-status-title .text{position:absolute;top:42px;left:0;width:calc(var(--listW) - 40px);min-height:16px;pointer-events:auto;cursor:default}
/* the tabs' hidden 0px-font label text still takes a 30px line box that spills below each button and
   stole the mouse from the stats line; clip the buttons to their own box */
body #status-menu .status-button{overflow:hidden}
/* favourites first (default sort only; a chosen Order puts "order" into data-query) */
body:not([data-query*='"order"']) .list-item:has(.data.tags a[href*="=Favourite"]){order:-1}
/* hidden gems: per-entry --topLabel/--gemRated/--gemToggle turn the TOP RATED tab into a lavender HIDDEN GEM tab */
body .data :is(.score-8,.score-9,.score-10)::after{content:var(--topLabel,"\\f005  TOP RATED")}
body .data .score-10{--rated:var(--gemRated,var(--goldRating))}
body .data .score-9{--rated:var(--gemRated,var(--silverRating));--toggle:var(--gemToggle,var(--toggleTopRatingSilver))}
body .data .score-8{--rated:var(--gemRated,var(--bronzeRating));--toggle:var(--gemToggle,var(--toggleTopRatingBronze))}
/* keyboard: show a card's details while anything inside it has focus, like hover does */
.list-item:focus-within{transform:scale(1)}
.list-item:focus-within .data:not(.image),.list-item:focus-within .add-edit-more,.list-item:focus-within .notes,.list-item:focus-within .malicon,.list-item:focus-within .data.tags a{opacity:1}
.list-item:focus-within .data.image .link{filter:brightness(var(--imageBrightnessHov)) opacity(var(--imageBrightnessHov)) blur(var(--imageBlurHov))}
.list-item:focus-within .data.tags span a[href*="=Favourite"]:not(:focus){opacity:0}
.list-item :focus-visible{outline:2px solid hsl(var(--accent));outline-offset:2px;border-radius:3px}
/* reduced motion: no card zoom, no blur; near-zero durations (delays kept, so the NOTES click latch still works) */
@media (prefers-reduced-motion:reduce){
body .list-item,body .list-item:is(:hover,:focus-within){transform:scale(.95)}
body .list-item:is(:hover,:focus-within) .data.image .link{filter:brightness(var(--imageBrightnessHov)) opacity(var(--imageBrightnessHov))}
body .more-content,body .notes .text,body .notes textarea{-webkit-backdrop-filter:none!important;backdrop-filter:none!important}
*,*::before,*::after{transition-duration:.01ms!important;animation-duration:.01ms!important;animation-iteration-count:1!important}}
body .list-unit .loading-space{pointer-events:none}
@media (max-width:926px){body .list-block{padding-top:152px;padding-bottom:80px}body .list-unit .list-status-title .text{left:calc(238px - 50vw);width:calc(100vw - 40px)}}"""


def get(url, as_json=False):
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r) if as_json else r.read().decode("utf-8", "replace")
        except Exception as e:  # MAL rate-limits / 5xx now and then
            if attempt == 3:
                raise
            print(f"retry {url}: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))


def entries(kind):
    out, offset = [], 0
    while True:
        page = get(f"https://myanimelist.net/{kind}list/{USER}/load.json?offset={offset}&status=7", as_json=True)
        out += page
        if len(page) < PAGE:
            return out
        offset += PAGE
        time.sleep(2)


def css_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def hd(path):
    # https://cdn.myanimelist.net/r/192x272/images/anime/1779/143584.jpg?s=... -> .../r/320x452/images/anime/1779/143584.webp
    m = re.search(r"/images/(anime|manga)/(\d+)/(\d+)\.(?:jpg|jpeg|png|webp)", path or "")
    if not m:
        return None  # no cover on MAL (placeholder) -> leave MAL's default
    base = f"https://cdn.myanimelist.net/{SIZE + '/' if SIZE else ''}images/{m[1]}/{m[2]}/{m[3]}"
    return base + (".webp" if SIZE else "l.webp")


def stats_text(kind):
    """The visible text of MAL's footer stats line, e.g. 'TV: 415, ..., Mean Score: 7.6, Score Dev.: 0.07'."""
    page = get(f"https://myanimelist.net/{kind}list/{USER}")
    m = re.search(r'<div class="list-stats">(.*?)</div>', page, re.S)
    if not m:
        return None
    inner = re.sub(r'<span>\s*<a class="floatRightHeader".*?</span>', "", m.group(1), flags=re.S)
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", inner))).strip(" ,")
    # write MAL's abbreviations in full
    for short, full in ((r"\bSpcl\.", "Specials"), (r"\bEps\b", "Episodes"), (r"\bDev\.", "Deviation")):
        text = re.sub(short, full, text)
    return text or None


def score_chart(scores):
    """Tiny single-series bar chart (scores 1..10) as an SVG data URI; 4px-wide... thin bars, 2px gaps, baseline."""
    counts = [scores.count(s) for s in range(1, 11)]
    top = max(counts) or 1
    bars = []
    for i, c in enumerate(counts):
        h = max(1, round(13 * c / top))  # 1px stub keeps empty scores visible on the baseline
        bars.append(f'<rect x="{i * 10}" y="{14 - h}" width="8" height="{h}" rx="1.5"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="14" viewBox="0 0 100 14">'
           f'<g fill="{CHART_FILL}">{"".join(bars)}</g></svg>')
    return 'url("data:image/svg+xml,' + urllib.parse.quote(svg, safe=" =:/,") + '")', counts


def main():
    rules, per_entry, lists = [], [], []
    cutoff = max(time.time() - UPDATED_DAYS * 86400, UPDATED_NOT_BEFORE)
    for kind in ("anime", "manga"):
        items = entries(kind)
        for it in sorted(items, key=lambda i: i[f"{kind}_id"]):
            link = f'.data.image a[href^="/{kind}/{it[kind + "_id"]}/"]'
            url = hd(it.get(f"{kind}_image_path"))
            if url:
                rules.append(f"{link}{{background-image:url({url})}}")
            props = []
            if (it.get("updated_at") or 0) > cutoff:
                props.append('--updated:"UPDATED"')
            diff, mal = it.get(f"{kind}_score_diff"), it.get(f"{kind}_score_val") or 0
            if it.get("score") and mal and diff is not None:
                d = round(float(diff), 1)
                if d > 0:
                    txt, col = f"+{d:.1f} above", "var(--current)"
                elif d < 0:
                    txt, col = f"\\2212 {abs(d):.1f} below", "var(--dropped)"
                else:
                    txt, col = "\\00B1 0 same as", "var(--planned)"
                props.append(f'--diff:"{txt}\\A ";--diffColor:{col}')
                if round(float(diff), 2) >= GEM_DIFF:
                    props.append('--topLabel:"\\f219  HIDDEN GEM";--gemRated:var(--accent);--gemToggle:visible')
            if props:
                per_entry.append(f".list-item:has({link}){{{';'.join(props)}}}")
        scored = [it["score"] for it in items if it.get("score")]
        chart, counts = score_chart(scored)
        st = stats_text(kind)
        lists.append(f"body.{kind}{{" + (f"--scoreChart:{chart};--chartLabel:\"Scores 1\\2013 10\"" if scored else "--chartLabel:none") + (f";--statsText:{css_string(st)}" if st else "") + "}")
        print(f"{kind}: {len(items)} entries, scores 1-10 = {counts}, stats = {st!r}", file=sys.stderr)
        time.sleep(2)

    tags = "\n".join(f'body .data.tags span a[href$="tag={urllib.parse.quote_plus(t)}"]::after{{color:{c}}}' for t, c in TAG_COLOURS)
    css = (
        '@charset "UTF-8";\n'
        f"/* Sharper covers + theme extras for MAL user {USER} - {len(rules)} covers, built "
        f"{datetime.now(timezone.utc):%Y-%m-%d} by github.com/HaydarRizaldy/mal-covers */\n"
        + "\n".join(rules) + "\n"
        + EXTRA_CSS + "\n"
        + "/* tag colours (icon only) */\n" + tags + "\n"
        + "\n".join(lists) + "\n"
        + "".join(p + "\n" for p in per_entry)
    )
    old = open(OUT, encoding="utf-8").read() if __import__("os").path.exists(OUT) else ""
    # ignore the header comment (it holds the build date) when deciding whether anything changed
    body = lambda s: [l for l in s.splitlines() if not l.startswith("/*")]
    if body(old) == body(css):
        print("no change", file=sys.stderr)
        return
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(css)
    print(f"wrote {OUT}: {len(rules)} covers, {len(per_entry)} per-entry rules, {len(css)} bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
