from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from config import Settings
from core.errors import Problem
from core.routes import router
from database import session_factory


def create_app(settings=None, factory=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        yield
        for session in list(app.state.voice_sessions.values()):
            await session.close()

    app = FastAPI(title="Saarthi v2", debug=False, lifespan=lifespan)
    app.state.voice_sessions = {}
    app.state.settings = settings
    app.state.db = factory or session_factory(settings.database_url)

    @app.middleware("http")
    async def browser_boundary(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("origin") != settings.app_origin:
                return JSONResponse(
                    {
                        "error": {
                            "code": "invalid_origin",
                            "message": "Request origin is not allowed.",
                        }
                    },
                    status_code=403,
                )
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(
                    {
                        "error": {
                            "code": "invalid_origin",
                            "message": "Cross-site requests are not allowed.",
                        }
                    },
                    status_code=403,
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(Problem)
    async def problem_handler(request, exc):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message, **exc.details}},
            status_code=exc.status,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        # Validation input/context can contain secrets; expose field locations only.
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_input",
                    "message": "Check the submitted fields.",
                    "fields": [".".join(map(str, e["loc"])) for e in exc.errors()],
                }
            },
            status_code=422,
        )

    @app.exception_handler(HTTPException)
    async def http_handler(request, exc):
        return JSONResponse(
            {"error": {"code": "http_error", "message": str(exc.detail)}},
            status_code=exc.status_code,
        )

    @app.exception_handler(IntegrityError)
    async def constraint_handler(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "conflict",
                    "message": "This operation conflicts with saved data. Refresh and retry.",
                }
            },
            status_code=409,
        )

    @app.exception_handler(Exception)
    async def unexpected_handler(request, exc):
        return JSONResponse(
            {"error": {"code": "internal_error", "message": "The request failed. Please retry."}},
            status_code=500,
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(router)
    from voice.routes import router as voice_router

    app.include_router(voice_router)
    client = Path(__file__).resolve().parent.parent / "client"
    app.mount("/static", StaticFiles(directory=client), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(client / "index.html")

    return app


app = create_app()
