# OSM fixture

`krakow-main-square.osm.pbf` (70 KB): a tiny OpenStreetMap extract around Kraków's Main
Square for tests of `prepare_otp_inputs` (`--osm-file`, PBF validation, osmium clipping).
It covers the stops of `../gtfs/minimal/` only partly; that is fine for clipping tests.

- Source: Geofabrik `malopolskie-latest.osm.pbf`, replication timestamp 2026-11-13T21:22:20Z.
- Made with: `osmium extract --bbox 19.9370,50.0600,19.9400,50.0625 --strategy complete_ways --set-bounds`
- Content: 4929 nodes, 381 ways, 36 relations; file bbox 19.937,50.06,19.94,50.0625.
- Licence: © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright).
