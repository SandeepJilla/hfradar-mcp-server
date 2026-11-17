"""Read-only access to GCOOS HTTP and HFRNet S3 radial archives."""

import json
import os
import re
import urllib.error
import urllib.request
from contextlib import closing
from functools import cached_property
from urllib.parse import quote, unquote, urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from mcp.server.mcpserver.exceptions import ToolError

DEFAULT_SOURCE = "https://hfr.gcoos.org/data/"


class HTTPArchive:
    layout = "gcoos"

    def __init__(self, source: str):
        parsed = urlsplit(source)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("HTTP archive must be a directory URL without a query or fragment")
        self.base = source.rstrip("/") + "/"

    def url(self, path: str) -> str:
        return self.base + quote(path, safe="/")

    def read(self, url: str, accept: str = "*/*") -> bytes:
        request = urllib.request.Request(
            url, headers={"Accept": accept, "User-Agent": "gcoos-hfr-mcp"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise ToolError(f"HTTP {exc.code} fetching {url}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ToolError(f"Could not read {url}: {exc}") from exc

    def list(self, path: str) -> list[dict]:
        try:
            return json.loads(self.read(self.url(path), accept="application/json"))
        except ValueError as exc:
            raise ToolError(f"Expected a Caddy JSON directory listing at {self.url(path)}") from exc


class S3Archive:
    layout = "hfrnet"

    def __init__(self, source: str):
        # An access point's resource name is part of Bucket, not the key prefix.
        access_point = re.fullmatch(
            r"s3://(arn:aws(?:-[a-z0-9-]+)?:s3:([a-z0-9-]+):\d{12}:accesspoint/[a-zA-Z0-9-]+)(?:/([^?#]*))?",
            source,
        )
        self.region = None
        if access_point:
            self.bucket, self.region, prefix = access_point.groups()
            self.prefix = unquote(prefix or "").strip("/")
            self.prefix = self.prefix + "/" if self.prefix else ""
            return
        parsed = urlsplit(source)
        if (parsed.scheme != "s3" or not parsed.netloc or parsed.query or parsed.fragment
                or "@" in parsed.netloc or ":" in parsed.netloc):
            raise ValueError("HFR_DATA_PATH must be s3://bucket/optional-prefix or s3://<access-point-ARN>/optional-prefix")
        self.bucket = parsed.netloc
        self.prefix = unquote(parsed.path).lstrip("/").rstrip("/")
        self.prefix = self.prefix + "/" if self.prefix else ""

    @cached_property
    def client(self):
        return boto3.client(
            "s3", region_name=self.region,
            config=Config(connect_timeout=10, read_timeout=60,
                          retries={"mode": "standard", "total_max_attempts": 3}),
        )

    def url(self, path: str) -> str:
        return f"s3://{self.bucket}/" + quote(self.prefix + path, safe="/")

    def read(self, url: str) -> bytes:
        root = f"s3://{self.bucket}/"
        if not url.startswith(root):
            raise ToolError("Object URI does not belong to the configured S3 source")
        client = self.client

        try:
            result = client.get_object(Bucket=self.bucket, Key=unquote(url[len(root):]))
            with closing(result["Body"]) as body:
                return body.read()
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ToolError(f"Could not read {url}: {exc}") from exc

    def list(self, path: str) -> list[dict]:
        client = self.client

        prefix = self.prefix + path
        entries = []
        try:
            for page in client.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=prefix, Delimiter="/"
            ):
                entries.extend({"name": item["Prefix"][len(prefix):], "is_dir": True, "size": 0}
                               for item in page.get("CommonPrefixes", []))
                entries.extend({"name": item["Key"][len(prefix):], "is_dir": False, "size": item["Size"]}
                               for item in page.get("Contents", []) if item["Key"] != prefix)
        except (BotoCoreError, ClientError) as exc:
            raise ToolError(f"Could not list {self.url(path)}: {exc}") from exc
        return entries


def archive_from_env() -> HTTPArchive | S3Archive:
    source = os.environ.get("HFR_DATA_PATH") or os.environ.get("HFR_BASE_URL") or DEFAULT_SOURCE
    if urlsplit(source).scheme in {"http", "https"}:
        return HTTPArchive(source)
    return S3Archive(source)
