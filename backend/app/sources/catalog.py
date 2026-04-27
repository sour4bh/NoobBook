"""
Source Catalog - Business logic for managing project sources.

Educational Note: This service provides the main interface for source operations.
It delegates to specialized modules for cleaner code organization:
- sources.index: Index CRUD operations
- sources.upload: Upload handling (file, URL, text)
- sources.pipeline: Processing orchestration

CRUD Operations are kept here for backwards compatibility with API routes.
"""
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
from werkzeug.datastructures import FileStorage

from app.sources.upload.file import upload_file, create_from_existing_file
from app.sources.upload.url import upload_url
from app.sources.upload.text import upload_text
from app.sources.analysis.database.upload import add_database_source
from app.sources.analysis.freshdesk.upload import add_freshdesk_source
from app.sources.analysis.jira.upload import add_jira_source
from app.sources.analysis.mcp.upload import add_mcp_source
from app.sources.analysis.mixpanel.upload import add_mixpanel_source
from app.sources.analysis.research.upload import upload_research
from app.base.paths import (
    get_raw_dir,
    get_processed_dir,
    get_chunks_dir
)
from app.sources.file_contract import ALLOWED_EXTENSIONS
from app.sources import index


logger = logging.getLogger(__name__)
# Local path utils used for temp file staging during source processing


