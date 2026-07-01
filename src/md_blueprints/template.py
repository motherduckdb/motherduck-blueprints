from __future__ import annotations

import re

from .schema import ValidationError


class Template:
    _REFERENCE = re.compile(r"(?<!\\)\$\{([^}]+)\}")

    @classmethod
    def render(cls, value: object, context: dict[str, object]) -> object:
        if isinstance(value, str):
            rendered = cls._REFERENCE.sub(lambda match: str(cls.lookup(match.group(1), context)), value)
            return rendered.replace(r"\${", "${")
        if isinstance(value, list):
            return [cls.render(item, context) for item in value]
        if isinstance(value, dict):
            return {str(cls.render(key, context)): cls.render(item, context) for key, item in value.items()}
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
