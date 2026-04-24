"""
Data Services - CRUD operations for data entities.

Educational Note: This folder contains services that manage data persistence
and entity lifecycle. These are NOT AI-powered services - they handle
reading, writing, and organizing data stored in Supabase (PostgreSQL).

Services:
- chat_service: Chat CRUD operations (create, list, get, update, delete)
- project_service: Project CRUD operations and settings management
- message_service: Message persistence, context building, and tool response parsing
- brand_asset_service: Brand asset CRUD (logos, icons, fonts, images)
- brand_config_service: Brand configuration management (colors, typography, etc.)

These services typically:
- Work with Supabase tables for persistence
- Handle entity metadata and relationships
- Provide structured queries for efficient lookups
"""
from app.services.data_services.chat_service import chat_service
from app.projects.store import project_service
from app.services.data_services.message_service import message_service
from app.brand.asset.store import brand_asset_service
from app.brand.config.store import brand_config_service
from app.connectors.database.connection.store import database_connection_service
from app.services.data_services.user_service import get_user_service

__all__ = [
    "chat_service",
    "project_service",
    "message_service",
    "brand_asset_service",
    "brand_config_service",
    "database_connection_service",
    "get_user_service",
]
