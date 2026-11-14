# OpenTripPlanner 2

OTP 2 serves exactly one graph per instance, so each city runs its own OTP container
(image `opentripplanner/opentripplanner:2.6.0`) with its own data directory.

## Layout

```
otp/
  config/                     # shared, city-agnostic defaults (committed)
    build-config.json
    router-config.json
    otp-config.json
  <city>/                     # optional per-city overrides (committed), deep-merged
    build-config.json         #   over config/; lists are replaced, not merged
  queries/<city>-sample.graphql
  data/                       # git-ignored, written by prepare_otp_inputs and OTP
    <city>/
      build-config.json       # generated: shared + override + feeds/OSM/time zone
      router-config.json
      otp-config.json
      <feed id>.gtfs.zip      # every static GTFS feed of the city with a URL
      <city>.osm.pbf          # regional OSM extract clipped to the served area
      prepare-report.json     # URLs, sha256, download times, bbox used
      graph.obj               # written by `otp --build --save`
      cache/                  # unclipped regional extract + download metadata
```

City-specific values never live in these files: feed ids and files, the OSM file and
the time zone are added by `prepare_otp_inputs` from `backend/cities/config/<city>.yaml`
(`feeds.gtfs_static`, `timezone`, `otp.osm_url`, optional `otp.bbox`). Feeds with
`url: null` are skipped.

## Rebuilding a graph

1. Prepare the inputs (downloads are conditional, failed downloads keep the previous file):

   ```sh
   python manage.py prepare_otp_inputs --city krakow
   ```

   The OSM extract is clipped with `osmium extract --strategy complete_ways` to the bbox of
   all GTFS stops plus 3 km (`--buffer-km`, setting `OTP_BBOX_BUFFER_KM`) unless the city
   config sets `otp.bbox`. This needs `osmium-tool` on the PATH; `--no-clip` uses the whole
   regional extract instead (works, but needs more heap and build time).

   - Download limits: GTFS feeds use `TRANSIT_GTFS_MAX_BYTES` (1 GB) and
     `TRANSIT_GTFS_DOWNLOAD_MAX_SECONDS` (900 s); the OSM extract uses `OTP_OSM_MAX_BYTES`
     (2 GB) and `OTP_OSM_DOWNLOAD_MAX_SECONDS` (1800 s).
   - The clip bbox is sanity-checked: wider than 2 degrees in either axis, or reaching
     beyond the bounds in the extract's PBF header, gives a warning (output and
     `prepare-report.json`), not an error.
   - One run per city at a time: `cache/prepare.lock`. A hard-killed run can leave it
     behind; the error message names it, delete it once no run is active.
   - `--osm-file` must be the regional extract, not the prepared `<city>.osm.pbf`.

2. Build and save the graph (the image's entrypoint passes `/var/opentripplanner/`):

   ```sh
   docker run --rm -e JAVA_OPTS=-Xmx4G \
     -v "$PWD/otp/data/krakow:/var/opentripplanner" \
     opentripplanner/opentripplanner:2.6.0 --build --save
   ```

3. Serve it:

   ```sh
   docker run --rm -e JAVA_OPTS=-Xmx2G -p 8080:8080 \
     -v "$PWD/otp/data/krakow:/var/opentripplanner" \
     opentripplanner/opentripplanner:2.6.0 --load --serve
   ```

   `router-config.json` and `otp-config.json` are read again at `--load`, so routing
   defaults can be changed without a rebuild. Health: `GET /otp/actuators/health`.

Rebuild whenever a GTFS feed changes (Warsaw's feed is a rolling window, so daily).

Measured on 2026-11-14 (8 CPUs, OTP 2.6.0):

| City | Inputs | Build + save | Build heap | graph.obj | Serve heap (RSS) | Load |
|---|---|---|---|---|---|---|
| krakow | 3 GTFS (31 MB), OSM clipped 204 -> 72 MB | 4 min 11 s | `-Xmx4G` (peak RSS 3.5 GB) | 122 MB | `-Xmx2G` (1.0 GB) | 17 s |
| warszawa | 2 GTFS (99 MB), OSM clipped 302 -> 134 MB | 8 min 21 s | `-Xmx7G` (peak RSS 7.4 GB) | 244 MB | `-Xmx3G` (1.8 GB) | 33 s |

Direct transfers are walk-only (plus wheelchair) and capped at 15 minutes; adding bicycle
transfers and a 30-minute cap made the Kraków build 10x more transfers, 6.4 GB RSS and a
343 MB graph.

## Sample query

GTFS GraphQL API (`planConnection`), endpoint `/otp/gtfs/v1`. The body can be sent raw:

```sh
curl -s -H "Content-Type: application/graphql" \
  --data-binary @otp/queries/krakow-sample.graphql http://localhost:8080/otp/gtfs/v1
```

Without variables the search starts now. A fixed time needs a JSON body with variables:
`{"query": "<file contents>", "variables": {"dateTime": {"earliestDeparture": "2026-11-16T08:00:00+01:00"}}}`.
An interactive GraphiQL client is at `http://localhost:8080/graphiql`.
