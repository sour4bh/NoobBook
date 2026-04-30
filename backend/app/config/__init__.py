"""Configuration package bootstrap.

Importing this package registers domain-owned tool-spec paths. Built-in
prompts are typed Python modules discovered by `app.config.prompt`.
Callers should import concrete modules such as `app.config.prompt`,
`app.config.tool`, `app.config.provider`, or `app.config.runtime`.
"""

import app.config.asset as asset
from app.config.asset import (
    register_tool_category,
    register_tool_path,
)


asset.register_production_asset_paths()

__all__ = [
    "asset",
    "register_tool_category",
    "register_tool_path",
]
