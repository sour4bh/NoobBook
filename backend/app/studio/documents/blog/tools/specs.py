"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class GenerateBlogImageInput(ContractModel):
    alt_text: str = Field(description='Accessibility-friendly alt text describing the image for screen readers')
    aspect_ratio: Literal['1:1', '16:9', '4:3', '3:2', '21:9'] = Field(description='Aspect ratio for the image. 16:9 for hero images, 4:3 for inline content images, 1:1 for square visuals, 21:9 for ultra-wide banners')
    image_prompt: str = Field(description='Detailed image generation prompt describing the visual style, subject, composition, and mood. Be specific and descriptive for best results.')
    purpose: str = Field(description="The purpose of this image (e.g., 'hero_image', 'section_illustration', 'concept_visual', 'infographic_style')")
    section_heading: str = Field(description='The section heading this image relates to (from your outline)')
class PlanBlogPostInputOutlineItemModel(ContractModel):
    content_description: str = Field(description='What content will be covered in this section')
    heading: str = Field(description='Section heading (will be H2 in the blog)')
    image_description: Optional[str] = Field(default=None, description='Description of the image needed (if needs_image is true)')
    needs_image: bool = Field(description='True if this section would benefit from a generated image')
    subsections: Optional[list[str]] = Field(default=None, description='Optional subsection headings (will be H3)')
class PlanBlogPostInput(ContractModel):
    estimated_word_count: int = Field(description='Estimated word count for the complete post (should be 3000+)')
    key_takeaways: list[str] = Field(description='3-5 key takeaways readers should get from this post')
    meta_description: str = Field(description='Compelling meta description for search engines (150-160 characters) that includes the target keyword')
    outline: list[PlanBlogPostInputOutlineItemModel] = Field(description='Detailed outline of blog sections with descriptions')
    target_audience: str = Field(description="Who is this blog post written for? (e.g., 'marketing professionals', 'small business owners', 'beginners')")
    title: str = Field(description='SEO-optimized blog post title that includes the target keyword (60-70 characters ideal)')
    tone: Literal['professional', 'conversational', 'educational', 'persuasive', 'casual', 'authoritative'] = Field(description='The writing tone/voice for this blog post')
class WriteBlogPostInput(ContractModel):
    markdown_content: str = Field(description='REQUIRED: The complete blog post in Markdown format. Must include: YAML frontmatter (title, meta_description, target_keyword, author, date), H1 title, all sections with H2/H3 headings, image placeholders as ![alt text](IMAGE_1), bullet points, bold/italic formatting, and a conclusion with call-to-action. Should be 3000+ words, comprehensive, and publish-ready. Reference generated images using IMAGE_1, IMAGE_2, etc. placeholders.')
    seo_notes: str = Field(description='Brief notes on SEO optimization applied (keyword placement, heading structure, etc.)')
    word_count: int = Field(description='Actual word count of the blog post (should be 3000+)')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='generate_blog_image',
        description='Generate an image for use in the blog post. Use this for hero images, concept illustrations, or section visuals. You can call this multiple times for different sections (recommended: 2-4 images per post).',
        input_model=GenerateBlogImageInput,
        terminates_run=False,
        metadata={'registry_name': 'generate_blog_image'},
    ),
    LocalToolSpec(
        name='plan_blog_post',
        description='Plan the structure, outline, and content strategy for the blog post. Call this first to establish the post structure before generating images or writing content.',
        input_model=PlanBlogPostInput,
        terminates_run=False,
        metadata={'registry_name': 'plan_blog_post'},
    ),
    LocalToolSpec(
        name='write_blog_post',
        description='FINAL STEP: Write the complete blog post in Markdown format. YOU MUST provide the full blog content in the markdown_content parameter - this is not optional. The markdown_content parameter must contain the entire blog post (3000+ words). This is the termination tool - call this only when you have the complete blog post ready.',
        input_model=WriteBlogPostInput,
        terminates_run=True,
        metadata={'registry_name': 'write_blog_post'},
    ),
)
