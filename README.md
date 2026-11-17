# gcoos-hfr MCP server

A small MCP server for the public GCOOS HF radar radial files at <https://hfr.gcoos.org/data/>.

The archive layout is `<operator>/<SITE>/raw/{MeasPattern,IdealPattern}/RDL{m,i}_<SITE>_YYYY_MM_DD_HHMM.ruv`.
The files are hourly CODAR SeaSonde LLUV radial maps, kept for a rolling window of about one month.
It has 17 sites, run by the operators gerg, rates and usm.

## Tools

| Tool | What it does |
|---|---|
| `list_sites()` | Lists the sites and the operator of each |
| `list_files(site, pattern="measured", start?, end?, limit=48)` | Lists the hourly files, plus the archive's first and last time |
| `get_radials(site, time?, pattern="measured", max_rows=500, include_flagged=False)` | Parses one hour of radial vectors (the latest by default), plus header metadata and a summary |

Times are ISO 8601 UTC, for example `2026-11-17T13:00Z`. `velocity_cm_s` follows the CODAR convention: a positive value means flow **toward** the radar site.

## Run

```bash
uv run test-mcp              # stdio
```

Claude Code:

```bash
claude mcp add gcoos-hfr -- uv --directory /home/sanzo/test-mcp run test-mcp
```

Set `HFR_BASE_URL` to point the server at a different mirror. It has no dependencies beyond `mcp`, and HTTP goes through the stdlib.
