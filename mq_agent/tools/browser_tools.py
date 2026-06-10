"""Browser-safe URL inspection and content fetching tools."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

_BLOCKED_SCHEMES = {"file", "ftp", "data", "javascript"}
_MAX_CONTENT_BYTES = 512_000  # 512 KB cap


def _assert_safe_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme in _BLOCKED_SCHEMES:
        raise ValueError(f"Blocked URL scheme: {parsed.scheme}")
    if not parsed.scheme:
        raise ValueError("URL must include a scheme (https:// or http://)")


class _HTMLExtractor(HTMLParser):
    """Minimal HTML → structured data extractor."""

    def __init__(self) -> None:
        super().__init__()
        self.title: str = ""
        self.description: str = ""
        self.h1s: list[str] = []
        self.h2s: list[str] = []
        self.links: list[str] = []
        self._in_title = False
        self._in_h1 = False
        self._in_h2 = False
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attr_map = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
        elif tag == "h2":
            self._in_h2 = True
        elif tag == "meta":
            name = attr_map.get("name", "").lower()
            prop = attr_map.get("property", "").lower()
            content = attr_map.get("content", "")
            if name in ("description",) or prop in ("og:description",):
                if content and not self.description:
                    self.description = content.strip()
        elif tag == "a":
            href = attr_map.get("href", "")
            if href and not href.startswith(("#", "javascript:")):
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
        elif tag == "h2":
            self._in_h2 = False

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._in_title and not self.title:
            self.title = text
        if self._in_h1:
            self.h1s.append(text)
        if self._in_h2:
            self.h2s.append(text)
        self._text_parts.append(text)

    def text_content(self) -> str:
        return " ".join(self._text_parts)


def fetch_url(url: str, timeout: int = 10) -> str:
    """Fetch raw content from a URL. Read-only GET request."""
    _assert_safe_url(url)
    import httpx
    resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "mq-agent/0.7"})
    resp.raise_for_status()
    return resp.text[:_MAX_CONTENT_BYTES]


def inspect_url(url: str, timeout: int = 10) -> dict:
    """Fetch a URL and return structured metadata: title, description, headings, links, word count."""
    _assert_safe_url(url)
    import httpx
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "mq-agent/0.7"})
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {"url": url, "ok": False, "status_code": exc.response.status_code, "error": str(exc)}
    except Exception as exc:
        return {"url": url, "ok": False, "error": str(exc)}

    content_type = resp.headers.get("content-type", "")
    body = resp.text[:_MAX_CONTENT_BYTES]

    if "html" in content_type or body.lstrip().startswith("<"):
        parser = _HTMLExtractor()
        parser.feed(body)
        text = parser.text_content()
        word_count = len(re.split(r"\s+", text.strip())) if text.strip() else 0
        return {
            "url": url,
            "ok": True,
            "status_code": resp.status_code,
            "content_type": content_type,
            "title": parser.title,
            "description": parser.description,
            "h1s": parser.h1s[:5],
            "h2s": parser.h2s[:10],
            "links": [urljoin(url, link) for link in parser.links[:20]],
            "word_count": word_count,
        }

    return {
        "url": url,
        "ok": True,
        "status_code": resp.status_code,
        "content_type": content_type,
        "title": "",
        "description": "",
        "h1s": [],
        "h2s": [],
        "links": [],
        "word_count": len(re.split(r"\s+", body.strip())) if body.strip() else 0,
    }


def summarize_url(url: str, max_words: int = 120, timeout: int = 10) -> str:
    """Fetch a URL and return a plain-text content summary (first N words from visible text)."""
    meta = inspect_url(url, timeout=timeout)
    if not meta.get("ok"):
        return f"Error fetching {url}: {meta.get('error', 'unknown error')}"

    parts: list[str] = []
    if meta["title"]:
        parts.append(f"Title: {meta['title']}")
    if meta["description"]:
        parts.append(f"Description: {meta['description']}")
    if meta["h1s"]:
        parts.append("Headings: " + " / ".join(meta["h1s"]))
    if meta["h2s"]:
        parts.append("Sections: " + " / ".join(meta["h2s"][:5]))
    parts.append(f"Word count: ~{meta['word_count']}")
    parts.append(f"Links found: {len(meta['links'])}")
    return "\n".join(parts)


def verify_release_url(url: str, expected_tag: str = "", timeout: int = 10) -> dict:
    """Inspect a release page URL and check for expected release fields.

    Works with GitHub release pages and generic pages. Returns a structured
    verification result with pass/fail items.
    """
    _assert_safe_url(url)
    meta = inspect_url(url, timeout=timeout)

    checks: list[dict] = []

    # Page reachable
    checks.append({
        "check": "page reachable",
        "passed": meta.get("ok", False),
        "note": f"HTTP {meta.get('status_code')}" if meta.get("ok") else meta.get("error", ""),
    })

    if not meta.get("ok"):
        return {"url": url, "checks": checks, "passed": False}

    title = meta.get("title", "")
    h1s = meta.get("h1s", [])
    h2s = meta.get("h2s", [])
    all_headings = " ".join(h1s + h2s).lower()

    # Has a title
    checks.append({
        "check": "page has title",
        "passed": bool(title),
        "note": title or "no title found",
    })

    # GitHub release: look for version/tag reference
    parsed = urlparse(url)
    is_github = "github.com" in parsed.netloc
    if is_github:
        path_parts = parsed.path.strip("/").split("/")
        # e.g. /owner/repo/releases/tag/v0.7.0
        has_tag_in_path = "releases" in path_parts
        checks.append({
            "check": "GitHub releases URL",
            "passed": has_tag_in_path,
            "note": f"path: {parsed.path}",
        })

    # Expected tag present somewhere in title or headings
    if expected_tag:
        tag_present = expected_tag in title or expected_tag in all_headings
        checks.append({
            "check": f"expected tag '{expected_tag}' present",
            "passed": tag_present,
            "note": f"title: {title!r}" if not tag_present else "found",
        })

    # Has some content
    checks.append({
        "check": "page has content",
        "passed": meta.get("word_count", 0) > 10,
        "note": f"{meta.get('word_count', 0)} words",
    })

    all_passed = all(c["passed"] for c in checks)
    return {"url": url, "checks": checks, "passed": all_passed}
