"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class AddWireframeSectionInputElementsItemModel(ContractModel):
    backgroundColor: Optional[str] = Field(default=None, description="Fill color. Use 'transparent' for no fill, #f5f5f5 for light gray, #e0e0e0 for medium gray, #333333 for dark.")
    fillStyle: Optional[Literal['solid', 'hachure', 'cross-hatch']] = Field(default=None, description="Fill pattern. Use 'hachure' for sketchy look (default), 'solid' for buttons/important elements, 'cross-hatch' for image placeholders.")
    fontSize: Optional[float] = Field(default=None, description='Font size for text. Use 28 for headings, 20 for subheadings, 16 for body, 12 for small text.')
    height: Optional[float] = Field(default=None, description='Height in pixels (for rectangle, ellipse, diamond)')
    label: Optional[str] = Field(default=None, description='Optional label to display inside/near the element')
    points: Optional[list[list[float]]] = Field(default=None, description='For line/arrow: array of [x,y] points relative to element position.')
    strokeColor: Optional[str] = Field(default=None, description='Border/stroke color. Use #000000 for dark, #666666 for medium, #aaaaaa for light.')
    text: Optional[str] = Field(default=None, description='Text content (for text elements, or label inside shapes)')
    type: Literal['rectangle', 'text', 'line', 'arrow', 'ellipse', 'diamond'] = Field(description='Element type. Use rectangle for containers/buttons/cards/images, text for labels, line for separators, arrow for flows, ellipse for avatars/icons, diamond for decision points.')
    width: Optional[float] = Field(default=None, description='Width in pixels (for rectangle, ellipse, diamond)')
    x: float = Field(description='X position from left edge')
    y: float = Field(description='Y position from top edge')
class AddWireframeSectionInput(ContractModel):
    elements: list[AddWireframeSectionInputElementsItemModel] = Field(description='Array of Excalidraw elements for this section')
    section_name: str = Field(description='Name of the section being generated (must match a section from plan_wireframe)')
class FinalizeWireframeInputFinalElementsItemModel(ContractModel):
    backgroundColor: Optional[str] = None
    fillStyle: Optional[str] = None
    fontSize: Optional[float] = None
    height: Optional[float] = None
    points: Optional[list[list[float]]] = None
    strokeColor: Optional[str] = None
    text: Optional[str] = None
    type: Literal['rectangle', 'text', 'line', 'arrow', 'ellipse', 'diamond']
    width: Optional[float] = None
    x: float
    y: float
class FinalizeWireframeInput(ContractModel):
    canvas_height: Optional[float] = Field(default=None, description='Final canvas height (adjust based on total content height)')
    canvas_width: Optional[float] = Field(default=None, description='Final canvas width (if different from plan)')
    final_elements: Optional[list[FinalizeWireframeInputFinalElementsItemModel]] = Field(default=None, description='Optional final elements to add (annotations, connecting lines, etc.)')
    summary: str = Field(description='Final summary describing the complete wireframe')
class PlanWireframeInputSectionsItemModel(ContractModel):
    description: Optional[str] = Field(default=None, description='Optional: What this section contains')
    name: str = Field(description="Section name (e.g., 'Header', 'Hero', 'Features', 'Footer')")
    y_end: float = Field(description='Ending Y position for this section')
    y_start: float = Field(description='Starting Y position for this section')
class PlanWireframeInput(ContractModel):
    canvas_height: Optional[float] = Field(default=None, description='Canvas height in pixels. Default 800, increase for longer pages.')
    canvas_width: Optional[float] = Field(default=None, description='Canvas width in pixels. Default 1200 for desktop, 400 for mobile.')
    description: Optional[str] = Field(default=None, description='Brief description of what this wireframe represents')
    sections: list[PlanWireframeInputSectionsItemModel] = Field(description='List of sections to create. Each section will be generated in a separate step.')
    title: str = Field(description="Title for this wireframe (e.g., 'Homepage Layout', 'Dashboard View')")
