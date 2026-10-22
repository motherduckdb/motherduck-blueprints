from __future__ import annotations

import json
import re

from .schema import ValidationError, breaking_change


def as_text(value: object) -> str:
    """Render YAML booleans, nulls, and nested values as JSON text, never as Python reprs."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (bool, dict, list)):
        return json.dumps(value)
    return str(value)


class Template:
    _REFERENCE = re.compile(r"(?<!\\)\$\{([^}]+)\}")
    _UNTERMINATED = re.compile(r"(?<!\\)\$\{")

    @classmethod
    def render(cls, value: object, context: dict[str, object], *, unescape: bool = True) -> object:
        """Resolve ``${path}`` references. ``\\${`` stays literal.

        ``unescape=False`` keeps escaped references escaped so a value can be
        rendered again (for example variables that reference other variables).
        """
        if isinstance(value, str):
            rendered = cls._REFERENCE.sub(lambda match: as_text(cls.lookup(match.group(1), context)), value)
            if not unescape:
                return rendered
            if cls._UNTERMINATED.search(rendered):
                raise ValidationError(
                    f"Unterminated template reference in {value!r}: close it with }}, "
                    r"or write \${ for a literal ${." + breaking_change("unterminated-template-reference")
                )
            return rendered.replace(r"\${", "${")
        if isinstance(value, list):
            return [cls.render(item, context, unescape=unescape) for item in value]
        if isinstance(value, dict):
            return {
                str(cls.render(key, context, unescape=unescape)): cls.render(item, context, unescape=unescape)
                for key, item in value.items()
            }
        return value

    @staticmethod
    def lookup(path: str, context: dict[str, object]) -> object:
        node: object = context
        for segment in path.split("."):
            if isinstance(node, dict) and segment in node:
                node = node[segment]
            else:
                raise ValidationError(f"Unknown template reference ${{{path}}}")
        return node
