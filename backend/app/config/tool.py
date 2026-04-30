"""
Typed tool spec loader.

Tool contracts are Python/Pydantic first after NBB-1104. Domain-owned
``tools/specs.py`` files expose ``TOOL_SPECS`` and this loader returns those
provider-neutral specs. Provider-specific schemas are compiled only by provider
adapters.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import app.config.asset as asset
from app.agents.runtime.tool import ToolSpec, validate_tool_spec


class ToolLoader:
    """Load domain-owned ``ToolSpec`` objects through stable category keys."""

    def __init__(self):
        self._spec_cache: dict[Path, tuple[ToolSpec, ...]] = {}

    def _load_module(self, specs_path: Path) -> ModuleType:
        module_name = "_noobbook_tool_specs_" + str(abs(hash(specs_path)))
        module_spec = importlib.util.spec_from_file_location(module_name, specs_path)
        if module_spec is None or module_spec.loader is None:
            raise FileNotFoundError(f"Cannot import tool specs from {specs_path}")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        return module

    def _load_specs_from_dir(self, directory: Path) -> tuple[ToolSpec, ...]:
        specs_path = directory / "specs.py"
        if specs_path in self._spec_cache:
            return self._spec_cache[specs_path]
        if not specs_path.exists():
            return ()

        module = self._load_module(specs_path)
        raw_specs = getattr(module, "TOOL_SPECS", ())
        specs = tuple(validate_tool_spec(spec) for spec in raw_specs)
        self._spec_cache[specs_path] = specs
        return specs

    def _registry_name(self, spec: ToolSpec) -> str:
        value = spec.metadata.get("registry_name")
        return value if isinstance(value, str) else spec.name

    def _file_registered_specs(self, category: str) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for tool_name, directory in asset.iter_tool_file_candidate_dirs(category):
            for spec in self._load_specs_from_dir(directory):
                if self._registry_name(spec) == tool_name:
                    specs.append(spec)
        return specs

    def _category_registered_specs(self, category: str) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for directory in asset.iter_tool_category_dirs(category):
            specs.extend(self._load_specs_from_dir(directory))
        return specs

    def _all_specs_for_category(self, category: str) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        seen: set[tuple[str, str]] = set()
        for spec in [
            *self._file_registered_specs(category),
            *self._category_registered_specs(category),
        ]:
            key = (self._registry_name(spec), spec.name)
            if key in seen:
                continue
            seen.add(key)
            specs.append(spec)
        return specs

    def load_tool_spec(self, category: str, tool_name: str) -> ToolSpec:
        """Load one provider-neutral tool spec by stable category/name key."""
        for spec in self._all_specs_for_category(category):
            if self._registry_name(spec) == tool_name:
                return spec

        available = self.get_available_categories()
        raise FileNotFoundError(
            f"Tool definition not found for category={category!r} "
            f"tool={tool_name!r}.\n"
            f"Available registered categories: {available}"
        )

    def get_available_categories(self) -> list[str]:
        categories: list[str] = []
        seen: set[str] = set()
        for category in asset.registered_tool_categories():
            if category not in seen:
                categories.append(category)
                seen.add(category)
        return categories

    def get_available_tools(self, category: str) -> list[str]:
        return [
            self._registry_name(spec)
            for spec in self._all_specs_for_category(category)
        ]

    def load_tool_specs_for_agent(self, category: str) -> tuple[ToolSpec, ...]:
        """Return provider-neutral specs for runtime callers."""
        specs = self._all_specs_for_category(category)
        if not specs:
            available = self.get_available_categories()
            raise FileNotFoundError(
                f"Tool category not found: {category!r}\n"
                f"Available registered categories: {available}"
            )
        return tuple(specs)


tool_loader = ToolLoader()
