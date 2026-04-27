"""
Base Paths - Centralized path management for runtime directories.

Educational Note: This utility provides a single source of truth for all
project-related local paths. Most user data lives in Supabase (PostgreSQL +
Storage), but some local directories are still used for:
- Agent debug logs (data/projects/{id}/agents/)
- Temp file staging during source processing
- Background task tracking (data/tasks/)
- Project-level prompt overrides (data/projects/{id}.json)

Local Directory Structure:
    data/
    ├── projects/
    │   ├── {project_id}.json          # Project prompt config
    │   └── {project_id}/
    │       └── agents/
    │           └── web_agent/         # Agent execution logs (debug)
    │               └── {execution_id}.json
    └── tasks/                         # Background task tracking

User data (projects, sources, chats, messages, memory, costs) is stored
in Supabase. Files (raw uploads, processed text, chunks) are stored in
Supabase Storage.
"""
import logging
from pathlib import Path
from app.config.runtime import Config

logger = logging.getLogger(__name__)


# =============================================================================
# Base Directories
# =============================================================================

def get_data_dir() -> Path:
    """
    Get the main data directory.

    Educational Note: This is the root for all persistent data.
    Auto-creates if it doesn't exist.
    """
    path = Config.DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_projects_base_dir() -> Path:
    """
    Get the base projects directory (contains all project folders).

    Educational Note: This holds individual project directories.
    Auto-creates if it doesn't exist.
    """
    path = Config.PROJECTS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_tasks_dir() -> Path:
    """
    Get the tasks directory for background task tracking.
    """
    path = Config.DATA_DIR / "tasks"
    path.mkdir(parents=True, exist_ok=True)
    return path


# =============================================================================
# Project-Level Directories
# =============================================================================

def get_project_dir(project_id: str) -> Path:
    """
    Get a project's directory.

    Args:
        project_id: The project UUID

    Returns:
        Path to project directory (auto-created)
    """
    path = get_projects_base_dir() / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path


# =============================================================================
# Source Directories
# =============================================================================

def get_sources_dir(project_id: str) -> Path:
    """
    Get a project's sources directory.

    Args:
        project_id: The project UUID

    Returns:
        Path to sources directory (auto-created)
    """
    path = get_project_dir(project_id) / "sources"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_raw_dir(project_id: str) -> Path:
    """
    Get the raw files directory for a project.

    Educational Note: Original uploaded files are stored here.
    These are preserved even if processing fails, allowing retry.

    Args:
        project_id: The project UUID

    Returns:
        Path to raw/ directory (auto-created)
    """
    path = get_sources_dir(project_id) / "raw"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_processed_dir(project_id: str) -> Path:
    """
    Get the processed files directory for a project.

    Educational Note: Extracted text from PDFs, images, audio, etc.
    is saved here as .txt files with page markers.

    Args:
        project_id: The project UUID

    Returns:
        Path to processed/ directory (auto-created)
    """
    path = get_sources_dir(project_id) / "processed"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_chunks_dir(project_id: str) -> Path:
    """
    Get the chunks directory for a project.

    Educational Note: For large sources that need embedding,
    text is split into chunks stored in per-source subdirectories.

    Args:
        project_id: The project UUID

    Returns:
        Path to chunks/ directory (auto-created)
    """
    path = get_sources_dir(project_id) / "chunks"
    path.mkdir(parents=True, exist_ok=True)
    return path


# =============================================================================
# Agent Directories
# =============================================================================

def get_agents_dir(project_id: str) -> Path:
    """
    Get the agents directory for a project.

    Educational Note: Stores execution logs for agent runs
    (web_agent, etc.) for debugging purposes.

    Args:
        project_id: The project UUID

    Returns:
        Path to agents/ directory (auto-created)
    """
    path = get_project_dir(project_id) / "agents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_web_agent_dir(project_id: str) -> Path:
    """
    Get the web agent logs directory.

    Args:
        project_id: The project UUID

    Returns:
        Path to agents/web_agent/ directory (auto-created)
    """
    path = get_agents_dir(project_id) / "web_agent"
    path.mkdir(parents=True, exist_ok=True)
    return path


# =============================================================================
# Initialization
# =============================================================================

def ensure_base_directories() -> None:
    """
    Ensure all base directories exist.

    Educational Note: Call this on app startup to create the
    directory structure before any files are accessed.
    This prevents FileNotFoundError on first use.
    """
    get_data_dir()
    get_projects_base_dir()
    get_tasks_dir()
    logger.info("Base directories initialized")
