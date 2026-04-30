"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class CreateFileInput(ContractModel):
    content: str = Field(description='COMPLETE file content. Must be production-ready and properly formatted. For HTML: full structure from <!DOCTYPE html> to </html> including Tailwind CDN, navigation (identical across all pages), page-specific content, footer (identical across all pages), and script links. Use IMAGE_1, IMAGE_2, etc. as placeholders for generated images. For CSS: complete stylesheet with custom styles only (use Tailwind for 90%+ of styling). For JS: complete script with all interactivity. Keep concise but complete: HTML 3k-10k chars, CSS 500-2k chars, JS 1k-5k chars.')
    filename: str = Field(description='Filename to create. For HTML: index.html, about.html, contact.html, services.html, portfolio.html, blog.html, etc. For CSS: styles.css. For JS: script.js')
class FinalizeWebsiteInput(ContractModel):
    cdn_libraries_used: Optional[list[str]] = Field(default=None, description="List of CDN libraries used in the website (e.g., ['Tailwind CSS', 'Font Awesome', 'AOS Animations', 'Google Fonts'])")
    features_implemented: list[str] = Field(description="List of features successfully implemented (e.g., ['responsive_navigation', 'contact_form', 'image_gallery', 'scroll_animations'])")
    pages_created: list[str] = Field(description="List of HTML page filenames created (e.g., ['index.html', 'about.html', 'contact.html'])")
    summary: str = Field(description='Brief summary of the completed website including pages created, key features implemented, and any important notes for the user')
class GenerateWebsiteImageInput(ContractModel):
    aspect_ratio: Literal['1:1', '16:9', '4:3', '3:2', '9:16', '21:9'] = Field(description='Aspect ratio for the image. Choose based on usage: 16:9 for hero backgrounds, 1:1 for avatars/logos, 4:3 for content images, 3:2 for portfolio items')
    image_prompt: str = Field(description="Detailed image generation prompt. Describe the desired image in detail including style, mood, colors, composition, and specific elements. Be specific and descriptive for best results. Example: 'Modern minimalist hero image with abstract geometric shapes in blue and purple gradients, clean professional aesthetic, high-end corporate feel, 3D rendered style with soft lighting'")
    purpose: str = Field(description="What the image is for (e.g., 'hero_background', 'about_section_photo', 'portfolio_item_1', 'team_member_ceo'). This will be used in the tracking system.")
class InsertCodeInput(ContractModel):
    after_line: float = Field(description='Line number after which to insert the new code (1-indexed). The new content will be inserted AFTER this line. Use 0 to insert at the very beginning of the file. Use read_file first to find the correct insertion point.')
    content: str = Field(description='The code to insert. Must maintain proper indentation and structure to match surrounding code. For HTML: ensure tags are properly closed. For CSS: ensure rules are complete. For JS: ensure syntax is valid and functions are complete.')
    filename: str = Field(description='The file to insert code into (HTML, CSS, or JS)')
class PlanWebsiteInputDesignSystemModel(ContractModel):
    accent_color: Optional[str] = Field(default=None, description='Accent color for CTAs and highlights (hex code)')
    background_color: Optional[str] = Field(default=None, description="Background color (hex code, e.g., '#ffffff' or '#f9fafb')")
    font_family: Optional[str] = Field(default=None, description="Google Font family name (e.g., 'Inter', 'Poppins', 'Roboto')")
    primary_color: str = Field(description="Primary color (hex code, e.g., '#2563eb')")
    secondary_color: str = Field(description='Secondary color (hex code)')
    text_color: str = Field(description="Primary text color (hex code, e.g., '#1f2937')")
class PlanWebsiteInputImagesNeededItemModel(ContractModel):
    aspect_ratio: Literal['1:1', '16:9', '4:3', '3:2', '9:16', '21:9'] = Field(description='Aspect ratio for the image')
    description: str = Field(description='Detailed description for image generation')
    purpose: str = Field(description="What the image is for (e.g., 'hero_background', 'portfolio_item_1', 'team_photo_ceo')")
class PlanWebsiteInputPagesItemModel(ContractModel):
    description: str = Field(description='Brief description of page content and purpose')
    filename: str = Field(description="The HTML filename (e.g., 'index.html', 'about.html')")
    page_title: str = Field(description='The page title for <title> tag')
