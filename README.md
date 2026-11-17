# HF radar MCP server

Read CODAR SeaSonde radial data through MCP using either source below.

## 1. GCOOS over HTTP (default)

Use the public archive at <https://hfr.gcoos.org/data/>. No AWS credentials needed.

```bash
uv run test-mcp
```

For a mirror, set `HFR_BASE_URL`:

```bash
HFR_BASE_URL=https://mirror.example/data/ uv run test-mcp
```

Mirrors must serve Caddy JSON listings with the layout
`<operator>/<SITE>/raw/{MeasPattern,IdealPattern}/<file>.ruv`.

## 2. HFRNet radials over S3

Use your AWS credentials or `AWS_PROFILE` to access the radial archive:

```bash
HFR_DATA_PATH=s3://arn:aws:s3:us-east-1:579273261343:accesspoint/hfrnet-prod/radials/ \
uv run test-mcp
```

S3 support is included. Other buckets or access point URIs work with the layout
`<SITE>/<YYYY-MM>/<file>.ruv` under the configured root. Access requires
`s3:ListBucket` and `s3:GetObject`; only the configured prefix is used.

`HFR_DATA_PATH` overrides `HFR_BASE_URL`. The server uses stdio for both sources.

## Tools

| Tool | What it does |
|---|---|
| `list_sites()` | Sites and operators (`operator` is null for HFRNet) |
| `list_files(site, ...)` | Hourly files, with time filtering and archive coverage |
| `get_radials(site, ...)` | Radial vectors, metadata, and summary; latest file by default |

Times are ISO 8601 UTC, for example `2026-11-17T13:00Z`. `velocity_cm_s` follows
the CODAR convention: a positive value means flow **toward** the radar site.

## Development checks

```bash
uv sync
uv run python -m unittest discover -s tests -v
```
