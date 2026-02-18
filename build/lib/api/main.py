"""
Main FastAPI application for intelligent document processing.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from .config import ApiConfig
from .routes import router
from ..storage.storage import get_storage
from ..observability import setup_observability

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Intelligent Document Processing API")
    try:
        get_storage().ensure_all_containers_ready()
        logger.info("Storage container initialized")
    except Exception as exc:
        logger.error("Storage initialization failed: %s", exc)
    yield
    logger.info("Shutting down Intelligent Document Processing API")


api_config = ApiConfig()
templates = Jinja2Templates(directory="src/api/templates")

app = FastAPI(
    title="Intelligent Document Processing API",
    description="Upload, trigger, and monitor asynchronous ACU document processing.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    debug=api_config.debug,
    lifespan=lifespan,
)
setup_observability(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=api_config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1", tags=["documents"])


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": "The requested resource was not found",
            "detail": f"Path: {request.url.path}",
        },
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    logger.error("Internal server error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An internal server error occurred",
            "detail": str(exc) if api_config.debug else None,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=api_config.host,
        port=api_config.port,
        reload=api_config.reload and not api_config.is_production,
        log_level="debug" if api_config.debug else "info",
    )
