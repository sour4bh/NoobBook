"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class SaveMemoryInput(ContractModel):
    memory: str = Field(description='The final merged memory content. Must be concise (max 150 tokens) and capture the most important information from both existing and new memory.')
    memory_type: Literal['user', 'project'] = Field(description='The type of memory being saved.')
class StoreMemoryInput(ContractModel):
    project_memory: Optional[str] = Field(default=None, description='Important information specific to this project. Examples: project goals, what the user is trying to achieve, key milestones, decisions made, progress notes. Leave empty if no project-level memory to store.')
    user_memory: Optional[str] = Field(default=None, description='Important information about the user that should persist across all projects. Examples: name, preferences, communication style, general goals, expertise level. Leave empty if no user-level memory to store.')
    why_generated: str = Field(description='Brief explanation of why this memory is being stored. Helps with future context and memory management.')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='save_memory',
        description='Save the merged and condensed memory. You MUST use this tool to output the final memory after merging existing and new memory content.',
        input_model=SaveMemoryInput,
        terminates_run=False,
        metadata={'registry_name': 'manage_memory_tool'},
    ),
    LocalToolSpec(
        name='store_memory',
        description="Store important information in memory for future conversations. Use this tool to remember user preferences, goals, important context, and project-specific information. Only use for significant details that should persist across conversations - NOT for trivial or temporary information.\n\nWhen to use:\n- User explicitly states a preference (e.g., 'I prefer concise answers', 'Call me John')\n- User shares important context about themselves or their goals\n- Project-related insights that should be remembered (e.g., 'This project is for my thesis on AI')\n- Key decisions or milestones in the project\n\nWhen NOT to use:\n- Temporary information that only matters for current conversation\n- Information already available in sources\n- Trivial details or greetings never pass user memory and project memory in together when using this tool, only one memory tyoe user or project at a time",
        input_model=StoreMemoryInput,
        terminates_run=False,
        metadata={'registry_name': 'memory_tool'},
    ),
)

# Keep static tool contracts out of memory workflow code. The tool catalog and
# provider adapters need to discover model-visible schemas without importing the
# effectful merge path. Domains can choose how much hierarchy they need, but the
# contract/effect split is the boundary this runtime relies on.
