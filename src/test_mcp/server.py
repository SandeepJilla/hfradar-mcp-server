"""MCP server for the GCOOS HF radar radial files at https://hfr.gcoos.org/data/.

Layout: <operator>/<SITE>/raw/{MeasPattern,IdealPattern}/RDL{m,i}_<SITE>_YYYY_MM_DD_HHMM.ruv
Files are hourly CODAR SeaSonde LLUV radial maps (rolling ~1 month window).
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

BASE = os.environ.get("HFR_BASE_URL", "https://hfr.gcoos.org/data/").rstrip("/") + "/"
TTL = 600  # seconds to cache directory listings
PATTERNS = {"measured": "MeasPattern", "ideal": "IdealPattern"}
RUV = re.compile(r"RDL[mi]_([A-Z0-9]+)_(\d{4})_(\d{2})_(\d{2})_(\d{2})(\d{2})\.ruv$")
NAMES = {
    "LOND": "lon", "LATD": "lat", "VELO": "velocity_cm_s", "BEAR": "bearing_deg",
    "RNGE": "range_km", "HEAD": "direction_deg", "VELU": "u_cm_s", "VELV": "v_cm_s",
    "VFLG": "flag", "ESPC": "spatial_quality", "ETMP": "temporal_quality", "EASN": "snr_db",
}
HEADER_KEYS = [
    "Site", "TimeStamp", "TimeCoverage", "Origin", "PatternType", "PatternDate",
    "RangeResolutionKMeters", "AngularResolution", "TransmitCenterFreqMHz",
    "AverageSignalToNoise", "CurrentVelocityLimit", "LLUVDataQuality",
]

mcp = MCPServer("gcoos-hfr")
_cache: dict[str, tuple[float, list[dict]]] = {}


def fetch(url: str, accept: str = "*/*") -> bytes:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "gcoos-hfr-mcp"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise ToolError(f"HTTP {e.code} fetching {url}") from e
    except urllib.error.URLError as e:
        raise ToolError(f"Could not reach {url}: {e.reason}") from e


def ls(path: str) -> list[dict]:
    """Directory listing (Caddy JSON) for a path relative to BASE, cached."""
    hit = _cache.get(path)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    entries = json.loads(fetch(BASE + path, accept="application/json"))
    _cache[path] = (time.time(), entries)
    return entries


def sites() -> dict[str, str]:
    """SITE -> operator."""
    return {
        s["name"].rstrip("/").upper(): op["name"].rstrip("/")
        for op in ls("") if op["is_dir"]
        for s in ls(op["name"]) if s["is_dir"]
    }


def files(site: str, pattern: str) -> list[tuple[datetime, str, int]]:
    """Sorted (time, url, size) for every radial file of a site/pattern."""
    site = site.upper()
    op = sites().get(site)
    if not op:
        raise ToolError(f"Unknown site {site!r}. Known: {', '.join(sorted(sites()))}")
    if pattern not in PATTERNS:
        raise ToolError(f"pattern must be one of {list(PATTERNS)}")
    path = f"{op}/{site}/raw/{PATTERNS[pattern]}/"
    try:
        entries = ls(path)
    except ToolError:
        raise ToolError(f"Site {site} has no {pattern}-pattern data")
    out = []
    for e in entries:
        if m := RUV.search(e["name"]):
            y, mo, d, hh, mm = map(int, m.groups()[1:])
            out.append((datetime(y, mo, d, hh, mm, tzinfo=timezone.utc), BASE + path + e["name"], e["size"]))
    return sorted(out)


def parse_time(s: str) -> datetime:
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise ToolError(f"Bad time {s!r}; use ISO 8601 like 2026-11-17T13:00Z")
    return t.replace(tzinfo=t.tzinfo or timezone.utc).astimezone(timezone.utc)


def fmt(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%MZ")


def num(v: str) -> float | int | str:
    try:
        f = float(v)
        return int(f) if f.is_integer() and "." not in v else f
    except ValueError:
        return v


def parse_ruv(text: str) -> tuple[dict, list[dict]]:
    """Header dict and rows of the first (radial vector) LLUV table."""
    header: dict[str, str] = {}
    cols: list[str] = []
    rows: list[dict] = []
    in_table = False
    for line in text.splitlines():
        if not line.strip() or line.startswith("%%"):
            continue
        if line.startswith("%"):
            key, _, val = line[1:].partition(":")
            if key == "TableStart" and not in_table and not rows:
                in_table, cols = True, header.get("TableColumnTypes", "").split()
            elif key == "TableEnd" and in_table:
                break
            else:
                header.setdefault(key, val.strip())
        elif in_table:
            rows.append({NAMES.get(c, c.lower()): num(v) for c, v in zip(cols, line.split())})
    return header, rows


@mcp.tool()
def list_sites() -> list[dict]:
    """List the HF radar sites on hfr.gcoos.org and the operator (gerg, rates, usm) running each."""
    return [{"site": s, "operator": op} for s, op in sorted(sites().items())]


@mcp.tool()
def list_files(
    site: str,
    pattern: Literal["measured", "ideal"] = "measured",
    start: str | None = None,
    end: str | None = None,
    limit: int = 48,
) -> dict:
    """List hourly radial files for a site, newest last.

    start/end are ISO 8601 UTC (e.g. 2026-11-17T00:00Z). Returns at most `limit`
    files (the most recent ones in the range), plus the full coverage of the archive.
    """
    fl = files(site, pattern)
    lo = parse_time(start) if start else None
    hi = parse_time(end) if end else None
    sel = [f for f in fl if (lo is None or f[0] >= lo) and (hi is None or f[0] <= hi)]
    return {
        "site": site.upper(),
        "pattern": pattern,
        "archive_first": fmt(fl[0][0]) if fl else None,
        "archive_last": fmt(fl[-1][0]) if fl else None,
        "matched": len(sel),
        "files": [{"time": fmt(t), "url": u, "bytes": n} for t, u, n in sel[-limit:]],
    }


@mcp.tool()
def get_radials(
    site: str,
    time: str | None = None,
    pattern: Literal["measured", "ideal"] = "measured",
    max_rows: int = 500,
    include_flagged: bool = False,
) -> dict:
    """Radial surface-current velocities for one hour from one site (default: latest file).

    Picks the file nearest `time` (ISO 8601 UTC, must be within 30 min). Each row has
    lon, lat, velocity_cm_s (CODAR convention: positive = flowing toward the site),
    bearing_deg (true, site->cell), range_km, direction_deg (true direction the
    radial component points), u_cm_s, v_cm_s and quality columns.
    Rows with a non-zero vector flag are dropped unless include_flagged. If more than
    max_rows remain, they are evenly subsampled. Also returns a summary and key header metadata.
    """
    fl = files(site, pattern)
    if not fl:
        raise ToolError(f"No {pattern} files for {site}")
    if time:
        want = parse_time(time)
        t, url, _ = min(fl, key=lambda f: abs((f[0] - want).total_seconds()))
        if abs((t - want).total_seconds()) > 1800:
            raise ToolError(f"No file within 30 min of {time}; nearest is {fmt(t)}")
    else:
        t, url, _ = fl[-1]

    header, rows = parse_ruv(fetch(url).decode("latin-1"))
    total = len(rows)
    if not include_flagged:
        rows = [r for r in rows if r.get("flag", 0) == 0]
    speeds = [abs(r["velocity_cm_s"]) for r in rows if isinstance(r.get("velocity_cm_s"), (int, float))]
    step = max(1, -(-len(rows) // max_rows)) if max_rows > 0 else 1
    return {
        "site": site.upper(),
        "time": fmt(t),
        "url": url,
        "header": {k: header[k] for k in HEADER_KEYS if k in header},
        "summary": {
            "rows_in_file": total,
            "rows_after_flag_filter": len(rows),
            "rows_returned": len(rows[::step]),
            "mean_abs_velocity_cm_s": round(sum(speeds) / len(speeds), 2) if speeds else None,
            "max_abs_velocity_cm_s": max(speeds) if speeds else None,
        },
        "rows": rows[::step],
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
