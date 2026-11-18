# HF radar MCP server

MCP server for the GCOOS HF radar network. It answers questions about site status,
diagnosis findings, measurements, outages, radial vectors and surface currents.

## hfradmin API (default)

The server reads the read-only hfradmin JSON API described in
[docs/API_V1.md](docs/API_V1.md). No credentials are needed for now.

```bash
uv run test-mcp
```

| Variable | Default | Purpose |
|---|---|---|
| `HFR_API_URL` | `https://hfr.gcoos.org/api/v1` | API base URL (use it for a staging host) |
| `HFR_API_TOKEN` | unset | Sent as `Authorization: Bearer ...` if the API ever requires it |

Transport is stdio. Authentication, if added, is a change to `HfrApi.headers()` only.

## Tools

| Tool | Answers | API routes |
|---|---|---|
| `network_overview()` | Data freshness and the state of every site (with position, frequency, data age) | `/meta`, `/status` |
| `get_site(site)` | One site: status, TX settings, open outages and findings | `/sites/{site}` |
| `get_findings(status, site, rule, severity, since, limit)` | What is wrong, worst first | `/findings` |
| `get_rules()` | Rule meanings, thresholds, possible causes (cached 1 h) | `/rules` |
| `list_diagnostic_fields(search)` | Field codes for diagnostics (cached 1 h) | `/diagnostics/catalog` |
| `get_diagnostics(site, fields, start, end, resolution, pattern, max_rows)` | Measurement series with a summary; rows thinned to `max_rows` | `/sites/{site}/diagnostics` |
| `get_history(kind, site, start, end, status, limit)` | `outages`, `annotations` or `settings_changes` | `/outages`, `/annotations`, `/sites/{site}/settings-history` |
| `list_radial_files(site, start, end, pattern, limit)` | Coverage and gaps, newest first | `/sites/{site}/radials` |
| `get_radials(site, filename, time, pattern, max_rows)` | Header and vectors of one hourly file (latest by default) | `/radials/{filename}`, `/radials/{filename}/vectors` |
| `get_surface_currents(source, lat, lon, hours)` | Total-current sources, or one cell's time series | `/totals`, `/totals/{source}/cell` |

Times are ISO 8601 UTC (`2026-11-17T13:00Z` or `2026-11-17`); the server sends them to the
API as `2026-11-17T13:00:00Z`. Radial files reach the database in batches every few hours,
so check `network_overview().freshness` before calling a site down.
`velocity` follows the CODAR convention: positive means flow **toward** the radar site.

## Archive mode (fallback)

Until the API is in production, the previous file-archive server is still available as
`test-mcp-archive`. It reads `.ruv` files from <https://hfr.gcoos.org/data/> (override with
`HFR_BASE_URL`) or from the HFRNet S3 archive (`HFR_DATA_PATH=s3://...`) and offers
`list_sites`, `list_files` and `get_radials`.

```bash
uv run test-mcp-archive
```

## Development checks

```bash
uv sync
uv run python -m unittest discover -s tests -v
```

API tests use a fake transport, so they run without network access.
