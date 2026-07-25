# Page Pulse

A small tool that audits any URL and returns a JSON health report: HTTP status,
response time, title, meta description, H1 count, images missing `alt` text,
and approximate word count. Built for the Digital Heroes SDE internship task.

**Live demo:** _add your deployed Render URL here_

---

## Setup

```bash
git clone <your-repo-url>
cd page-pulse
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

uvicorn app.main:app --reload
```

Open `http://localhost:8000` — the frontend is served directly by FastAPI.

Run tests:

```bash
pytest tests/ -v
```

---

## API Contract

### `GET /api/analyze?url=<url>`

**Query params**

| Param | Type   | Required | Notes                                      |
|-------|--------|----------|---------------------------------------------|
| `url` | string | yes      | With or without scheme (`example.com` OK)  |

**Success — `200 OK`**

```json
{
  "url": "https://example.com",
  "status_code": 200,
  "response_time_ms": 154,
  "title": "Example Domain",
  "meta_description": "An example page.",
  "h1_count": 1,
  "images_missing_alt": 2,
  "total_images": 5,
  "word_count": 240
}
```

**Errors** — all return `{"detail": "<human readable message>"}`

| Status | When                                              |
|--------|---------------------------------------------------|
| `400`  | URL is empty, malformed, or uses an unsupported scheme |
| `408`  | Target site did not respond within 8 seconds       |
| `415`  | Target responded, but with non-HTML content        |
| `502`  | Target site is unreachable (DNS/connection failure) |

### `GET /health`
Liveness check, returns `{"status": "ok"}`. Used by the hosting platform.

---

## Design Decisions

**1. Core logic is separated from the FastAPI route (`app/core.py` vs `app/main.py`).**
`analyze_url()` raises plain Python exceptions and has zero knowledge of HTTP
status codes. The FastAPI route is the only place that maps exceptions to
status codes. This means the core logic is unit-testable without spinning up
a server or mocking `TestClient`, and it could be reused in a CLI or a queue
worker later without change.

**2. Four specific exception types instead of one generic error.**
`InvalidURLError`, `FetchTimeoutError`, `UnreachableError`, `NotHTMLError` each
map to a distinct, correct HTTP status (400/408/502/415) instead of collapsing
everything into a generic 500. A caller — human or frontend — gets an accurate
signal about what actually went wrong rather than an opaque "internal error."

**3. Word count strips `<script>` and `<style>` before counting.**
Counting raw text nodes would include JS/CSS content on script-heavy pages and
wildly overstate the "word count" a reader or search engine actually sees.
Stripping non-content tags first makes the number meaningful.

---

## What I'd change with another day

- Add a small on-disk/SQLite cache so re-auditing the same URL within a few
  minutes doesn't re-fetch it.
- Respect `robots.txt` before fetching.
- Add a Lighthouse-style overall score (0-100) instead of just raw metrics,
  so the report is scannable at a glance.
- Rate-limit the endpoint to prevent it being used as an open proxy/scraper.

---

## Where I used AI

Used Claude to scaffold the FastAPI/BeautifulSoup wiring and to write the
mocked pytest suite quickly. I changed the error-type mapping (added the
space-in-host edge case after testing it manually), rewrote the word-count
logic to strip script/style tags after noticing GitHub's raw word count was
inflated by inline JS, and wrote the frontend color-coding thresholds myself
based on what I'd actually want to see as an SEO signal.
