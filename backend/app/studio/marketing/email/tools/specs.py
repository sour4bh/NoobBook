"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class GenerateEmailImageInput(ContractModel):
    aspect_ratio: Literal['1:1', '16:9', '4:3', '3:2', '9:16'] = Field(description='Aspect ratio for the image based on section layout. 16:9 for wide hero banners, 1:1 for square product images, 4:3 for content images')
    image_prompt: str = Field(description='Detailed image generation prompt describing the visual style, subject, composition, and mood. Be specific and descriptive.')
    section_name: str = Field(description="The section name from your plan that needs this image (e.g., 'hero_banner', 'product_showcase')")
class PlanEmailTemplateInputColorSchemeModel(ContractModel):
    background: str = Field(description='Background color (hex code, usually light)')
    button: str = Field(description='Call-to-action button color (hex code)')
    primary: str = Field(description="Primary brand color (hex code, e.g., '#3B82F6')")
    secondary: str = Field(description='Secondary accent color (hex code)')
    text: str = Field(description='Primary text color (hex code, usually dark for readability)')
class PlanEmailTemplateInputSectionsItemModel(ContractModel):
    content_description: str = Field(description='What content will go in this section')
    image_description: Optional[str] = Field(default=None, description='Description of the image needed (if needs_image is true)')
    needs_image: bool = Field(description='True if this section needs a generated image (photo/illustration only, not icons)')
    section_name: str = Field(description="Unique name for this section (e.g., 'hero_banner', 'product_showcase')")
    section_type: Literal['header', 'hero', 'content', 'product_grid', 'cta', 'testimonial', 'footer'] = Field(description='Type of section')
class PlanEmailTemplateInput(ContractModel):
    color_scheme: PlanEmailTemplateInputColorSchemeModel
    layout_notes: Optional[str] = Field(default=None, description='Additional notes about layout, spacing, or special design requirements')
    sections: list[PlanEmailTemplateInputSectionsItemModel] = Field(description='Ordered list of email sections from top to bottom')
    template_name: str = Field(description="A descriptive name for this email template (e.g., 'Product Launch Email', 'Monthly Newsletter')")
    template_type: Literal['newsletter', 'promotional', 'transactional', 'announcement'] = Field(description='The type of email template to create')
class WriteEmailCodeInput(ContractModel):
    html_code: str = Field(description="REQUIRED: The complete HTML email template. Must be a full, working HTML document with inline CSS, table-based layout, and all content. Structure: <!DOCTYPE html><html><head><meta charset='UTF-8'><title>...</title><style>/* media queries */</style></head><body><table width='600' cellpadding='0' cellspacing='0'><!-- all content with inline styles --></table></body></html>. Reference generated images as IMAGE_1, IMAGE_2, etc. Keep concise (3000-6000 characters). Must be production-ready and compatible with Gmail, Outlook, Apple Mail.")
    preheader_text: Optional[str] = Field(default=None, description='Preheader text that appears in email client preview (50-100 characters, optional)')
    subject_line_suggestion: str = Field(description='Suggested email subject line based on the content (required)')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='generate_email_image',
        description='Generate an image for use in the email template. Use this only for photos, illustrations, or complex graphics - NOT for icons, buttons, or simple shapes (use CSS/SVG for those). You can call this multiple times for different sections.',
        input_model=GenerateEmailImageInput,
        terminates_run=False,
        metadata={'registry_name': 'generate_email_image'},
    ),
    LocalToolSpec(
        name='plan_email_template',
        description='Plan the structure, color scheme, and content sections for the email template. Call this first to establish the template design before generating images or writing code.',
        input_model=PlanEmailTemplateInput,
        terminates_run=False,
        metadata={'registry_name': 'plan_email_template'},
    ),
    LocalToolSpec(
        name='write_email_code',
        description='FINAL STEP: Write the complete HTML email template code. YOU MUST provide the full HTML code in the html_code parameter - this is not optional. The html_code parameter must contain the entire working HTML template from <!DOCTYPE html> to </html>. This is the termination tool - call this only when you have the complete HTML ready.',
        input_model=WriteEmailCodeInput,
        terminates_run=True,
        metadata={'registry_name': 'write_email_code'},
    ),
)
