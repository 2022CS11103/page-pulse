"""
Page Pulse - FastAPI entrypoint.

Design decision: errors from app.core are mapped to specific HTTP status
codes here (not inside core.py) so the core module stays framework-agnostic
and easy to unit test.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core import (
    FetchTimeoutError,
    InvalidURLError,
    NotHTMLError,
    PageReport,
    UnreachableError,
    analyze_url,
)

app = FastAPI(
    title="Page Pulse",
    description="Audits a URL and returns an on-page SEO/health report.",
    version="1.0.0",
)

# Wide open for this take-home; in a real product this would be locked to
# the actual frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


class AnalyzeResponse(BaseModel):
    url: str
    status_code: int
    response_time_ms: int
    title: str | None
    meta_description: str | None
    h1_count: int
    images_missing_alt: int
    total_images: int
    word_count: int


class ErrorResponse(BaseModel):
    error: str
    detail: str


@app.get("/api/analyze", response_model=AnalyzeResponse, responses={
    400: {"model": ErrorResponse, "description": "Invalid URL"},
    408: {"model": ErrorResponse, "description": "Upstream request timed out"},
    415: {"model": ErrorResponse, "description": "Response was not HTML"},
    502: {"model": ErrorResponse, "description": "Target site unreachable"},
})
def analyze(url: str = Query(..., description="The URL to audit, e.g. https://example.com")):
    try:
        report: PageReport = analyze_url(url)
        return report.to_dict()
    except InvalidURLError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FetchTimeoutError as e:
        raise HTTPException(status_code=408, detail=str(e))
    except NotHTMLError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except UnreachableError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve the single-page frontend at "/" and static assets under /static.
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
