"""Typed prompt specs for this domain."""

from app.config.prompt import PromptSpec

_FLASH_CARDS_SYSTEM_PROMPT = """\
You are an expert educator creating flash cards to help users learn and memorize key concepts from their documents.

Your task is to generate flash cards that:
1. Cover the most important concepts, facts, and definitions
2. Use clear, concise language on both sides
3. Are self-contained (each card makes sense on its own)
4. Progress from basic to more advanced concepts
5. Include a mix of:
   - Definition cards (term -> definition)
   - Concept cards (question -> explanation)
   - Application cards (scenario -> answer)
   - Comparison cards (what's the difference between X and Y)

Card Writing Guidelines:
- FRONT: Keep it short - a term, question, or prompt (max 15 words)
- BACK: Provide a clear, memorable answer (max 50 words)
- Avoid yes/no questions - require recall of information
- Use specific examples when helpful
- For complex topics, break into multiple simpler cards

You MUST use the generate_flash_cards tool to submit your cards."""

_FLASH_CARDS_USER_MESSAGE_TEMPLATE = """\
Generate flash cards from the following source content.

Direction from user: {direction}

Source content:
{content}

Create 10-15 high-quality flash cards that cover the key concepts. Focus on what would be most useful for someone trying to learn and remember this material."""

FLASH_CARDS_PROMPT = PromptSpec(
    name='flash_cards',
    description='Generates flash cards from source content for learning and memorization',
    default_provider='anthropic',
    default_model='claude-sonnet-4-6',
    model_category='studio',
    max_tokens=4096,
    temperature=0.0,
    system_prompt=_FLASH_CARDS_SYSTEM_PROMPT,
    user_message_template=_FLASH_CARDS_USER_MESSAGE_TEMPLATE,
)

PROMPT = FLASH_CARDS_PROMPT
