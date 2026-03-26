"""Web content reading and remote download tools."""

from __future__ import annotations

import ipaddress
import re
import socket
from html import unescape
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

from .types import ToolResult


class WebOpsMixin:
    """Web operations with basic SSRF and size safeguards."""

    _USER_AGENT = "llm-service-agent/1.0"
    _DEFAULT_TIMEOUT_SECONDS = 20
    _DEFAULT_MAX_READ_BYTES = 2 * 1024 * 1024
    _DEFAULT_MAX_READ_CHARS = 20_000
    _DEFAULT_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
    _MAX_REDIRECTS = 5
    _DOWNLOAD_CHUNK_SIZE = 64 * 1024

    def read_online_content(self, url: str) -> ToolResult:
        """Fetch online content and return extracted plain text with metadata."""
        if not url or not str(url).strip():
            return ToolResult(False, "", "url is required")

        try:
            response = self._request_with_redirects(url=str(url).strip(), stream=False)
            response.raise_for_status()

            max_read_bytes = int(getattr(self, "web_max_read_bytes", self._DEFAULT_MAX_READ_BYTES))
            body_bytes = response.content
            bytes_truncated = False
            if len(body_bytes) > max_read_bytes:
                body_bytes = body_bytes[:max_read_bytes]
                bytes_truncated = True

            decoded_text = self._decode_body(body_bytes, response.encoding)
            is_html = self._is_html_content(response.headers.get("content-type", ""), decoded_text)

            title = ""
            raw_html_preview = ""
            if is_html:
                title = self._extract_html_title(decoded_text)
                plain_text = self._extract_html_text(decoded_text)
                raw_html_preview = decoded_text[:4000]
            else:
                plain_text = decoded_text

            plain_text = plain_text.strip()
            max_read_chars = int(getattr(self, "web_max_read_chars", self._DEFAULT_MAX_READ_CHARS))
            chars_truncated = False
            if len(plain_text) > max_read_chars:
                chars_truncated = True
                omitted = len(plain_text) - max_read_chars
                plain_text = (
                    f"{plain_text[:max_read_chars]}\n\n"
                    f"...[truncated {omitted} chars from online content]..."
                )

            if not plain_text:
                plain_text = "(no text content extracted)"

            return ToolResult(
                True,
                plain_text,
                data={
                    "url": str(url),
                    "final_url": response.url,
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "bytes_read": len(body_bytes),
                    "is_html": is_html,
                    "title": title,
                    "bytes_truncated": bytes_truncated,
                    "chars_truncated": chars_truncated,
                    "raw_html_preview": raw_html_preview,
                },
            )
        except Exception as e:
            return ToolResult(False, "", f"Failed to read online content: {e}")

    def download_remote_resource(self, url: str, path: Optional[str] = None) -> ToolResult:
        """Download a remote resource into workdir, defaulting to downloads/."""
        if not url or not str(url).strip():
            return ToolResult(False, "", "url is required")

        try:
            response = self._request_with_redirects(url=str(url).strip(), stream=True)
            response.raise_for_status()

            max_download_bytes = int(
                getattr(self, "web_max_download_bytes", self._DEFAULT_MAX_DOWNLOAD_BYTES)
            )
            content_length = response.headers.get("content-length")
            if content_length and content_length.isdigit() and int(content_length) > max_download_bytes:
                return ToolResult(
                    False,
                    "",
                    f"Remote file exceeds max download size ({int(content_length)} > {max_download_bytes})",
                )

            target_path = self._resolve_download_target(url, response, path)
            if target_path.exists():
                return ToolResult(False, "", f"Target already exists: {target_path}")

            target_path.parent.mkdir(parents=True, exist_ok=True)
            total = 0

            with open(target_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=self._DOWNLOAD_CHUNK_SIZE):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_download_bytes:
                        f.close()
                        target_path.unlink(missing_ok=True)
                        return ToolResult(
                            False,
                            "",
                            f"Download exceeded max size limit ({max_download_bytes} bytes)",
                        )
                    f.write(chunk)

            return ToolResult(
                True,
                f"Downloaded {total} bytes to {target_path}",
                data={
                    "url": str(url),
                    "final_url": response.url,
                    "path": str(target_path),
                    "size_bytes": total,
                    "content_type": response.headers.get("content-type", ""),
                },
            )
        except Exception as e:
            return ToolResult(False, "", f"Failed to download remote resource: {e}")

    def _request_with_redirects(self, url: str, stream: bool) -> requests.Response:
        """Fetch URL while validating each redirect target."""
        current_url = self._normalize_and_validate_url(url)
        timeout = int(getattr(self, "web_request_timeout", self._DEFAULT_TIMEOUT_SECONDS))
        headers = {"User-Agent": self._USER_AGENT}

        for _ in range(self._MAX_REDIRECTS + 1):
            response = requests.get(
                current_url,
                timeout=timeout,
                headers=headers,
                allow_redirects=False,
                stream=stream,
            )
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("Redirect response missing location header")
                current_url = self._normalize_and_validate_url(urljoin(current_url, location))
                continue
            return response

        raise ValueError(f"Too many redirects (>{self._MAX_REDIRECTS})")

    def _normalize_and_validate_url(self, raw_url: str) -> str:
        """Validate URL scheme and block private/loopback hosts."""
        parsed = urlparse(raw_url.strip())
        scheme = (parsed.scheme or "").lower()
        if scheme not in {"http", "https"}:
            raise ValueError("Only http/https URLs are allowed")

        hostname = parsed.hostname
        if not hostname:
            raise ValueError("URL must include a hostname")

        if bool(getattr(self, "web_block_private_hosts", True)):
            self._validate_public_hostname(hostname, parsed.port)

        return parsed.geturl()

    def _validate_public_hostname(self, hostname: str, port: Optional[int]) -> None:
        """Reject hostnames resolving to loopback/private/link-local/reserved ranges."""
        if hostname.lower() == "localhost":
            raise ValueError("localhost targets are blocked")

        addrinfo = socket.getaddrinfo(hostname, port or 80, proto=socket.IPPROTO_TCP)
        seen = set()
        for info in addrinfo:
            ip_str = info[4][0]
            if ip_str in seen:
                continue
            seen.add(ip_str)
            ip_obj = ipaddress.ip_address(ip_str)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_reserved
                or ip_obj.is_multicast
                or ip_obj.is_unspecified
            ):
                raise ValueError(f"Blocked non-public target address: {ip_str}")

    def _resolve_download_target(
        self,
        url: str,
        response: requests.Response,
        path: Optional[str],
    ) -> Path:
        """Resolve safe target path in workdir for downloads."""
        if path and str(path).strip():
            raw = Path(str(path).strip())
            if raw.is_absolute():
                raise ValueError("Absolute download path is not allowed")
            target = self._resolve_path(str(raw))
        else:
            filename = self._guess_filename(url, response)
            target = self._resolve_path("downloads") / filename
        return target

    def _guess_filename(self, url: str, response: requests.Response) -> str:
        """Derive a safe filename from headers or URL path."""
        from_header = self._filename_from_content_disposition(
            response.headers.get("content-disposition", "")
        )
        if from_header:
            return self._sanitize_filename(from_header)

        parsed = urlparse(response.url or url)
        from_url = Path(parsed.path).name
        if from_url:
            return self._sanitize_filename(from_url)

        return "download.bin"

    def _filename_from_content_disposition(self, content_disposition: str) -> str:
        """Extract filename from Content-Disposition header when available."""
        if not content_disposition:
            return ""

        # Supports filename="x" and filename*=UTF-8''x
        filename_star = re.search(r"filename\*=([^;]+)", content_disposition, flags=re.IGNORECASE)
        if filename_star:
            value = filename_star.group(1).strip().strip('"')
            if "''" in value:
                value = value.split("''", 1)[1]
            return value

        filename = re.search(r"filename=([^;]+)", content_disposition, flags=re.IGNORECASE)
        if filename:
            return filename.group(1).strip().strip('"')
        return ""

    def _sanitize_filename(self, filename: str) -> str:
        """Convert remote filename to a local safe filename."""
        name = filename.replace("\\", "_").replace("/", "_").strip()
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
        name = name.strip("._")
        if not name:
            return "download.bin"
        return name[:200]

    def _decode_body(self, body_bytes: bytes, encoding: Optional[str]) -> str:
        """Decode bytes using server encoding fallback to utf-8."""
        codec = encoding or "utf-8"
        try:
            return body_bytes.decode(codec, errors="replace")
        except LookupError:
            return body_bytes.decode("utf-8", errors="replace")

    def _is_html_content(self, content_type: str, text: str) -> bool:
        """Best-effort HTML detection."""
        ct = (content_type or "").lower()
        if "html" in ct or "xhtml" in ct:
            return True
        snippet = text[:1000].lower()
        return "<html" in snippet or "<!doctype html" in snippet

    def _extract_html_title(self, html_text: str) -> str:
        """Extract page title from HTML."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return unescape(re.sub(r"\s+", " ", match.group(1)).strip())

    def _extract_html_text(self, html_text: str) -> str:
        """Remove script/style/tags and return plain text."""
        cleaned = re.sub(r"<script[^>]*>.*?</script>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<style[^>]*>.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<noscript[^>]*>.*?</noscript>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = unescape(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()
