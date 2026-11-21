"""KABAMAN API process. Phase 1A serves GET /api/health and nothing else."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.config import load_settings


def create_app() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/api/health")
    def health() -> JSONResponse:
        return JSONResponse(content={"ok": True})

    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