class SourceCatalog:
    """
    Service class for managing project sources.

    Educational Note: This is the main entry point for source operations.
    Most logic has been delegated to specialized modules, keeping this
    class focused on orchestrating the modules and providing a clean API.
    """

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    def list_sources(self, project_id: str) -> List[Dict[str, Any]]:
        """
        List all sources for a project.

        Args:
            project_id: The project UUID

        Returns:
            List of source metadata dictionaries (newest first)
        """
        return index.list_sources_from_index(project_id)

    def get_source(self, project_id: str, source_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific source's metadata.

        Args:
            project_id: The project UUID
            source_id: The source UUID

        Returns:
            Source metadata or None if not found
        """
        return index.get_source_from_index(project_id, source_id)

    def get_source_file_url(self, project_id: str, source_id: str) -> Optional[str]:
        """
        Get a signed URL for downloading a source's raw file from Supabase Storage.

        Args:
            project_id: The project UUID
            source_id: The source UUID

        Returns:
            Signed URL for the raw file or None if not found
        """
        from app.providers.supabase import storage_service

        source = self.get_source(project_id, source_id)
        if not source:
            return None

        # Get stored filename from embedding_info
        embedding_info = source.get("embedding_info", {})
        stored_filename = embedding_info.get("stored_filename", "")

        if not stored_filename:
            return None

        return storage_service.get_raw_file_url(
            project_id=project_id,
            source_id=source_id,
            filename=stored_filename
        )

    def get_source_file_data(self, project_id: str, source_id: str) -> Optional[tuple]:
        """
        Download a source's raw file from Supabase Storage.

        Args:
            project_id: The project UUID
            source_id: The source UUID

        Returns:
            Tuple of (file_data bytes, stored_filename) or None if not found
        """
        from app.providers.supabase import storage_service

        source = self.get_source(project_id, source_id)
        if not source:
            return None

        # Get stored filename from embedding_info
        embedding_info = source.get("embedding_info", {})
        stored_filename = embedding_info.get("stored_filename", "")

        if not stored_filename:
            return None

        file_data = storage_service.download_raw_file(
            project_id=project_id,
            source_id=source_id,
            filename=stored_filename
        )

        if file_data:
            return (file_data, stored_filename)

        return None

    def update_source(
        self,
        project_id: str,
        source_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        active: Optional[bool] = None,
        processing_info: Optional[Dict[str, Any]] = None,
        embedding_info: Optional[Dict[str, Any]] = None,
        summary_info: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update a source's metadata.

        Args:
            project_id: The project UUID
            source_id: The source UUID
            name: New display name (optional)
            description: New description (optional)
            status: New status (optional)
            active: Whether source is included in chat context (optional)
            processing_info: Processing details (optional)
            embedding_info: Embedding details (optional)
            summary_info: Summary details (optional)

        Returns:
            Updated source metadata or None if not found
        """
        # Build updates dict with non-None values
        updates = {}

        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description
        if status is not None:
            updates["status"] = status
            # Auto-activate when status becomes ready
            if status == "ready":
                updates["is_active"] = True
        if active is not None:
            updates["is_active"] = active
        if processing_info is not None:
            updates["processing_info"] = processing_info
        if embedding_info is not None:
            updates["embedding_info"] = embedding_info
        if summary_info is not None:
            updates["summary_info"] = summary_info

        result = index.update_source_in_index(project_id, source_id, updates)

        return result

    def delete_source(self, project_id: str, source_id: str) -> bool:
        """
        Delete a source, its raw file, processed content, and embeddings.

        Educational Note: When deleting a source, we clean up:
        1. Raw file (original upload)
        2. Processed file (extracted text)
        3. Chunk files (individual page files)
        4. Pinecone vectors and chunk files

        Args:
            project_id: The project UUID
            source_id: The source UUID

        Returns:
            True if deleted, False if not found
        """
        source = self.get_source(project_id, source_id)
        if not source:
            return False

        # Delete embeddings and chunk files from Supabase Storage (if any)
        if source.get("embedding_info", {}).get("is_embedded"):
            try:
                from app.sources.embedding import delete_embeddings
                delete_embeddings(
                    project_id=project_id,
                    source_id=source_id
                )
            except Exception as e:
                logger.error("Error deleting embeddings for %s: %s", source_id, e)

        # Stop Freshdesk auto-sync if this is a Freshdesk source
        file_ext = (source.get("embedding_info") or {}).get("file_extension", "")
        if file_ext == ".freshdesk":
            try:
                from app.connectors.freshdesk.sync import freshdesk_sync_service
                freshdesk_sync_service.stop_auto_sync()
            except Exception as e:
                logger.error("Error stopping Freshdesk auto-sync for %s: %s", source_id, e)

        # Delete all files from Supabase Storage
        from app.providers.supabase import storage_service

        # Get stored filename from embedding_info
        embedding_info = source.get("embedding_info", {})
        stored_filename = embedding_info.get("stored_filename", "")

        if stored_filename:
            # Delete raw file, processed file, and chunks
            storage_service.delete_source_files(project_id, source_id, stored_filename)

        # Remove from index
        index.remove_source_from_index(project_id, source_id)

        return True

    def get_sources_summary(self, project_id: str) -> Dict[str, Any]:
        """
        Get a summary of sources for a project.

        Returns:
            Dictionary with source counts by category and total size
        """
        sources = self.list_sources(project_id)

        summary = {
            "total_count": len(sources),
            "total_size": sum(s.get("file_size", 0) for s in sources),
            "by_category": {},
            "by_status": {}
        }

        for source in sources:
            # Count by category
            category = source.get("category", "unknown")
            if category not in summary["by_category"]:
                summary["by_category"][category] = 0
            summary["by_category"][category] += 1

            # Count by status
            status = source.get("status", "unknown")
            if status not in summary["by_status"]:
                summary["by_status"][status] = 0
            summary["by_status"][status] += 1

        return summary

    def get_allowed_extensions(self) -> dict:
        """
        Get the allowed file extensions and their categories.

        Returns:
            Dictionary mapping extensions to categories
        """
        return ALLOWED_EXTENSIONS.copy()

    # =========================================================================
    # Source Upload/Creation
    # =========================================================================

    def upload_source(
        self,
        project_id: str,
        file: FileStorage,
        name: Optional[str] = None,
        description: str = ""
    ) -> Dict[str, Any]:
        """
        Upload a new source file to a project.

        Delegates to sources/upload/file.py.
        """
        return upload_file(project_id, file, name, description)

    def create_source_from_file(
        self,
        project_id: str,
        file_path: Path,
        name: str,
        original_filename: str,
        category: str,
        mime_type: str,
        description: str = ""
    ) -> Dict[str, Any]:
        """
        Create a source entry from an already-saved file.

        Delegates to sources/upload/file.py.
        """
        return create_from_existing_file(
            project_id, file_path, name, original_filename,
            category, mime_type, description
        )

    def add_url_source(
        self,
        project_id: str,
        url: str,
        name: Optional[str] = None,
        description: str = ""
    ) -> Dict[str, Any]:
        """
        Add a URL source (website or YouTube link) to a project.

        Delegates to sources/upload/url.py.
        """
        return upload_url(project_id, url, name, description)

    def add_text_source(
        self,
        project_id: str,
        content: str,
        name: str,
        description: str = ""
    ) -> Dict[str, Any]:
        """
        Add a pasted text source to a project.

        Delegates to sources/upload/text.py.
        """
        return upload_text(project_id, content, name, description)

    def add_research_source(
        self,
        project_id: str,
        topic: str,
        description: str,
        links: List[str] = None
    ) -> Dict[str, Any]:
        """
        Add a deep research source to a project.

        Delegates to sources/analysis/research/upload.py.
        """
        return upload_research(project_id, topic, description, links)

    def add_database_source(
        self,
        project_id: str,
        connection_id: str,
        name: Optional[str] = None,
        description: str = "",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a database source (Postgres/MySQL) to a project.

        Educational Note: This creates a DATABASE source that stores a small
        `.database` metadata file in Supabase Storage and triggers processing
        to fetch a schema snapshot + embeddings.
        """
        if user_id:
            return add_database_source(
                project_id,
                connection_id,
                name,
                description,
                user_id=user_id,
            )
        return add_database_source(project_id, connection_id, name, description)

    def add_freshdesk_source(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: str = "",
        days_back: int = 30,
    ) -> Dict[str, Any]:
        """
        Add a Freshdesk ticket source to a project.

        Educational Note: This creates a Freshdesk source that stores a small
        `.freshdesk` metadata file in Supabase Storage and triggers processing
        to sync tickets and make them queryable via the analysis agent.
        """
        return add_freshdesk_source(project_id, name, description, days_back)

    def add_jira_source(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Add a Jira source flag to a project.

        Educational Note: Lightweight source that enables the existing Jira
        API tools (jira_list_projects, jira_search_issues, etc.) for this
        specific project. No data sync — tools query Jira live.
        """
        return add_jira_source(project_id, name, description)

    def add_mixpanel_source(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Add a Mixpanel source flag to a project.

        Educational Note: Same lightweight pattern as Jira — enables Mixpanel
        chat tools (mixpanel_list_events, mixpanel_query_events, etc.) for
        this specific project. Queries Mixpanel's Query API live.
        """
        return add_mixpanel_source(project_id, name, description)

    def add_mcp_source(
        self,
        project_id: str,
        connection_id: str,
        resource_uris: List[str],
        name: Optional[str] = None,
        description: str = "",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add an MCP source to a project.

        Educational Note: This creates an MCP source that stores a small
        `.mcp` metadata file in Supabase Storage and triggers processing
        to snapshot selected resources, embed them, and make them searchable.
        """
        if user_id:
            return add_mcp_source(
                project_id,
                connection_id,
                resource_uris,
                name,
                description,
                user_id=user_id,
            )
        return add_mcp_source(project_id, connection_id, resource_uris, name, description)

    # =========================================================================
    # Processing Delegation (thin wrappers)
    # =========================================================================

    def cancel_processing(self, project_id: str, source_id: str) -> bool:
        """
        Cancel processing for a source.

        Delegates to sources.pipeline.
        """
        from app.sources.pipeline import source_pipeline
        return source_pipeline.cancel_processing(project_id, source_id)

    def retry_processing(self, project_id: str, source_id: str) -> Dict[str, Any]:
        """
        Retry processing for a source that failed or was cancelled.

        Delegates to sources.pipeline.
        """
        from app.sources.pipeline import source_pipeline
        return source_pipeline.retry_processing(project_id, source_id)

    # =========================================================================
    # Path helpers retained for source processing callers.
    # =========================================================================

    def _get_raw_dir(self, project_id: str) -> Path:
        """Get raw directory."""
        return get_raw_dir(project_id)

    def _get_processed_dir(self, project_id: str) -> Path:
        """Get processed directory."""
        return get_processed_dir(project_id)

    def _get_chunks_dir(self, project_id: str) -> Path:
        """Get chunks directory."""
        return get_chunks_dir(project_id)


# Singleton instance
source_service = SourceCatalog()
