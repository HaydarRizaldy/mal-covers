# mal-covers

Sharper cover images for the MyAnimeList list of [_HyZer](https://myanimelist.net/animelist/_HyZer).

MAL's list page uses small 192×272 covers. `generate.py` reads the public anime and manga lists and writes
`covers.css`, with one rule per entry pointing at MAL's own CDN in a 320×452 WebP size. A GitHub Action
rebuilds it daily, so newly added entries get sharp covers within a day. Until then they show MAL's default.

Served at: https://haydarrizaldy.github.io/mal-covers/covers.css

Use it in the list's Custom CSS (MAL style: escaped `@\import`, at the top):

```css
@\import "https://haydarrizaldy.github.io/mal-covers/covers.css";
```

Refresh now: Actions → "Update covers" → Run workflow.

GitHub turns off scheduled workflows after 60 days with no repository activity. To prevent that, the job
pushes an empty "Keep daily update alive" commit whenever nothing has been committed for 50 days.
