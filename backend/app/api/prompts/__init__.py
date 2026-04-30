"""
Prompts API Blueprint.

Educational Note: System prompts are the instructions that shape how the
configured assistant responds in conversations. This blueprint manages:

1. Project Prompts:
   - Each project can have a custom system prompt
   - If no custom prompt, falls back to default
   - Stored in local project config files

2. Default Prompt:
   - Global fallback stored as a typed PromptSpec in the chat domain
   - Used when projects don't have custom prompts

Why System Prompts Matter:
- They set the assistant's persona and behavior
- They define what tools are available and how to use them
- They provide context about the user's sources
- They're the foundation of prompt engineering
"""
from flask import Blueprint, request

# Create blueprint for prompt management
prompts_bp = Blueprint('prompts', __name__)


# Verify project ownership for prompt routes that have a project_id
# (skips global routes like /prompts/default and /prompts/all)
from app.api.auth.middleware import verify_project_access  # noqa: E402

@prompts_bp.before_request
def check_project_access():
    if request.method == 'OPTIONS':
        return None
    project_id = request.view_args.get('project_id') if request.view_args else None
    if project_id:
        denied = verify_project_access(project_id)
        if denied:
            return denied


# Import routes to register them with the blueprint
from app.api.prompts import routes  # noqa: F401, E402
