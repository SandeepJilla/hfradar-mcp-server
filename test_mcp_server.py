import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as Server
    from mcp.server.fastmcp.exceptions import ToolError

BASE = os.environ.get("HFR_BASE_URL", "https://hfr.gcoos.org/data/")
TTL = 600  # seconds to cache directory listings
RUV = re.compile(r"RDL([mi])_([A-Z0-9]+)_(\d{4})_(\d{2})_(\d{2})_(\d{2})(\d{2})\.ruv$")
NAMES = {"LOND": "lon", "LATD": "lat", "VELO": "velocity_cm_s", "BEAR": "bearing_deg",
         "RNGE": "range_km", "HEAD": "heading_deg", "VELU": "u_cm_s", "VELV": "v_cm_s"}

http = httpx.Client(timeout=30, follow_redirects=True)
_cache: dict[str, tuple[float, list[str]]] = {}
mcp = Server("gcoos-hfr")


def ls(url: str) -> list[str]:
    """Child links (absolute URLs) of a directory listing; folders end in '/'."""
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    html = http.get(url).raise_for_status().text
    out = []
    for href in re.findall(r'href="([^"?#]+)"', html):
        full = urljoin(url, href)
        rest = full[len(url):] if full.startswith(url) else ""
        if rest and rest.rstrip("/").count("/") == 0:
            out.append(full)
    out = sorted(set(out))
    _cache[url] = (time.time(), out)
    return out


def sites() -> dict[str, str]:
    """SITE -> site folder URL."""
    return {
        u.rstrip("/").rsplit("/", 1)[-1].upper(): u
        for op in ls(BASE) if op.endswith("/")
        for u in ls(op) if u.endswith("/")
    }


def files(site: str, pattern: str = "m") -> list[tuple[datetime, str]]:
    """(time, url) for every .ruv under a site, walked up to 3 levels deep."""
    root = sites().get(site.upper())
    if not root:
        raise ToolError(f"Unknown site {site}. Known: {', '.join(sorted(sites()))}")
    found, todo = [], [(root, 0)]
    while todo:
        url, depth = todo.pop()
        for u in ls(url):
            if u.endswith("/") and depth < 3:
                todo.append((u, depth + 1))
            elif m := RUV.search(u):
                if m[1] == pattern:
                    y, mo, d, hh, mm = map(int, m.groups()[2:])
                    found.append((datetime(y, mo, d, hh, mm, tzinfo=timezone.utc), u))
    return sorted(found)


def parse_time(s: str) -> datetime:
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise ToolError(f"Bad time {s!r}; use ISO 8601 like 2026-11-17T13:00Z")
    return t.replace(tzinfo=t.tzinfo or timezone.utc).astimezone(timezone.utc)


def num(v: str) -> float | str:
    try:
        return float(v)
    except ValueError:
        return v


def parse_ruv(text: str) -> tuple[dict, list[dict]]:
    """Header dict and rows of the first LLUV table."""
    header, cols, rows, in_table = {}, [], [], False
    for line in text.splitlines():
        if line.startswith("%%") or not line.strip():
            continue
        if line.startswith("%"):
            key, _, val = line[1:].partition(":")
            if key == "TableStart" and not rows:
                in_table, cols = True, header.get("TableColumnTypes", "").split()
            elif key == "TableEnd":
                if rows:
                    break
            else:
                header.setdefault(key, val.strip())
        elif in_table:
            vals = [num(v) for v in line.split()]
            rows.append({NAMES.get(c, c.lower()): v for c, v in zip(cols, vals)})
    return header, rows


@mcp.tool()
def list_sites() -> list[dict]:
    """List HF radar sites and their operators (gerg, usm, rates)."""
    return [{"site": s, "operator": u.split("/")[-3], "url": u} for s, u in sorted(sites().items())]


@mcp.tool()
def list_files(site: str, start: str | None = None, end: str | None = None) -> list[dict]:
    """List hourly measured-pattern radial files for a site (UTC, ISO 8601 start/end)."""
    lo = parse_time(start) if start else None
    hi = parse_time(end) if end else None
    return [
        {"time": t.strftime("%Y-%m-%dT%H:%MZ"), "url": u}
        for t, u in files(site)
        if (lo is None or t >= lo) and (hi is None or t <= hi)
    ]


@mcp.tool()
def get_radials(site: str, time: str | None = None, max_rows: int = 500) -> dict:
    """Radial velocities for one hour (default: latest file).

    Rows have lon, lat, velocity_cm_s (positive = away from site), bearing_deg
    (clockwise from north, site to cell), range_km. Rows capped at max_rows.
    """
    fl = files(site)
    if not fl:
        raise ToolError(f"No files for {site}")
    if time:
        want = parse_time(time)
        t, url = min(fl, key=lambda f: abs((f[0] - want).total_seconds()))
        if abs((t - want).total_seconds()) > 1800:
            raise ToolError(f"No file within 30 min of {time}; nearest is {t:%Y-%m-%dT%H:%MZ}")
    else:
        t, url = fl[-1]
    header, rows = parse_ruv(http.get(url).raise_for_status().text)
    step = max(1, -(-len(rows) // max_rows)) if max_rows else 1
    return {
        "site": site.upper(),
        "time": t.strftime("%Y-%m-%dT%H:%MZ"),
        "url": url,
        "origin": header.get("Origin"),
        "pattern": header.get("PatternType"),
        "rows_in_file": len(rows),
        "rows": rows[::step],
    }


if __name__ == "__main__":
    mcp.run()


