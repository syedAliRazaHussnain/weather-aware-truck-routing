# Testing

Two layers: automated tests that run in CI on every pull request, and a manual pass through the app as a driver would use it, on a desktop browser and on an iPhone.

## Automated (CI)

| Part | Tool | What it covers |
|---|---|---|
| Backend | pytest (214 tests) | Every band edge in the risk table on both sides, the load rules, road miles and ETAs, checkpoint placement, route alternatives, ranking in the spec's order, the heatmap grid, both API clients against saved real responses (no network), the whole plan with fake services, the HTTP layer, and the production settings |
| Backend | ruff | Lint and formatting |
| Frontend | vitest (39 tests) | Form rules, what every problem button does, error clearing, lb/kg, times in the origin's zone (MST vs MDT), the colour palette, the API client's error handling |
| Frontend | oxlint, `tsc`, `vite build` | Lint, types, production build |

Run them locally:

```bash
cd backend && ruff check . && python -m pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

## Manual, from the driver's point of view

Done on a Mac set to Lahore time (PKT), which also checks that trip times follow the **origin**, not the browser. Desktop: Chrome. Phone: Safari on an iPhone 17 Pro Max simulator.

Live services were used throughout. Weather that couldn't be produced on demand (Severe, No Travel, an outage) was tested by intercepting the API response in the browser and injecting those values, to check what the driver sees.

### Planning a trip

| Check | Desktop | iPhone |
|---|---|---|
| Place search suggests as you type, biased to the map view | ✅ | ✅ |
| Keyboard: arrows move, Enter picks, Escape closes | ✅ | n/a |
| Tap or click a suggestion | ✅ | ✅ |
| Editing a picked place clears it, so a new one must be picked | ✅ | ✅ |
| Clicking a picked place selects its text, so typing replaces it | ✅ | ✅ |
| Plan with empty fields: every missing field named in plain words | ✅ | ✅ |
| Errors disappear as soon as each field is fixed | ✅ | ✅ |
| lb/kg switch converts the number both ways | ✅ | ✅ |
| Load with an extra zero is caught | ✅ | ✅ |
| 10 / 25 / 50 mi changes checkpoint spacing (10 mi: denser dots, bigger heatmap squares and a note) | ✅ | ✅ |
| Leave now uses the current time at the origin (Chicago trip shown in CST, Denver in MST) | ✅ | ✅ |
| Leave later with a local time at the origin | ✅ | ✅ |
| Both places are framed on the map before planning | ✅ | ✅ |

### Results

| Check | Desktop | iPhone |
|---|---|---|
| Up to 3 routes; recommended selected and coloured, others faded | ✅ | ✅ |
| Reason line (e.g. "0 Severe miles vs 167 on Route A. 3 h 28 min slower than the fastest.") | ✅ | ✅ |
| Route cards: time, distance, extra time vs fastest, risky miles, risk bar | ✅ | ✅ |
| Select a route by card or by clicking its line on the map | ✅ | ✅ (card scrolls up to the map) |
| Checkpoint popup: mile, ETA with zone, level and cause, wind/gusts/rain/snow, "raised from High by your load" | ✅ | ✅ |
| Severe and No Travel checkpoints ringed in red | ✅ | ✅ |
| Heatmap slider 0-48 h, labelled with day and time in the origin's zone | ✅ | ✅ |
| Slider stays smooth (each hour repainted within one frame) | ✅ | ✅ |
| Long-trip note about rest stops | ✅ | ✅ |
| Results come into view after planning on a phone | n/a | ✅ |

### When something goes wrong

| Situation | What the driver sees | Button works |
|---|---|---|
| Departure in the past | "That departure time has passed." | [Leave now] re-plans at the current origin time ✅ |
| Same origin and destination | "The origin and destination are the same place." | [Pick a different destination] focuses the field ✅ |
| Trip too long or across the sea (Chicago to London) | "This trip is too long for the free routing service ... or it crosses the sea." | ✅ |
| No road near a point (injected) | "There's no truck road near your destination." | [Use Rawlins, WY (2 mi away)] fills it in and re-plans ✅ |
| Every route No Travel (injected) | Warning on purple routes | [Check tomorrow 6 AM] sets that time and re-plans ✅ |
| Weather service busy (injected) | Routes in grey, "Weather unknown", no recommendation | Retries once by itself after a countdown, then waits for a tap ✅ |
| Server can't be reached | "We couldn't reach the server. Your trip details are kept." | [Try again] ✅ |

## Bugs found by this pass, and fixed

1. Checkpoint dots were hard to click: added a larger invisible hit area, gave dots priority over the line, and a pointer cursor.
2. Faded routes were hard to click: added a wide invisible hit line.
3. Before planning, the map showed only the destination: it now frames both places.
4. The first place search wasn't biased to the map: it now uses the map's starting view.
5. Retry countdown could repeat forever while a service stayed busy: now one automatic retry, then manual.
6. Typing into a picked place appended text: the text is now selected on focus.
7. "You're offline" was shown when only the server was down: now says the server couldn't be reached unless the browser really is offline.
8. The too-long message suggested "a city about halfway" even for trips across the sea: reworded.
9. The reason line said "fastest" twice when routes tied on risk: reworded.
10. iPhone: Safari zoomed the page when an input was focused (inputs under 16 px): inputs are now 16 px.
11. iPhone: autocorrect "fixed" place names: turned off for place inputs.
12. iPhone: the slider and legend covered the routes on a small map: routes are framed above them and the overlay is compact.
13. iPhone: results were below the fold after planning, and tapping a card left the map off-screen: results scroll into view, and picking a route scrolls back to the map.
