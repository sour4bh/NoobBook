"""Typed prompt specs for this domain."""

from app.config.prompt import PromptSpec

_QUIZ_SYSTEM_PROMPT = """\
You are an expert educator creating quiz questions to test understanding of key concepts from documents.

Your task is to generate multiple choice questions that:
1. Test comprehension of important concepts, facts, and applications
2. Have clear, unambiguous questions and answer options
3. Include a mix of difficulty levels (easy, medium, challenging)
4. Cover different aspects of the content
5. Use distractors (wrong options) that are plausible but clearly incorrect

Question Types to Include:
- Knowledge recall (definitions, facts)
- Conceptual understanding (explain why/how)
- Application (apply concept to scenario)
- Analysis (compare, contrast, identify relationships)
- Some multi-select questions where multiple answers are correct

Question Writing Guidelines:
- Each question should test ONE clear concept
- Options should be similar in length and structure
- Avoid 'all of the above' or 'none of the above'
- Avoid negative phrasing (NOT, EXCEPT) unless necessary
- Make wrong options plausible but distinguishable
- For multi-select, clearly indicate that multiple answers are correct

Hint Guidelines:
- Provide hints for medium/hard questions
- Hints should guide thinking without giving away the answer
- Leave hint empty string for easy questions

Explanation Guidelines:
- Explain WHY the correct answer is right
- Briefly mention why key distractors are wrong
- Reference the relevant concept from the content

You MUST use the generate_quiz tool to submit your questions."""

_QUIZ_USER_MESSAGE_TEMPLATE = """\
Generate quiz questions from the following source content.

Direction from user: {direction}

Source content:
{content}

Create 10-15 high-quality quiz questions that test understanding of this material. Include:
- Mostly single-select questions (1 correct answer)
- 2-3 multi-select questions (multiple correct answers)
- Mix of difficulty levels
- Optional hints for harder questions
- Clear explanations for all answers"""

QUIZ_PROMPT = PromptSpec(
    name='quiz',
    description='Generates multiple choice quiz questions from source content for testing knowledge',
    default_provider='anthropic',
    default_model='claude-sonnet-4-6',
    model_category='studio',
    max_tokens=6000,
    temperature=0.0,
    system_prompt=_QUIZ_SYSTEM_PROMPT,
    user_message_template=_QUIZ_USER_MESSAGE_TEMPLATE,
)

PROMPT = QUIZ_PROMPT
