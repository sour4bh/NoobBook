"""Typed prompt specs for this domain."""

from app.config.prompt import PromptSpec

_MEMORY_SYSTEM_PROMPT = """\
You are a memory manager. Your task is to merge existing memory with new memory content and create a concise, updated memory.

RULES:
1. You MUST use the save_memory tool to output the final memory
2. Maximum 150 tokens for the merged memory
3. Prioritize: recent/new information, user preferences, important goals, key context
4. Remove: outdated information, redundancies, trivial details
5. Write in concise notes format (can use short phrases, not full sentences)
6. Preserve the most important facts from existing memory while incorporating new information
7. If new information contradicts existing memory, prefer the new information"""

_MEMORY_USER_MESSAGE = """\
Memory Type: {memory_type}

Current Memory:
{current_memory}

New Memory to Incorporate:
{new_memory}

Reason for Update:
{reason}

Please merge the current memory with the new memory, creating a concise updated memory (max 150 tokens). Use the save_memory tool to output the result."""

MEMORY_PROMPT = PromptSpec(
    name='memory',
    description='System prompt for merging and condensing memory content',
    default_provider='anthropic',
    default_model='claude-haiku-4-5-20251001',
    model_category='chat',
    max_tokens=400,
    temperature=0.0,
    system_prompt=_MEMORY_SYSTEM_PROMPT,
    user_message=_MEMORY_USER_MESSAGE,
    version='1.0',
    metadata={'created_at': '2025-11-29T00:00:00.000000', 'updated_at': '2025-11-29T00:00:00.000000'},
)

PROMPT = MEMORY_PROMPT
