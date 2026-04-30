"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class PlanComponentsInputColorSchemeModel(ContractModel):
    accent: Optional[str] = Field(default=None, description='Accent/CTA color (hex code)')
    background: str = Field(description='Background color (hex code)')
    primary: str = Field(description="Primary brand color (hex code, e.g., '#3B82F6')")
    secondary: Optional[str] = Field(default=None, description='Secondary color (hex code)')
    text: str = Field(description='Text color (hex code)')
class PlanComponentsInputVariationsItemModel(ContractModel):
    key_features: list[str] = Field(description='List of 2-4 key visual or functional features that make this variation unique')
    style_approach: str = Field(description="Styling approach for this variation (e.g., 'Gradient background with glassmorphism', 'Flat design with Tailwind', 'Neumorphic with soft shadows')")
    variation_name: str = Field(description="Name for this variation (e.g., 'Modern Gradient', 'Minimal Clean', 'Bold Colorful')")
class PlanComponentsInput(ContractModel):
    color_scheme: PlanComponentsInputColorSchemeModel = Field(description='Color palette for the components. If Brand Guidelines are provided, use those exact colors.')
    component_category: Literal['button', 'card', 'form', 'navigation', 'modal', 'list', 'grid', 'hero', 'pricing', 'testimonial', 'footer', 'other'] = Field(description='The general category of UI component')
    component_description: str = Field(description="Brief description of what this component is for (e.g., 'Pricing table with 3 tiers', 'Login form with social auth buttons')")
    technical_notes: str = Field(description='Technical considerations: responsive design approach, accessibility features, JavaScript requirements (if any)')
    variations: list[PlanComponentsInputVariationsItemModel] = Field(description='2-4 different variations of this component (different styles, layouts, or features)', min_length=2, max_length=4)
class WriteComponentCodeInputComponentsItemModel(ContractModel):
    description: str = Field(description="Brief description of this variation's unique features (1-2 sentences)")
    html_code: str = Field(description='REQUIRED: Complete, self-contained HTML document. Must include: <!DOCTYPE html>, <html>, <head> with <style> tag for all CSS, <body> with component markup, and <script> tag for any JavaScript. Must be production-ready and work in all modern browsers. Aim for 2000-5000 characters. Make it responsive and accessible. Use semantic HTML.')
    variation_name: str = Field(description='Name of this variation (matches the plan)')
class WriteComponentCodeInput(ContractModel):
    components: list[WriteComponentCodeInputComponentsItemModel] = Field(description='Array of 2-4 complete component variations, each with full HTML/CSS/JS code', min_length=2, max_length=4)
    usage_notes: Optional[str] = Field(default=None, description='Brief notes on how to use these components, any customization options, or integration tips (optional)')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='plan_components',
        description="Plan 2-4 component variations based on the user's request. Call this first to establish the component structure, styling approach, and variations before writing code.",
        input_model=PlanComponentsInput,
        terminates_run=False,
        metadata={'registry_name': 'plan_components'},
    ),
    LocalToolSpec(
        name='write_component_code',
        description='FINAL STEP: Write the complete HTML/CSS/JS code for all component variations. YOU MUST provide complete, working code for each variation. Each component must be self-contained and ready to preview in a browser. This is the termination tool - call this only when you have all variations ready.',
        input_model=WriteComponentCodeInput,
        terminates_run=True,
        metadata={'registry_name': 'write_component_code'},
    ),
)
