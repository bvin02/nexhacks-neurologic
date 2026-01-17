"""
DecisionOS - Project Continuity Copilot

FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db, close_db
from .config import settings
from .api import projects_router, chat_router, memory_router, ops_router
from .tracer import setup_follow_through_logging

# Configure logging based on mode
if settings.debug:
    log_level = logging.DEBUG
elif settings.follow_through:
    log_level = logging.WARNING  # Suppress normal logs, let tracer handle output
else:
    log_level = logging.INFO

logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Quiet down noisy loggers when not in debug mode
if not settings.debug:
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

# Setup follow-through tracing
setup_follow_through_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting DecisionOS...")
    
    # Validate provider key
    try:
        settings.validate_provider_key()
        logger.info(f"Using LLM provider: {settings.llm_provider}")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise
    
    # Initialize database
    await init_db()
    logger.info("Database initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down DecisionOS...")
    await close_db()


# Create FastAPI app
app = FastAPI(
    title="DecisionOS",
    description="""
    Project Continuity Copilot - A persistent cognitive layer for building things.
    
    DecisionOS fixes a core failure of stateless LLMs: they do not remember why 
    things were decided, what was tried before, or what constraints still apply.
    
    ## Features
    - **Persistent Memory**: Durable project memory that survives across sessions
    - **Typed Memories**: Decisions, commitments, constraints, goals, failures
    - **Enforcement**: Detects violations against commitments and constraints
    - **Versioning**: Full history of how decisions evolved
    - **Conflict Detection**: Identifies contradictions automatically
    - **Receipts**: Every answer is backed by citations to source material
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(projects_router)
app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(ops_router)


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "DecisionOS",
        "version": "1.0.0",
        "description": "Project Continuity Copilot",
        "provider": settings.llm_provider,
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
