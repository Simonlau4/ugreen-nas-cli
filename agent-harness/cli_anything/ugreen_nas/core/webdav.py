from __future__ import annotations

import base64
import copy
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from .config import Profile
from .paths import normalize_remote_path


DAV_NS = "{DAV:}"


class WebDavError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: bytes | None = None):
        super().__init__(message)
        self.status = status
        self.body = body or b""


@dataclass(frozen=True)
class WebDavItem:
    path: str
    is_dir: bool
    size: int | None
    modified: str | None
    etag: str | None


class WebDavClient:
    def __init__(self, profile: Profile):
        self.profile = profile
        self._base_parts = urllib.parse.urlsplit(profile.base_url)

    def propfind(self, path: str, depth: str = "1") -> list[WebDavItem]:
        body = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<d:propfind xmlns:d="DAV:"><d:prop>'
            b"<d:displayname/><d:getcontentlength/><d:getlastmodified/>"
            b"<d:getetag/><d:resourcetype/>"
            b"</d:prop></d:propfind>"
        )
        status, _, response_body = self.request(
            "PROPFIND",
            path,
            body=body,
            headers={"Depth": depth, "Content-Type": "text/xml; charset=utf-8"},
            expected={200, 207},
        )
        if status not in {200, 207}:
            raise WebDavError("unexpected PROPFIND response", status, response_body)
        return self._parse_multistatus(response_body)

    def stat(self, path: str) -> WebDavItem:
        items = self.propfind(path, depth="0")
        if not items:
            raise WebDavError(f"not found: {path}", status=404)
        return items[0]

    def get(self, path: str) -> bytes:
        _, _, body = self.request("GET", path, expected={200})
        return body

    def put(self, path: str, data: bytes, overwrite: bool = False, etag: str | None = None) -> None:
        headers: dict[str, str] = {}
        if etag:
            headers["If-Match"] = etag
        elif not overwrite:
            headers["If-None-Match"] = "*"
        self.request("PUT", path, body=data, headers=headers, expected={200, 201, 204})

    def mkdir(self, path: str) -> None:
        self.request("MKCOL", path, expected={200, 201, 204, 405})

    def delete(self, path: str) -> None:
        self.request("DELETE", path, expected={200, 202, 204})

    def move(self, src: str, dst: str, overwrite: bool = False) -> None:
        self.request(
            "MOVE",
            src,
            headers={
                "Destination": self.url_for(dst),
                "Overwrite": "T" if overwrite else "F",
            },
            expected={200, 201, 204},
        )

    def copy(self, src: str, dst: str, overwrite: bool = False) -> None:
        self.request(
            "COPY",
            src,
            headers={
                "Destination": self.url_for(dst),
                "Overwrite": "T" if overwrite else "F",
            },
            expected={200, 201, 204},
        )

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        expected: set[int] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        expected = expected or set(range(200, 300))
        request_headers = {
            "Authorization": self._auth_header(),
            "User-Agent": "ugreen-nas-cli/0.1.0",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(
            self.url_for(path),
            data=body,
            headers=request_headers,
            method=method,
        )
        context = None
        if not self.profile.verify_tls:
            context = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.profile.timeout,
                context=context,
            ) as response:
                status = int(response.status)
                data = response.read()
                response_headers = dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            data = exc.read()
            response_headers = dict(exc.headers.items())
        except urllib.error.URLError as exc:
            raise WebDavError(f"network error: {exc.reason}") from exc

        if status not in expected:
            raise WebDavError(f"{method} failed with HTTP {status}", status, data)
        return status, response_headers, data

    def url_for(self, path: str) -> str:
        remote_path = normalize_remote_path(path)
        base_path = self._base_parts.path.rstrip("/")
        combined = f"{base_path}{remote_path}"
        quoted = urllib.parse.quote(combined, safe="/")
        return urllib.parse.urlunsplit(
            (
                self._base_parts.scheme,
                self._base_parts.netloc,
                quoted,
                "",
                "",
            )
        )

    def _auth_header(self) -> str:
        token = f"{self.profile.username}:{self.profile.password}".encode("utf-8")
        return "Basic " + base64.b64encode(token).decode("ascii")

    def _parse_multistatus(self, body: bytes) -> list[WebDavItem]:
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise WebDavError("invalid WebDAV XML response") from exc
        items: list[WebDavItem] = []
        for response in root.findall(f"{DAV_NS}response"):
            href_node = response.find(f"{DAV_NS}href")
            if href_node is None or not href_node.text:
                continue
            props = self._ok_props(response)
            resource_type = props.find(f"{DAV_NS}resourcetype")
            is_dir = resource_type is not None and resource_type.find(f"{DAV_NS}collection") is not None
            size = _optional_int(_text(props, "getcontentlength"))
            items.append(
                WebDavItem(
                    path=self._remote_from_href(href_node.text),
                    is_dir=is_dir,
                    size=size,
                    modified=_text(props, "getlastmodified"),
                    etag=_text(props, "getetag"),
                )
            )
        return items

    def _ok_props(self, response: ET.Element) -> ET.Element:
        for propstat in response.findall(f"{DAV_NS}propstat"):
            status = _text(propstat, "status") or ""
            if " 200 " in status:
                prop = propstat.find(f"{DAV_NS}prop")
                if prop is not None:
                    return prop
        empty = ET.Element(f"{DAV_NS}prop")
        return empty

    def _remote_from_href(self, href: str) -> str:
        href_path = urllib.parse.urlsplit(href).path or href
        href_path = urllib.parse.unquote(href_path)
        base_path = self._base_parts.path.rstrip("/")
        if base_path and href_path == base_path:
            href_path = "/"
        elif base_path and href_path.startswith(base_path + "/"):
            href_path = href_path[len(base_path) :]
        return normalize_remote_path(href_path)


def _text(parent: ET.Element, local_name: str) -> str | None:
    node = parent.find(f"{DAV_NS}{local_name}")
    if node is None or node.text is None:
        return None
    return node.text


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None
