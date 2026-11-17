# GCOOS HF radar MCP server

An MCP server for CODAR SeaSonde radial data, using the public GCOOS HTTP archive
by default. HFRNet radial data in S3 is also supported, with `boto3` included in
the standard installation.

## Run

```bash
uv run test-mcp              # stdio; https://hfr.gcoos.org/data/
```

## Data source

The default GCOOS source uses this directory layout:

```text
<operator>/<SITE>/raw/{MeasPattern,IdealPattern}/RDL{m,i}_<SITE>_YYYY_MM_DD_HHMM.ruv
```

Set `HFR_BASE_URL` to use another GCOOS HTTP mirror. It must serve Caddy JSON
directory listings and preserve that layout:

```bash
HFR_BASE_URL=https://mirror.example/data/ uv run test-mcp
```

`HFR_DATA_PATH` accepts either a GCOOS HTTP URL or an HFRNet S3 URI and takes
precedence over `HFR_BASE_URL`. S3 sources use the HFRNet layout
`<SITE>/<YYYY-MM>/RDL{m,i}_<SITE>_YYYY_MM_DD_HHMM.ruv` under the configured radial
root. The layout follows the source type, so no layout switch is needed.

```bash
HFR_DATA_PATH=s3://arn:aws:s3:us-east-1:579273261343:accesspoint/hfrnet-prod/radials/ \
uv run test-mcp
```

Only the configured radial prefix is traversed in S3. S3 credentials and regions
use boto3's standard AWS configuration, including `AWS_PROFILE`. The identity
needs `s3:ListBucket` for the prefix and `s3:GetObject` for the files. Access point
ARNs supply their region and endpoint automatically. Configuration is read at
startup; directory listings are cached for ten minutes.

## Tools

| Tool | What it does |
|---|---|
| `list_sites()` | Lists sites and their GCOOS operators; `operator` is null for HFRNet S3 |
| `list_files(site, pattern="measured", start?, end?, limit=48)` | Lists hourly files, plus the archive's first and last time |
| `get_radials(site, time?, pattern="measured", max_rows=500, include_flagged=False)` | Parses one hour of radial vectors (latest by default), with header metadata and a summary |

Times are ISO 8601 UTC, for example `2026-11-17T13:00Z`. `velocity_cm_s` follows
the CODAR convention: a positive value means flow **toward** the radar site.
The `url` fields contain HTTP URLs for GCOOS or S3 object URIs for HFRNet.

## Development checks

```bash
uv sync
uv run python -m unittest discover -s tests -v
```

`test_mcp_server.py` is an older standalone prototype, not the installed entry
point or the automated test suite. Use `uv run test-mcp` for this server.
