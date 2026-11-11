# lepszejakdojade — product concept

A web app for public transport in **Kraków and Warsaw**. It plans journeys, shows timetables,
suggests and sells (demo) tickets, and answers questions through an AI assistant.
Built as a recruitment project demonstrating development with AI tools; not a commercial product.
On first visit the user picks a city (Kraków or Warsaw); the choice is remembered.

## 1. Journey search A→B
- Start and destination: address, stop, point on the map, or "my location".
- Time: "depart at…" or "arrive by…".
- Results include buses, trams, metro (Warsaw) and agglomeration trains, with transfers and walking.
- Each result shows total duration, number of transfers, walking distance and the route on the map.
- Comparison with cycling and walking (e.g. "by bike 14 min").
- Preferences: fewer transfers, less walking, wheelchair-accessible vehicles only.
- Ticket suggestion under each result (e.g. "a 60-minute ticket, zone I is enough").
- Engine: OpenTripPlanner 2 (no custom routing code).

## 2. Timetable browser
Three steps:
1. **Vehicle type** — tabs at the top: Trams / Buses / Metro / Trains, only those that exist in the selected city (Kraków has no metro). Last tab remembered.
2. **Line** — grid of tiles with line numbers, sorted ascending and grouped (day, night, suburban, replacement/temporary), each group in its own colour.
   - Search box filters tiles while typing.
   - Logged-in users see favourite lines at the top.
   - Lines with a detour or timetable change show a warning badge.
3. **Direction and stop**
   - Toggle between the two directions (e.g. "→ Czerwone Maki | → Mistrzejowice").
   - Vertical line diagram like the one in vehicles: stops connected by a line, transfer line numbers next to each stop.
   - Map with the route alongside; clicking a stop on the diagram or map opens its timetable.
   - Route variants (short turns, depot runs) marked at the stops they affect.

**Stop timetable** (one line at one stop):
- Hours as rows, minutes next to them, three columns: weekdays, Saturdays, Sundays & holidays.
- Next departure highlighted; past departures dimmed.
- Markers on minutes: low-floor, short-turn, other route variant; legend below.
- Date picker shows the timetable for a specific day (holidays, school breaks, changes).
- Quick switch to the opposite direction and to previous/next stop.
- Clicking a minute shows the whole trip with times at following stops.
- Print / PDF version.

**Entry from a stop:** type a stop name (colloquial names too) and see all lines stopping there, grouped like the tabs, with directions; on top a combined board of next departures for all lines.

Kraków and Warsaw use the same views; they differ only in tabs and line group colours.

## 3. Tickets
- Ticket catalogue per city: time-based, single, daily, periodic, standard and reduced, by zone.
- Prices show an "as of" date and a link to the official source. Stored in the database, editable in admin.
- **Demo purchase**: account, test payment (Stripe test mode or PayU sandbox), QR ticket clearly labelled "demo ticket, not valid on vehicles".

## 4. AI assistant (chat)
- Answers natural-language questions: "How do I get to AGH by 8:00?", "When is the next 52 from Bagatela?", "Which ticket for the airport?", "Is the 4 late?".
- Understands colloquial place and stop names.
- Answers **only from app data** (journeys, timetables, tickets, live data) via tools, never from memory. Says plainly when it does not know.
- Can show cards (journey, departures, ticket) instead of plain text.
- Runs on the Gemini API (free tier), with per-user rate limits; the model is swappable.

## 5. Live data and delay prediction
- Where the city provides data: realtime departures on stop boards ("scheduled 8:14, expected 8:17") and a live vehicle map.
- The app continuously collects delay data and computes statistics: typical delay of a line at a stop at a given time, a weekday × hour heatmap, the most delayed segments.
- A machine-learning model predicts the delay at your stop and rates transfer risk ("you miss this transfer in 35% of cases"), offering a safer route.
- Every prediction shows how much data it is based on; with too little data no prediction is shown.
- Kraków: full realtime data. Warsaw: vehicle positions; delays are computed from them. Trains: delays from PKP PLK via a community feed that can stall; the app falls back to the schedule.

## 6. User account
- With an account: favourite journeys, stops and lines; search history limited to the last N searches (default 50); purchased demo tickets.
- Without an account: only search history, stored in the browser.
- Journey search, timetables and chat work without logging in.

## 7. Language (Polish / English)
- Language switcher (PL / EN) in the header, available on every page, with or without an account.
- First visit: language taken from the browser; then the choice is remembered (browser; for logged-in users also on the account).
- Translated: the whole interface, error messages, ticket names and descriptions, the data sources page, demo ticket labels, e-mails.
- Dates, times, numbers and prices formatted for the selected language.
- The AI assistant answers in the selected language (and understands questions in either language).
- Not translated: stop, street and place names (proper names). Service alerts from transport authorities are shown in their original language (usually Polish) with a short note in English mode.

## 8. Other
- "Data sources" page with required licence attributions (ZTP Kraków, ZTM Warszawa, WKD, PKP PLK, OpenStreetMap, mkuran.pl where used).
- City is configuration: adding a city (e.g. Szczecin) means a new config, not new code.
- Responsive web app that works well on phones.
