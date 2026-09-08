"""Restricted HTTPS fetch helper for non-mutating metadata checks."""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from .constants import DEFAULT_MAX_DOWNLOAD_BYTES, DEFAULT_NETWORK_TIMEOUT_SECONDS, DEFAULT_UPDATE_HOSTS
from .errors import NetworkError


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


@dataclass(frozen=True)
class FetchResponse:
    url: str
    text: str


def fetch_official_text(
    url: str,
    *,
    allowed_hosts: frozenset[str] = DEFAULT_UPDATE_HOSTS,
    timeout: float = DEFAULT_NETWORK_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
) -> FetchResponse:
    """Fetch a small HTTPS document from an exact allowlisted host."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise NetworkError("更新源不在允许的 HTTPS 官方地址列表中。")
    request = Request(url, headers={"User-Agent": "agent-reach/0.1"})
    opener = build_opener(_NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(request, timeout=timeout) as response:
            final = urlparse(response.url)
            if final.scheme != "https" or final.hostname not in allowed_hosts:
                raise NetworkError("更新源重定向到了未允许的地址。")
            body = response.read(max_bytes + 1)
    except HTTPError as error:
        if 300 <= error.code < 400:
            raise NetworkError("更新源发生重定向，已为安全起见拒绝访问。") from error
        raise NetworkError(f"更新检查失败，HTTP 状态码：{error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise NetworkError(f"无法连接更新源：{error}") from error
    if len(body) > max_bytes:
        raise NetworkError("更新元数据超过允许大小，已拒绝读取。")
    try:
        return FetchResponse(url=response.url, text=body.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise NetworkError("更新元数据不是有效 UTF-8 文本。") from error


def parse_pyproject_version(text: str) -> str:
    """Extract the project version without executing remote content."""
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.7-3.10
        import tomli as tomllib

    try:
        parsed = tomllib.loads(text)
        version = parsed["project"]["version"]
    except (tomllib.TOMLDecodeError, KeyError, TypeError) as error:
        raise NetworkError("更新源未提供有效的项目版本元数据。") from error
    if not isinstance(version, str):
        raise NetworkError("更新源版本格式无效。")
    return version
