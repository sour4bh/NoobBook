"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class CreateBaseStylesInput(ContractModel):
    content: str = Field(description='Complete CSS content for base-styles.css. Must include: 1) Google Font import, 2) CSS variables in :root for all brand colors (--brand-primary, --brand-secondary, --brand-accent, --brand-text, --brand-bg, --brand-light), 3) Body reset with font-family, 4) Utility classes that reference the variables (.text-brand-primary, .bg-brand-primary, etc.). NO layout classes - use Tailwind for that.')
class CreateSlideInput(ContractModel):
    content: str = Field(description="Complete HTML content for the slide. MUST include: 1) Full <!DOCTYPE html> structure, 2) Tailwind CDN and Font Awesome in head, 3) Link to base-styles.css, 4) Body with 'm-0 p-0 w-screen h-screen overflow-hidden', 5) Inner div with 'w-full h-full overflow-hidden flex items-center justify-center p-20', 6) All slide content inside the inner div using only Tailwind + brand utility classes.")
    slide_number: int = Field(description='The slide number (1-20). Will create file named slide_01.html, slide_02.html, etc.', ge=1, le=20)
    slide_type: Literal['title', 'section_divider', 'bullet_points', 'two_column', 'quote', 'statistics', 'image_focus', 'comparison', 'timeline', 'closing'] = Field(description='The layout type for this slide')
class FinalizePresentationInputSlidesCreatedItemModel(ContractModel):
    filename: str = Field(description="The slide filename (e.g., 'slide_01.html')")
    title: str = Field(description='The slide title/heading')
    type: str = Field(description='The slide layout type')
class FinalizePresentationInput(ContractModel):
    design_notes: Optional[str] = Field(default=None, description='Notes about the design choices made (colors, fonts, style)')
    slides_created: list[FinalizePresentationInputSlidesCreatedItemModel] = Field(description='List of all slides created with their titles and types')
    summary: str = Field(description='Brief summary of the completed presentation including topic, number of slides, and key sections covered')
    total_slides: int = Field(description='Total number of slides created', ge=1, le=20)
class PlanPresentationInputDesignSystemModel(ContractModel):
    accent_color: Optional[str] = Field(default=None, description='Accent color for highlights and CTAs (hex code)')
    background_color: str = Field(description="Slide background color (hex code, e.g., '#ffffff')")
    font_family: Optional[str] = Field(default=None, description="Google Font family name (e.g., 'Inter', 'Poppins', 'Montserrat')")
    primary_color: str = Field(description="Primary brand color (hex code, e.g., '#2563eb')")
    secondary_color: str = Field(description='Secondary color (hex code)')
    text_color: str = Field(description="Primary text color (hex code, e.g., '#1f2937')")
class PlanPresentationInputSlidesItemModel(ContractModel):
    key_points: Optional[list[str]] = Field(default=None, description='Main points to cover on this slide (max 6)', max_length=6)
    slide_number: int = Field(description='Sequential slide number (1, 2, 3, ...)')
    slide_type: Literal['title', 'section_divider', 'bullet_points', 'two_column', 'quote', 'statistics', 'image_focus', 'comparison', 'timeline', 'closing'] = Field(description='The layout type for this slide')
    title: str = Field(description='The slide title/heading')
class PlanPresentationInput(ContractModel):
    design_system: PlanPresentationInputDesignSystemModel = Field(description='Color scheme and typography')
    presentation_title: str = Field(description='The main title of the presentation')
    presentation_type: Literal['business', 'educational', 'pitch', 'report', 'training', 'marketing', 'technical'] = Field(description='The type/purpose of the presentation')
    slides: list[PlanPresentationInputSlidesItemModel] = Field(description='Array of slides to create (3-20 slides typical)', min_length=3, max_length=20)
    style_notes: Optional[str] = Field(default=None, description='Additional notes about style, tone, or specific requirements from the user')
    target_audience: Optional[str] = Field(default=None, description="Brief description of the intended audience (e.g., 'executives', 'developers', 'students')")


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='create_base_styles',
        description='Create the base-styles.css file with brand colors as CSS variables and utility classes. This MUST be created BEFORE any slides. Contains only brand identity - no layout styles.',
        input_model=CreateBaseStylesInput,
        terminates_run=False,
        metadata={'registry_name': 'create_base_styles'},
    ),
    LocalToolSpec(
        name='create_slide',
        description='Create an individual slide as an HTML file. Each slide must use the exact HTML structure with Tailwind CDN, link to base-styles.css, and fit all content within the safebox area (1920x1080 viewport with p-20 padding = ~1760x920 usable area). Use only Tailwind classes and brand utility classes from base-styles.css. NO inline styles, NO hex colors in HTML.',
        input_model=CreateSlideInput,
        terminates_run=False,
        metadata={'registry_name': 'create_slide'},
    ),
    LocalToolSpec(
        name='finalize_presentation',
        description='TERMINATION TOOL: Call this when all slides have been created and the presentation is complete. This signals that presentation generation is finished. base-styles.css and all slides must be created before calling this. Do not call until everything is production-ready.',
        input_model=FinalizePresentationInput,
        terminates_run=True,
        metadata={'registry_name': 'finalize_presentation'},
    ),
    LocalToolSpec(
        name='plan_presentation',
        description='Plan the complete presentation structure including slides, content distribution, and design system. This is the first step - analyze the source content and create a comprehensive plan before creating any files.',
        input_model=PlanPresentationInput,
        terminates_run=False,
        metadata={'registry_name': 'plan_presentation'},
    ),
)
