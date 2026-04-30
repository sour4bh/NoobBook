"""OpenAI Responses schema compilation for Pydantic-owned contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Type

from pydantic import BaseModel

from app.agents.runtime.tool import LocalToolSpec, McpProxyToolSpec


_UNSUPPORTED_SCHEMA_KEYS = {
    "dependentRequired",
    "dependentSchemas",
    "if",
    "then",
    "else",
    "not",
    "patternProperties",
    "propertyNames",
    "unevaluatedProperties",
}


def strict_model_schema(model: Type[BaseModel]) -> dict[str, Any]:
    """Compile a Pydantic model to the OpenAI-supported JSON schema subset."""
    schema = deepcopy(model.model_json_schema(by_alias=True))
    _normalize_node(schema)
    return schema


def function_schema(tool: LocalToolSpec | McpProxyToolSpec) -> dict[str, Any]:
    """Compile a local runtime tool into an OpenAI Responses function tool."""
    parameters = strict_model_schema(tool.input_model)
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": parameters,
        "strict": True,
    }


def response_format(model: Type[BaseModel]) -> dict[str, Any]:
    """Compile a Pydantic model for Responses structured output."""
    schema = strict_model_schema(model)
    return {
        "format": {
            "type": "json_schema",
            "name": model.__name__,
            "schema": schema,
            "strict": True,
        }
    }


def _normalize_node(node: Any) -> None:
    if isinstance(node, list):
        for item in node:
            _normalize_node(item)
        return
    if not isinstance(node, dict):
        return

    _reject_unsupported(node)
    node.pop("default", None)

    properties = node.get("properties")
    if node.get("type") == "object" or isinstance(properties, dict):
        additional = node.get("additionalProperties")
        if additional is True:
            raise ValueError(
                "OpenAI strict schema does not support free-form object "
                "properties; model this field with a typed Pydantic contract "
                "or a string payload validated at the external boundary"
            )
        if isinstance(additional, dict):
            raise ValueError(
                "OpenAI strict schema does not support map-shaped object "
                "properties; model this field with explicit Pydantic fields"
            )
        if additional not in (None, False):
            raise ValueError(
                f"OpenAI strict schema does not support additionalProperties={additional!r}"
            )
        node["additionalProperties"] = False
        if isinstance(properties, dict):
            node["required"] = list(properties.keys())
            for child in properties.values():
                _normalize_node(child)

    additional = node.get("additionalProperties")
    if isinstance(additional, dict):
        _normalize_node(additional)

    for key in ("$defs", "definitions"):
        definitions = node.get(key)
        if isinstance(definitions, dict):
            for child in definitions.values():
                _normalize_node(child)

    for key in ("items", "additionalItems", "contains"):
        if key in node:
            _normalize_node(node[key])

    for key in ("anyOf", "oneOf", "allOf", "prefixItems"):
        if key in node:
            _normalize_node(node[key])


def _reject_unsupported(node: dict[str, Any]) -> None:
    unsupported = sorted(key for key in _UNSUPPORTED_SCHEMA_KEYS if key in node)
    if unsupported:
        raise ValueError(
            "OpenAI strict schema does not support keys: "
            + ", ".join(unsupported)
        )
