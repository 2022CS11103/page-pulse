"""
Tests for app.core.

Design decision: we mock requests.get instead of hitting real websites.
This keeps tests fast, deterministic, and runnable offline/in CI — a test
suite that depends on github.com being up is not a real test suite.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.core import (
    FetchTimeoutError,
    InvalidURLError,
    NotHTMLError,
    UnreachableError,
    analyze_url,
)

SAMPLE_HTML = """
<html>
<head>
    <title>  Test Page - Best Widgets  </title>
    <meta name="description" content="A page about widgets.">
</head>
<body>
    <h1>Welcome to Widgets</h1>
    <p>We sell the finest widgets in town. Widgets for everyone.</p>
    <img src="a.jpg" alt="A widget">
    <img src="b.jpg">
    <img src="c.jpg" alt="">
</body>
</html>
"""


def _mock_response(text=SAMPLE_HTML, status_code=200, content_type="text/html; charset=utf-8"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"Content-Type": content_type}
    resp.text = text
    return resp


# ---------- Happy path ----------

@patch("app.core.requests.get")
def test_analyze_url_happy_path(mock_get):
    mock_get.return_value = _mock_response()

    report = analyze_url("https://example.com")

    assert report.status_code == 200
    assert report.title == "Test Page - Best Widgets"
    assert report.meta_description == "A page about widgets."
    assert report.h1_count == 1
    assert report.total_images == 3
    # b.jpg has no alt attr, c.jpg has an empty alt -> both count as missing
    assert report.images_missing_alt == 2
    assert report.word_count > 0
    assert report.response_time_ms >= 0


@patch("app.core.requests.get")
def test_url_without_scheme_gets_https_prefixed(mock_get):
    mock_get.return_value = _mock_response()

    report = analyze_url("example.com")

    assert report.url == "https://example.com"


# ---------- Failure case 1: invalid input, never hits the network ----------

def test_empty_url_raises_invalid_url_error():
    with pytest.raises(InvalidURLError):
        analyze_url("")


def test_unsupported_scheme_raises_invalid_url_error():
    with pytest.raises(InvalidURLError):
        analyze_url("ftp://example.com/file")


# ---------- Failure case 2: network-level failures ----------

@patch("app.core.requests.get")
def test_timeout_raises_fetch_timeout_error(mock_get):
    mock_get.side_effect = requests.exceptions.Timeout()

    with pytest.raises(FetchTimeoutError):
        analyze_url("https://example.com")


@patch("app.core.requests.get")
def test_connection_error_raises_unreachable_error(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError()

    with pytest.raises(UnreachableError):
        analyze_url("https://example.com")


# ---------- Failure case 3: non-HTML response ----------

@patch("app.core.requests.get")
def test_non_html_response_raises_not_html_error(mock_get):
    mock_get.return_value = _mock_response(
        text='{"not": "html"}', content_type="application/json"
    )

    with pytest.raises(NotHTMLError):
        analyze_url("https://example.com/data.json")


# ---------- Parsing edge cases ----------

@patch("app.core.requests.get")
def test_missing_title_returns_none(mock_get):
    html = "<html><head></head><body><p>No title here.</p></body></html>"
    mock_get.return_value = _mock_response(text=html)

    report = analyze_url("https://example.com")

    assert report.title is None


@patch("app.core.requests.get")
def test_missing_meta_description_returns_none(mock_get):
    html = "<html><head><title>Only a title</title></head><body><p>Text.</p></body></html>"
    mock_get.return_value = _mock_response(text=html)

    report = analyze_url("https://example.com")

    assert report.meta_description is None


@patch("app.core.requests.get")
def test_multiple_h1s_counted_correctly(mock_get):
    html = """
    <html><head><title>T</title></head>
    <body><h1>One</h1><h1>Two</h1><h1>Three</h1></body></html>
    """
    mock_get.return_value = _mock_response(text=html)

    report = analyze_url("https://example.com")

    assert report.h1_count == 3