class PlanWebsiteInput(ContractModel):
    design_system: PlanWebsiteInputDesignSystemModel = Field(description='Color scheme and typography for Tailwind config')
    features: list[Literal['animations_scroll', 'animations_hover', 'gallery_grid', 'gallery_lightbox', 'contact_form', 'newsletter_signup', 'testimonials', 'accordion_faq', 'mobile_menu', 'smooth_scroll', 'video_embed', 'social_links', 'blog_preview', 'pricing_table']] = Field(description='Features to implement in the website')
    images_needed: Optional[list[PlanWebsiteInputImagesNeededItemModel]] = Field(default=None, description='List of images to generate (photos/illustrations only, not icons)')
    layout_notes: Optional[str] = Field(default=None, description='Additional notes about layout, structure, or specific requirements')
    navigation_style: Literal['fixed', 'sticky', 'static'] = Field(description='Navigation bar style (fixed stays at top, sticky scrolls then sticks, static scrolls normally)')
    pages: list[PlanWebsiteInputPagesItemModel] = Field(description='Array of pages to create (1-8 pages). Must include index.html as first page.', min_length=1, max_length=8)
    site_name: str = Field(description='The name/title of the website')
    site_type: Literal['portfolio', 'business', 'blog', 'landing', 'corporate', 'personal', 'ecommerce'] = Field(description='The type of website based on content analysis')
class ReadFileInput(ContractModel):
    end_line: Optional[float] = Field(default=None, description='Ending line number (1-indexed, optional). If omitted, reads from start_line to end of file. If provided with start_line, reads the specified range with context.')
    filename: str = Field(description='The file to read. Can be any HTML page (index.html, about.html, contact.html, services.html, portfolio.html, blog.html, etc.), styles.css, or script.js')
    start_line: Optional[float] = Field(default=None, description='Starting line number (1-indexed, optional). If omitted for files over 100 lines, returns overview (first 50 + last 50 lines). If provided, returns this line through end_line (or end of file) with 5 lines of context on each side.')
class UpdateFileLinesInput(ContractModel):
    end_line: float = Field(description='Ending line number to replace (1-indexed, inclusive). Lines start_line through end_line will be replaced with new_content.')
    filename: str = Field(description='The file to update (HTML, CSS, or JS)')
    new_content: str = Field(description='The new code to replace the specified line range. Must maintain proper indentation and structure to match surrounding code. Ensure HTML tags are properly closed, CSS rules are complete, and JS syntax is valid.')
    start_line: float = Field(description='Starting line number to replace (1-indexed, inclusive). Use read_file first to find the correct line numbers.')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='create_file',
        description='Create a new website file. If file already exists, this will COMPLETELY OVERWRITE it. Use this for initial file creation or complete rewrites. For HTML: must include full <!DOCTYPE html> structure with Tailwind CDN, proper <head> section, navigation, content, footer, and script links. For CSS: complete stylesheet with any custom styles. For JS: complete script with all functionality. Each file must be production-ready and self-contained.',
        input_model=CreateFileInput,
        terminates_run=False,
        metadata={'registry_name': 'create_file'},
    ),
    LocalToolSpec(
        name='finalize_website',
        description='TERMINATION TOOL: Call this when the website is complete and all files have been created. This signals that website generation is finished. All HTML pages must be created with consistent navigation and footer, styles.css and script.js must be complete, and all features must be implemented. Do not call this until everything is production-ready.',
        input_model=FinalizeWebsiteInput,
        terminates_run=True,
        metadata={'registry_name': 'finalize_website'},
    ),
    LocalToolSpec(
        name='generate_website_image',
        description='Generate an image for the website (photos, illustrations, backgrounds only - not icons or simple shapes). Use CSS/SVG for icons, buttons, dividers, and decorative elements. Can be called multiple times to generate all needed images.',
        input_model=GenerateWebsiteImageInput,
        terminates_run=False,
        metadata={'registry_name': 'generate_website_image'},
    ),
    LocalToolSpec(
        name='insert_code',
        description='Insert new code at a specific position in an existing file. The code will be inserted AFTER the specified line number, pushing existing content down. Use this to add new sections without replacing existing code. IMPORTANT: Always use read_file FIRST to see current structure and determine correct insertion point.',
        input_model=InsertCodeInput,
        terminates_run=False,
        metadata={'registry_name': 'insert_code'},
    ),
    LocalToolSpec(
        name='plan_website',
        description='Plan the complete website structure including pages, features, design system, and navigation. This is the first step - analyze the source content and create a comprehensive plan before generating any files.',
        input_model=PlanWebsiteInput,
        terminates_run=False,
        metadata={'registry_name': 'plan_website'},
    ),
    LocalToolSpec(
        name='read_file',
        description='Read a website file (HTML, CSS, or JS) with smart context awareness. For files under 100 lines, returns entire file. For larger files, returns overview (first 50 + last 50 lines) unless specific line range is requested. Automatically adds 5 lines of context around requested ranges. ALWAYS use this before updating or inserting code to see current structure and line numbers.',
        input_model=ReadFileInput,
        terminates_run=False,
        metadata={'registry_name': 'read_file'},
    ),
    LocalToolSpec(
        name='update_file_lines',
        description='Replace a specific line range in an existing file with new code. Use this to modify or refine existing sections. IMPORTANT: Always use read_file FIRST to see the current content and determine correct line numbers. The specified line range will be completely replaced with the new content.',
        input_model=UpdateFileLinesInput,
        terminates_run=False,
        metadata={'registry_name': 'update_file_lines'},
    ),
)
