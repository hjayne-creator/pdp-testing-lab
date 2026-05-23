from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, auth, lab, models, settings
from app.api.auth import SESSION_COOKIE_NAME, is_auth_enabled, verify_session_token
from app.config import get_settings
from app.models.db import init_db
from app.repositories.run_history import prune_runs

settings_cfg = get_settings()

app = FastAPI(title="PDP Testing Lab", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings_cfg.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    init_db()
    prune_runs()
    if not settings_cfg.serpapi_api_key:
        logging.getLogger(__name__).warning(
            "SERPAPI_API_KEY is not set. %s",
            settings_cfg.missing_api_key_hint("SERPAPI_API_KEY"),
        )


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.middleware("http")
async def require_auth(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if path == "/health" or path.startswith("/auth"):
        return await call_next(request)
    if not is_auth_enabled():
        return await call_next(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if verify_session_token(token):
        return await call_next(request)
    return JSONResponse(status_code=401, content={"detail": "Authentication required."})


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(settings.router, prefix="/settings", tags=["settings"])
app.include_router(models.router, prefix="/models", tags=["models"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(lab.router, prefix="/lab", tags=["lab"])
