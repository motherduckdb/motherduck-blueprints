from __future__ import annotations


from md_blueprints.template import Template


def test_template_can_escape_literal_reference_syntax() -> None:
    rendered = Template.render(r"\${var.name} deploys ${var.name}", {"var": {"name": "analytics"}})

    assert rendered == "${var.name} deploys analytics"


