"""
Core analysis logic for Page Pulse.

Design decision: this is kept separate from the FastAPI route (app/main.py)
so it can be unit-tested without spinning up the web server, and so the
"business logic" doesn't get tangled with HTTP concerns.
"""

import time
from dataclasses import dataclass, asdict
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT_SECONDS = 8
USER_AGENT = "PagePulse/1.0 (+https://digitalheroesco.com)"


class PagePulseError(Exception):
    """Base class for all errors this module raises on purpose."""


class InvalidURLError(PagePulseError):
    pass


class FetchTimeoutError(PagePulseError):
    pass


class UnreachableError(PagePulseError):
    pass


class NotHTMLError(PagePulseError):
    pass


@dataclass
class PageReport:
    url: str
    status_code: int
    response_time_ms: int
    title: str | None
    meta_description: str | None
    h1_count: int
    images_missing_alt: int
    total_images: int
    word_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def _validate_url(url: str) -> str:
    """Normalize and sanity-check the URL before we ever hit the network."""
    url = url.strip()
    if not url:
        raise InvalidURLError("URL cannot be empty.")

    # Be forgiving: if someone types "example.com" without a scheme, assume https.
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise InvalidURLError(f"Unsupported URL scheme: '{parsed.scheme}'. Use http or https.")

    if not parsed.netloc:
        raise InvalidURLError("URL is missing a domain/host.")

    if " " in parsed.netloc:
        raise InvalidURLError("URL host cannot contain spaces.")

    return url


def _fetch(url: str) -> tuple[requests.Response, int]:
    headers = {"User-Agent": USER_AGENT}
    start = time.perf_counter()
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
    except requests.exceptions.Timeout as exc:
        raise FetchTimeoutError(f"Request to {url} timed out after {REQUEST_TIMEOUT_SECONDS}s.") from exc
    except requests.exceptions.ConnectionError as exc:
        raise UnreachableError(f"Could not connect to {url}.") from exc
    except requests.exceptions.RequestException as exc:
        raise UnreachableError(f"Request to {url} failed: {exc}") from exc

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return response, elapsed_ms


def analyze_url(raw_url: str) -> PageReport:
    """
    Fetch `raw_url` and return a PageReport.

    Raises PagePulseError subclasses on any expected failure mode; callers
    (the FastAPI route) are responsible for turning those into HTTP errors.
    """
    url = _validate_url(raw_url)
    response, elapsed_ms = _fetch(url)

    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type.lower():
        raise NotHTMLError(
            f"Response was '{content_type or 'unknown content-type'}', not HTML. "
            "Page Pulse only audits HTML pages."
        )

    soup = BeautifulSoup(response.text, "html.parser")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag and title_tag.get_text(strip=True) else None

    meta_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = None
    if meta_tag and meta_tag.get("content"):
        meta_description = meta_tag["content"].strip() or None

    h1_count = len(soup.find_all("h1"))

    images = soup.find_all("img")
    total_images = len(images)
    images_missing_alt = sum(
        1 for img in images if not img.get("alt") or not img["alt"].strip()
    )

    # Design decision: word count is computed on visible body text only,
    # after stripping <script> and <style> content, so it approximates what
    # a reader (or a search engine) actually sees rather than counting code.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    body_text = soup.get_text(separator=" ", strip=True)
    word_count = len(body_text.split()) if body_text else 0

    return PageReport(
        url=url,
        status_code=response.status_code,
        response_time_ms=elapsed_ms,
        title=title,
        meta_description=meta_description,
        h1_count=h1_count,
        images_missing_alt=images_missing_alt,
        total_images=total_images,
        word_count=word_count,
    )
