# Design: strava-dashboard
Chosen 2026-10-23 by Martin: **A2 "Logbook, Strava orange"**: light, table-first layout with Strava-style orange.
Canvas (private, for Martin): https://claude.ai/artifact/1ajnh1ZBL2wfpKTQrSAhs7 (rows A and A2; A2 is the choice).
Reference mockups (synthetic data) in the repo: `docs/design/segment-page.dc.html`, `docs/design/ride-page.dc.html`.
They are mockup markup, not production code: re-implement in `web/` (plain TS + CSS), keep the look.

Light only (no dark mode). No Strava logo or name anywhere: only the colour.

## Tokens (CSS custom properties in `web/src/styles/tokens.css`)
| Token | Value | Use |
|---|---|---|
| `--bg` | `#F7F7FA` | page background |
| `--surface` | `#FFFFFF` | panels, header |
| `--ink` | `#242428` | text, dark buttons (active sort), today marker on ride page |
| `--muted` | `#5E5E6A` | secondary text, column headers, labels |
| `--line` | `#DFDFE8` | panel borders, header rule |
| `--line-soft` | `#F0F0F5` | row separators |
| `--grid` | `#ECECF2` | chart gridlines |
| `--control-line` | `#C4C4CF` | outlined buttons, chart axes |
| `--orange` | `#FC4C02` | brand: wordmark, active nav underline, links, PR (badge bg, PR time, PR chart dot, best-year time), "NEW PR" chip |
| `--orange-hover` | `#D63F00` | link hover |
| `--effort` | `#8A8A96` | normal effort dots in charts, average tick |
| `--rank2` / `--rank3` | `#242428` / `#8A8A96` | outlined "2nd" / "3rd" badges |

Accessibility note (Martin's choice, 2026-10-23): orange `#FC4C02` is ~3:1 against white. Keep orange text at ≥ 14 px
semibold or larger (links, PR time), and white-on-orange badges bold. Never use orange as the only signal: PR rows also
say "PR" in text.

## Type
- One family: **Public Sans** (Google Fonts, weights 400/500/600/700/800), `font-variant-numeric: tabular-nums` on the root
  so times line up. Self-host the woff2 files in `web/public/fonts/` (no runtime call to Google).
- Sizes: body 15 px; h1 32 px / 700 / letter-spacing −0.02em; panel headings 15 px / 600; stat values 26–28 px / 500;
  column headers and stat labels 12 px uppercase, letter-spacing 0.06em, `--muted`; wordmark 18 px / 800, orange.

## Layout
- Content column `max-width: 1120px`, side padding 24 px (16 px under 480 px), page padding 32 px top.
- Header: white bar, wordmark "Segment Log" left, nav "Segments · Rides"; active item has a 3 px orange underline.
- Panels: white, 1 px `--line` border, square corners, header row with title left and controls right.
- Wide tables sit in an `overflow-x: auto` box; side-by-side panels wrap (flex-wrap) on narrow screens.
- Touch targets ≥ 36 px high for sort toggles, ≥ 44 px for "Show all" buttons.

## Screens
### Segment page (`#/segment/<slug>`), see `docs/design/segment-page.dc.html`
1. Back link "← All segments", h1 segment name, meta line "2.40 km · N efforts · first ridden <date>".
2. Summary strip (4 cells, auto-fit grid): Personal record (orange time, date, km/h) · Median (+gap to PR) ·
   Latest (date, +gap to PR) · This year (count, best).
3. "Time by date" chart: Chart.js scatter, x = date (year ticks), y = elapsed time reversed (faster is higher),
   efforts `--effort`, PR as a larger orange dot with a white ring and a "PR m:ss" label.
4. Two panels side by side: **All efforts** (sort toggle Fastest/Newest; columns Rank, Date, Ride (link), Time, km/h,
   Gap; rank 1 = orange "PR" badge, 2 = "2nd" outlined ink, 3 = "3rd" outlined grey; first 12 rows, then
   "Show all N efforts") and **By year** (Year, Efforts, Best; the PR year's best in orange).
5. Empty state: "No efforts on this segment yet." in place of chart and tables.

### Ride page (`#/ride/<id>`), see `docs/design/ride-page.dc.html`
1. Back link "← All rides", h1 ride name, meta "Sun 18 Oct 2026, 17:05 · <gear>". All dates and times are shown in
   Europe/Bratislava time (D-007), never the viewer's zone.
2. Summary strip: Distance · Moving time · Elapsed time · Segments (with "N new PR" in orange when > 0).
3. Panel **Segments on this ride**, one row per effort: Segment (link, "NEW PR" chip if PR at the time) · Today ·
   PR · Average · vs PR · position bar (track from PR on the left to slowest on the right, grey tick = average,
   dot = today: orange if PR, else ink) · Rank "8 / 24". Legend in the panel header.
4. Empty state: "No segments matched on this ride."

### Index (`#/`), not mocked up; build from the same parts
- Header + h1 "Segments" panel table: Name (link), Efforts, PR time (orange), PR date. Empty state explains
  `sdash segment add`.
- "Rides" panel table, newest first: Date, Name (link), km, Segments matched. Show 50, then "Show all".

### Not found
Unknown route: h1 "Not found" + link back to the index.
