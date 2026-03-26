"""Tests for web operation tools."""

from pathlib import Path

from llm_service.agent.tools import ToolRegistry


class _FakeResponse:
    def __init__(
        self,
        *,
        url: str,
        status_code: int = 200,
        headers=None,
        content: bytes = b"",
        encoding: str = "utf-8",
        is_redirect: bool = False,
        chunks=None,
    ):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content
        self.encoding = encoding
        self.is_redirect = is_redirect
        self._chunks = chunks or []

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=65536):
        for chunk in self._chunks:
            yield chunk


def _registry(tmp_path: Path) -> ToolRegistry:
    tools = ToolRegistry(workdir=str(tmp_path))
    tools.web_request_timeout = 10
    tools.web_max_read_bytes = 1024 * 1024
    tools.web_max_read_chars = 4000
    tools.web_max_download_bytes = 10
    tools.web_block_private_hosts = True
    return tools


def test_read_online_content_rejects_non_http_scheme(tmp_path):
    tools = _registry(tmp_path)

    result = tools.read_online_content("ftp://example.com/file.txt")

    assert not result.success
    assert "http/https" in (result.error or "")


def test_read_online_content_blocks_localhost(tmp_path):
    tools = _registry(tmp_path)

    result = tools.read_online_content("http://localhost:8080")

    assert not result.success
    assert "localhost" in (result.error or "")


def test_read_online_content_returns_text_and_metadata(tmp_path, monkeypatch):
    tools = _registry(tmp_path)

    html = b"<html><head><title>Demo Page</title></head><body><h1>Hello</h1><p>World</p></body></html>"

    def fake_request_with_redirects(url, stream):
        assert stream is False
        return _FakeResponse(
            url="https://example.com/final",
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=html,
            encoding="utf-8",
        )

    monkeypatch.setattr(tools, "_request_with_redirects", fake_request_with_redirects)

    result = tools.read_online_content("https://example.com")

    assert result.success
    assert "Hello" in result.output
    assert "World" in result.output
    assert result.data is not None
    assert result.data["is_html"] is True
    assert result.data["title"] == "Demo Page"
    assert result.data["final_url"] == "https://example.com/final"


def test_download_remote_resource_fails_when_target_exists(tmp_path, monkeypatch):
    tools = _registry(tmp_path)
    existing = tmp_path / "downloads" / "exists.txt"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("old", encoding="utf-8")

    def fake_request_with_redirects(url, stream):
        assert stream is True
        return _FakeResponse(
            url="https://example.com/exists.txt",
            status_code=200,
            headers={"content-type": "text/plain"},
            chunks=[b"new"],
        )

    monkeypatch.setattr(tools, "_request_with_redirects", fake_request_with_redirects)

    result = tools.download_remote_resource("https://example.com/exists.txt")

    assert not result.success
    assert "already exists" in (result.error or "")


def test_download_remote_resource_enforces_max_size(tmp_path, monkeypatch):
    tools = _registry(tmp_path)

    def fake_request_with_redirects(url, stream):
        return _FakeResponse(
            url="https://example.com/file.bin",
            status_code=200,
            headers={"content-type": "application/octet-stream"},
            chunks=[b"12345", b"67890", b"x"],
        )

    monkeypatch.setattr(tools, "_request_with_redirects", fake_request_with_redirects)

    result = tools.download_remote_resource("https://example.com/file.bin")

    assert not result.success
    assert "max size" in (result.error or "")
    assert not (tmp_path / "downloads" / "file.bin").exists()
