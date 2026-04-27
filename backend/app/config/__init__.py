"""Configuration package bootstrap.

Importing this package registers every domain-owned prompt and tool asset path.
Callers should import concrete modules such as `app.config.prompt`,
`app.config.tool`, `app.config.provider`, or `app.config.runtime`.
"""

import app.config.asset as asset
from app.config.asset import (
    AssetNotFoundError,
    register_prompt_path,
    register_tool_category,
    register_tool_path,
)


asset.register_production_asset_paths()

__all__ = [
    "AssetNotFoundError",
    "asset",
    "register_prompt_path",
    "register_tool_category",
    "register_tool_path",
]
