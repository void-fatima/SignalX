from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.errors import AppError
from app.agents.pipeline import get_provider
from app.api.routes.main import router
from app.api.routes.auth import router as auth_router
from app.schemas.api import ErrorOut
from app.integrations.telegram.routes import router as telegram_router, webhook_router


@asynccontextmanager
async def lifespan(app):
    get_provider(settings().provider_mode)
    yield


app = FastAPI(title="singnalX API", version="0.1.0", lifespan=lifespan,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}, 502: {"model": ErrorOut}})
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in settings().cors_origins.split(",") if origin.strip()],
    allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["Content-Type", "Idempotency-Key", "Authorization"])


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    # Avoid writing provider bodies, credentials, user data or SQL parameters to logs.
    logging.getLogger(__name__).error("Unexpected API error; sensitive exception details withheld")
    return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "An unexpected server error occurred", "details": []}})


@app.exception_handler(AppError)
async def app_error(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "Invalid request",
        "details": [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]}})


app.include_router(router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(telegram_router, prefix="/api/v1")
app.include_router(webhook_router)
