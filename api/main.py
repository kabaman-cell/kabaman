"""KABAMAN API process. Phase 1A health stays in place and Phase 1C routers are registered."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.config import load_settings
from api.routes.auth import login, logout, register
from api.routes.employees import login as employee_login
from api.routes.me import current


def create_app() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_api_route("/api/register", register, methods=["POST"])
    app.add_api_route("/api/login", login, methods=["POST"])
    app.add_api_route("/api/logout", logout, methods=["POST"])
    app.add_api_route("/api/employee/login", employee_login, methods=["POST"])
    app.add_api_route("/api/me", current, methods=["GET"])

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