class GenerateWireframeInputElementsItemModel(ContractModel):
    backgroundColor: Optional[str] = Field(default=None, description="Fill color. Use 'transparent' for no fill, #f5f5f5 for light gray, #e0e0e0 for medium gray, #333333 for dark.")
    fillStyle: Optional[Literal['solid', 'hachure', 'cross-hatch']] = Field(default=None, description="Fill pattern. Use 'hachure' for sketchy look (default), 'solid' for buttons/important elements, 'cross-hatch' for image placeholders.")
    fontSize: Optional[float] = Field(default=None, description='Font size for text. Use 28 for headings, 20 for subheadings, 16 for body, 12 for small text.')
    height: Optional[float] = Field(default=None, description='Height in pixels (for rectangle, ellipse, diamond)')
    label: Optional[str] = Field(default=None, description='Optional label to display inside/near the element (for rectangles representing components)')
    points: Optional[list[list[float]]] = Field(default=None, description='For line/arrow: array of [x,y] points relative to element position. E.g., [[0,0], [100,0]] for horizontal line.')
    strokeColor: Optional[str] = Field(default=None, description='Border/stroke color. Use #000000 for dark, #666666 for medium, #aaaaaa for light.')
    text: Optional[str] = Field(default=None, description='Text content (for text elements, or label inside shapes)')
    type: Literal['rectangle', 'text', 'line', 'arrow', 'ellipse', 'diamond'] = Field(description='Element type. Use rectangle for containers/buttons/cards/images, text for labels, line for separators, arrow for flows, ellipse for avatars/icons, diamond for decision points.')
    width: Optional[float] = Field(default=None, description='Width in pixels (for rectangle, ellipse, diamond)')
    x: float = Field(description='X position from left edge')
    y: float = Field(description='Y position from top edge')
class GenerateWireframeInput(ContractModel):
    canvas_height: Optional[float] = Field(default=None, description='Canvas height in pixels. Default 800.')
    canvas_width: Optional[float] = Field(default=None, description='Canvas width in pixels. Default 1200 for desktop, 400 for mobile.')
    description: Optional[str] = Field(default=None, description='Brief description of what this wireframe represents')
    elements: list[GenerateWireframeInputElementsItemModel] = Field(description='Array of Excalidraw elements that make up the wireframe')
    title: str = Field(description="Title for this wireframe (e.g., 'Homepage Layout', 'Login Screen', 'Dashboard View')")


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='add_wireframe_section',
        description='Add wireframe elements for a specific section. Call this for EACH section defined in plan_wireframe. Generate all elements needed for that section.',
        input_model=AddWireframeSectionInput,
        terminates_run=False,
        metadata={'registry_name': 'add_wireframe_section'},
    ),
    LocalToolSpec(
        name='finalize_wireframe',
        description='Complete the wireframe generation. Call this AFTER all sections have been added. You can optionally add any final connecting elements or annotations.',
        input_model=FinalizeWireframeInput,
        terminates_run=True,
        metadata={'registry_name': 'finalize_wireframe'},
    ),
    LocalToolSpec(
        name='plan_wireframe',
        description='Plan the wireframe structure by defining sections. Call this FIRST to establish the layout plan before generating elements. Each section will be generated separately to ensure complete coverage.',
        input_model=PlanWireframeInput,
        terminates_run=False,
        metadata={'registry_name': 'plan_wireframe'},
    ),
    LocalToolSpec(
        name='generate_wireframe',
        description='Generate a wireframe using Excalidraw elements. Create UI/UX wireframe layouts with rectangles, text, lines, and arrows. Position elements using x,y coordinates where (0,0) is top-left. Use width/height for sizing. Standard canvas is 1200x800.',
        input_model=GenerateWireframeInput,
        terminates_run=True,
        metadata={'registry_name': 'wireframe_tool'},
    ),
)
