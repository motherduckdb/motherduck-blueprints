from __future__ import annotations

import pytest

from md_blueprints.schema import ValidationError
from md_blueprints.template import Template


def test_template_reports_unresolved_references() -> None:
    with pytest.raises(ValidationError, match=r"Unknown template reference \$\{var.missing\}"):
        Template.render("${var.missing}", {"var": {}})


def test_template_can_escape_literal_reference_syntax() -> None:
    rendered = Template.render(r"\${var.name} deploys ${var.name}", {"var": {"name": "analytics"}})

    assert rendered == "${var.name} deploys analytics"
