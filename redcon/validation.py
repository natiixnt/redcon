"""
Validate redcon output artifacts against versioned JSON Schemas.

redcon ships draft 2020-12 schemas for its three JSON artifacts - the
``pack`` run report, the ``diff`` report and the ``benchmark`` report -
under ``redcon/schemas/json/v1``. The artifact type is read from the
``command`` field, the only discriminator the artifacts carry.

The core stays dependency-free, so validation runs on a small built-in
checker that covers exactly the JSON Schema keywords these schemas use.
When ``jsonschema`` is installed it is used instead, for full-spec
coverage. Either way the schemas are plain standard files that any
external validator can consume.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

SCHEMA_VERSION = "v1"

# Maps the artifact's ``command`` field to a schema name (and file stem).
_COMMAND_TO_TYPE: dict[str, str] = {
    "pack": "run",
    "diff": "diff",
    "benchmark": "benchmark",
}

ARTIFACT_TYPES = tuple(sorted(set(_COMMAND_TO_TYPE.values())))


@dataclass(frozen=True)
class ValidationError:
    """A single schema violation, addressed by a JSON path like ``$.budget``."""

    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


@cache
def _load_schema(artifact_type: str) -> dict[str, Any]:
    """Load a packaged schema by type, cached for the process lifetime."""
    filename = f"{artifact_type}.schema.json"
    resource = resources.files("redcon.schemas").joinpath("json", SCHEMA_VERSION, filename)
    return json.loads(resource.read_text(encoding="utf-8"))


def schema_for(artifact_type: str) -> dict[str, Any]:
    """Return the JSON Schema dict for a known artifact type."""
    if artifact_type not in ARTIFACT_TYPES:
        raise ValueError(f"unknown artifact type: {artifact_type!r}")
    return _load_schema(artifact_type)


def detect_artifact_type(data: Any) -> str | None:
    """Infer the artifact type from the ``command`` field, or None."""
    if not isinstance(data, dict):
        return None
    return _COMMAND_TO_TYPE.get(data.get("command"))


def validate_artifact(data: Any, artifact_type: str | None = None) -> list[ValidationError]:
    """Validate a parsed artifact against its schema.

    ``artifact_type`` overrides discriminator-based detection. Returns the
    list of violations; an empty list means the artifact is valid.
    """
    if artifact_type is None:
        artifact_type = detect_artifact_type(data)
        if artifact_type is None:
            return [
                ValidationError(
                    "$",
                    "cannot determine artifact type: expected a 'command' field of "
                    + ", ".join(repr(c) for c in sorted(_COMMAND_TO_TYPE)),
                )
            ]
    schema = schema_for(artifact_type)
    return _validate(data, schema)


def _validate(data: Any, schema: dict[str, Any]) -> list[ValidationError]:
    """Dispatch to jsonschema when available, else the built-in checker."""
    try:
        import jsonschema  # noqa: PLC0415
    except ImportError:
        errors: list[ValidationError] = []
        _check(data, schema, "$", errors)
        return errors
    validator = jsonschema.Draft202012Validator(schema)
    return [
        ValidationError(_jsonschema_path(err), err.message)
        for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    ]


def _jsonschema_path(err: Any) -> str:
    parts = ["$"]
    for token in err.absolute_path:
        if isinstance(token, int):
            parts.append(f"[{token}]")
        else:
            parts.append(f".{token}")
    return "".join(parts)


# --- Built-in checker (zero-dependency subset of draft 2020-12) -----------
#
# Supports only the keywords the packaged schemas use: type, const, enum,
# required, properties, additionalProperties, items, minimum, maximum.

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
}


def _matches_type(value: Any, type_spec: Any) -> bool:
    types = type_spec if isinstance(type_spec, list) else [type_spec]
    return any(_TYPE_CHECKS.get(t, lambda _v: True)(value) for t in types)


def _child_path(path: str, key: Any) -> str:
    return f"{path}[{key}]" if isinstance(key, int) else f"{path}.{key}"


def _check(value: Any, schema: dict[str, Any], path: str, errors: list[ValidationError]) -> None:
    if "const" in schema and value != schema["const"]:
        errors.append(ValidationError(path, f"expected constant {schema['const']!r}"))
    if "enum" in schema and value not in schema["enum"]:
        errors.append(ValidationError(path, f"value not in {schema['enum']!r}"))

    if "type" in schema and not _matches_type(value, schema["type"]):
        errors.append(ValidationError(path, f"expected type {schema['type']!r}"))
        # A type mismatch makes nested object/array checks meaningless.
        return

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(ValidationError(path, f"must be >= {schema['minimum']}"))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(ValidationError(path, f"must be <= {schema['maximum']}"))

    if isinstance(value, dict):
        _check_object(value, schema, path, errors)
    elif isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _check(item, schema["items"], _child_path(path, i), errors)


def _check_object(
    value: dict[str, Any], schema: dict[str, Any], path: str, errors: list[ValidationError]
) -> None:
    for key in schema.get("required", []):
        if key not in value:
            errors.append(ValidationError(path, f"missing required property {key!r}"))

    properties = schema.get("properties", {})
    for key, sub_value in value.items():
        if key in properties:
            _check(sub_value, properties[key], _child_path(path, key), errors)
            continue
        additional = schema.get("additionalProperties", True)
        if additional is False:
            errors.append(
                ValidationError(_child_path(path, key), "additional property not allowed")
            )
        elif isinstance(additional, dict):
            _check(sub_value, additional, _child_path(path, key), errors)
