"""Typed prompt specs for this domain."""

from app.config.prompt import PromptSpec

_SUMMARY_SYSTEM_PROMPT = """\
You are a document summarizer. Your task is to generate a concise, informative summary of the provided content. STRICT RULES: 1) Output ONLY the summary text - no greetings, no introductions like 'Here is the summary', no closing remarks. 2) The summary must be 150-200 tokens (approximately 600-800 characters). 3) Focus on: core topic/purpose, key points, main arguments or findings, and practical takeaways. 4) Write in clear, professional prose - not bullet points, no special text formatting or markdown formatting. 5) Capture the essence and direction of the document. You will receive context about the document including its type, total length, and how much content is being provided. Use this context to inform your summary appropriately."""

_SUMMARY_USER_MESSAGE = """\
DOCUMENT CONTEXT:
Document Type: {document_type} ({file_extension})
Document Name: {document_name}
Total Document Length: {total_pages} pages/sections
{content_info}

DOCUMENT CONTENT:
{content}"""

SUMMARY_PROMPT = PromptSpec(
    name='summary',
    description='System prompt for generating concise summaries of processed sources',
    default_provider='anthropic',
    default_model='claude-haiku-4-5-20251001',
    model_category='extraction',
    max_tokens=250,
    temperature=0.0,
    system_prompt=_SUMMARY_SYSTEM_PROMPT,
    user_message=_SUMMARY_USER_MESSAGE,
    version='1.0',
    metadata={'created_at': '2025-11-29T00:00:00.000000', 'updated_at': '2025-11-29T00:00:00.000000'},
)

PROMPT = SUMMARY_PROMPT
