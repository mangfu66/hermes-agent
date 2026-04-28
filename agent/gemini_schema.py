"""Helpers for translating OpenAI-style tool schemas to Gemini's schema subset."""

from __future__ import annotations

from typing import Any, Dict, List

# Gemini's ``FunctionDeclaration.parameters`` field accepts the ``Schema``
# object, which is only a subset of OpenAPI 3.0 / JSON Schema.  Strip fields
# outside that subset before sending Hermes tool schemas to Google.
_GEMINI_SCHEMA_ALLOWED_KEYS = {
    "type",
    "format",
    "title",
    "description",
    "nullable",
    "enum",
    "maxItems",
    "minItems",
    "properties",
    "required",
    "minProperties",
    "maxProperties",
    "minLength",
    "maxLength",
    "pattern",
    "example",
    "anyOf",
    "propertyOrdering",
    "default",
    "items",
    "minimum",
    "maximum",
}

# Anthropic-backed Claude routes behind Antigravity are stricter than Gemini's
# own function-declaration schema handling. In practice they reject several
# metadata-only fields and some permissive union/object patterns that Gemini
# accepts. Keep a second pass that trims the schema down to the subset we've
# verified works against the live Claude backend.
_CLAUDE_TOOL_SCHEMA_DROP_KEYS = {
    "default",
    "title",
    "example",
    "propertyOrdering",
    "format",
    "pattern",
    "description",
}


def sanitize_gemini_schema(schema: Any) -> Dict[str, Any]:
    """Return a Gemini-compatible copy of a tool parameter schema.

    Hermes tool schemas are OpenAI-flavored JSON Schema and may contain keys
    such as ``$schema`` or ``additionalProperties`` that Google's Gemini
    ``Schema`` object rejects.  This helper preserves the documented Gemini
    subset and recursively sanitizes nested ``properties`` / ``items`` /
    ``anyOf`` definitions.
    """

    if not isinstance(schema, dict):
        return {}

    cleaned: Dict[str, Any] = {}
    for key, value in schema.items():
        if key not in _GEMINI_SCHEMA_ALLOWED_KEYS:
            continue
        if key == "properties":
            if not isinstance(value, dict):
                continue
            props: Dict[str, Any] = {}
            for prop_name, prop_schema in value.items():
                if not isinstance(prop_name, str):
                    continue
                props[prop_name] = sanitize_gemini_schema(prop_schema)
            cleaned[key] = props
            continue
        if key == "items":
            cleaned[key] = sanitize_gemini_schema(value)
            continue
        if key == "anyOf":
            if not isinstance(value, list):
                continue
            cleaned[key] = [
                sanitize_gemini_schema(item)
                for item in value
                if isinstance(item, dict)
            ]
            continue
        cleaned[key] = value

    # Gemini's Schema validator requires every ``enum`` entry to be a string,
    # even when the parent ``type`` is ``integer`` / ``number`` / ``boolean``.
    # OpenAI / OpenRouter / Anthropic accept typed enums (e.g. Discord's
    # ``auto_archive_duration: {type: integer, enum: [60, 1440, 4320, 10080]}``),
    # so we only drop the ``enum`` when it would collide with Gemini's rule.
    # Keeping ``type: integer`` plus the human-readable description gives the
    # model enough guidance; the tool handler still validates the value.
    enum_val = cleaned.get("enum")
    type_val = cleaned.get("type")
    if isinstance(enum_val, list) and type_val in {"integer", "number", "boolean"}:
        if any(not isinstance(item, str) for item in enum_val):
            cleaned.pop("enum", None)

    return cleaned


def sanitize_gemini_tool_parameters(parameters: Any) -> Dict[str, Any]:
    """Normalize tool parameters to a valid Gemini object schema."""

    cleaned = sanitize_gemini_schema(parameters)
    if not cleaned:
        return {"type": "object", "properties": {}}
    return cleaned


def _sanitize_claude_tool_schema(schema: Any) -> Dict[str, Any]:
    """Trim a Gemini-sanitized schema down to a Claude-compatible subset."""
    if not isinstance(schema, dict):
        return {}

    cleaned: Dict[str, Any] = {}
    for key, value in schema.items():
        if key in _CLAUDE_TOOL_SCHEMA_DROP_KEYS:
            continue
        if key == "properties":
            if not isinstance(value, dict):
                continue
            props: Dict[str, Any] = {}
            for prop_name, prop_schema in value.items():
                if not isinstance(prop_name, str):
                    continue
                props[prop_name] = _sanitize_claude_tool_schema(prop_schema)
            cleaned[key] = props
            continue
        if key == "items":
            item_schema = _sanitize_claude_tool_schema(value)
            # Anthropic rejects completely empty array item schemas. This most
            # often happens when an OpenAI schema used ``$ref``/``$defs`` and
            # the generic Gemini sanitizer stripped those fields, leaving
            # ``items: {}``. Promote that case to an explicit empty object.
            if not item_schema:
                item_schema = {"type": "object", "properties": {}}
            cleaned[key] = item_schema
            continue
        if key == "anyOf":
            if not isinstance(value, list):
                continue
            options: List[Dict[str, Any]] = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                sanitized = _sanitize_claude_tool_schema(item)
                if sanitized == {"type": "null"}:
                    continue
                if sanitized == {"type": "object"} and len(value) > 1:
                    continue
                options.append(sanitized)
            if not options:
                continue
            if len(options) == 1:
                cleaned.update(options[0])
                continue
            option_types = {str(opt.get("type") or "").strip() for opt in options if isinstance(opt, dict)}
            option_types.discard("")
            # Anthropic's validator is much less tolerant of ``anyOf`` than the
            # Gemini path. Collapse common unions to a single broad type.
            if option_types and option_types.issubset({"integer", "number"}):
                cleaned["type"] = "number"
            elif "string" in option_types:
                cleaned["type"] = "string"
            elif "boolean" in option_types:
                cleaned["type"] = "boolean"
            elif "array" in option_types:
                cleaned["type"] = "array"
                exemplar = next((opt for opt in options if opt.get("type") == "array"), None)
                if isinstance(exemplar, dict) and isinstance(exemplar.get("items"), dict):
                    cleaned["items"] = exemplar["items"]
            elif "object" in option_types:
                exemplar = next((opt for opt in options if opt.get("type") == "object"), None)
                cleaned["type"] = "object"
                cleaned["properties"] = dict(exemplar.get("properties") or {}) if isinstance(exemplar, dict) else {}
            continue
        cleaned[key] = value
    return cleaned


def sanitize_claude_tool_parameters(parameters: Any) -> Dict[str, Any]:
    """Normalize tool parameters for Claude behind Antigravity.

    Start from the generic Gemini-safe schema, then drop extra metadata and
    simplify nullable/object unions that Anthropic's validator rejects in the
    Cloud Code Claude path.
    """
    cleaned = _sanitize_claude_tool_schema(sanitize_gemini_schema(parameters))
    if not cleaned:
        return {"type": "object", "properties": {}}
    return cleaned
