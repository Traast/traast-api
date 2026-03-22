from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI, Request
import structlog

from app.config.settings import settings
from app.routers import health, roles

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(settings.log_level),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("traast-api starting", environment=settings.environment)
    yield
    logger.info("traast-api shutting down")


app = FastAPI(
    title="Traast API",
    description="Core backend API — coordination, workflow, billing",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(roles.router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        service="traast-api",
        environment=settings.environment,
    )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
