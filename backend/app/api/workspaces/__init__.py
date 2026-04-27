"""Workspace membership API blueprint."""

from flask import Blueprint

workspaces_bp = Blueprint("workspaces", __name__)

from app.api.workspaces import routes  # noqa: F401
