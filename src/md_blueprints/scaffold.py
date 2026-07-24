from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path

from .schema import ValidationError


SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
KINDS = {"flight": "flights", "dive": "dives", "guide": "guides", "role": "roles", "project": "projects"}


def _title(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


def _render(text: str, *, name: str, alias: str, required_database: str | None = None) -> str:
    rendered = text.replace("__BLUEPRINT_NAME__", name).replace("__DATABASE_NAME__", alias)
    if required_database is not None:
        rendered = rendered.replace("__REQUIRED_DATABASE__", required_database)
    return rendered


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _starter_source(name: str) -> str:
    return resources.files("md_blueprints").joinpath("template_repo", "templates", "blueprint", name).read_text(
        encoding="utf-8"
    )


def run_new(
    root: Path,
    kind: str,
    name: str,
    *,
    input_ref: str | None = None,
    share_url: str | None = None,
    alias: str | None = None,
) -> Path:
    root = root.expanduser().resolve()
    if kind not in KINDS:
        raise ValidationError(f"Unknown blueprint kind {kind!r}; choose flight, dive, guide, role, or project")
    if not SLUG.fullmatch(name):
        raise ValidationError("Blueprint name must be a lowercase slug using a-z, 0-9, and hyphens")
    if not (root / "motherduck.yml").is_file():
        raise ValidationError(f"motherduck.yml not found in {root}")

    destination = root / KINDS[kind] / name
    if destination.exists():
        raise ValidationError(f"Blueprint already exists: {destination.relative_to(root)}")

    resource_alias = alias or name.replace("-", "_")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", resource_alias):
        raise ValidationError("Alias must be a SQL identifier using letters, numbers, and underscores")

    if kind == "dive":
        if bool(input_ref) == bool(share_url):
            raise ValidationError("new dive requires exactly one of --input BLUEPRINT.OUTPUT or --url SHARE_URL")
        required_database = _required_database(
            root,
            resource_alias,
            input_ref=input_ref,
            share_url=share_url,
        )
        manifest = _dive_manifest(name, resource_alias, input_ref=input_ref, share_url=share_url)
        _write(destination / "blueprint.yml", manifest)
        _write(
            destination / "src/dive.tsx",
            _render(
                _starter_source("standalone-dive.tsx"),
                name=name,
                alias=resource_alias,
                required_database=json.dumps(required_database),
            ),
        )
    elif kind == "flight":
        _write(destination / "blueprint.yml", _flight_manifest(name, resource_alias))
        _write(destination / "src/flight.py", _render(_starter_source("flight.py"), name=name, alias=resource_alias))
        _write(destination / "src/requirements.txt", _starter_source("requirements.txt"))
    elif kind == "guide":
        _write(destination / "blueprint.yml", _guide_manifest(name))
        _write(destination / "guide.md", f"# {_title(name)}\n\nAdd trusted context for agents here.\n")
    elif kind == "role":
        _write(destination / "blueprint.yml", _role_manifest(name))
    else:
        _write(destination / "blueprint.yml", _project_manifest(name, resource_alias))
        _write(destination / "src/flight.py", _render(_starter_source("flight.py"), name=name, alias=resource_alias))
        _write(destination / "src/requirements.txt", _starter_source("requirements.txt"))
        _write(destination / "src/dive.tsx", _render(_starter_source("dive.tsx"), name=name, alias=resource_alias))

    _write(
        destination / "README.md",
        f"# {_title(name)}\n\nGenerated `{kind}` blueprint. Run `make validate` before opening a PR.\n",
    )
    print(f"Created {destination.relative_to(root)}")
    return destination


def _share_and_flight(name: str, alias: str) -> str:
    return f"""variables:
  database:
    default: {alias}
  share:
    default: {alias}
  schema:
    default: main

resources:
  shares:
    data:
      name: ${{var.share}}
      database: ${{var.database}}
      access: ORGANIZATION
      visibility: DISCOVERABLE
      cleanup: true
      dropDatabase: false
      targets:
        preview:
          name: ${{var.share}}${{var.preview_suffix}}
          database: ${{var.database}}${{var.preview_suffix}}
          access: RESTRICTED
          visibility: HIDDEN
          dropDatabase: true
  flights:
    loader:
      name: {name}
      source: src/flight.py
      requirements: src/requirements.txt
      scheduleCron: ""
      runOnDeploy: true
      waitForRun: success
      config:
        database: ${{resources.shares.data.database}}
        schema: ${{var.schema}}
        share: ${{resources.shares.data.name}}
        share_access: ${{resources.shares.data.access}}
        share_visibility: ${{resources.shares.data.visibility}}
      targets:
        preview:
          name: {name}:${{target.branch}} (Preview)
"""


def _flight_manifest(name: str, alias: str) -> str:
    return f"""schemaVersion: 1
name: {name}
title: {_title(name)}
description: Flight package that publishes a share for downstream blueprints.

outputs:
  data:
    share: data

{_share_and_flight(name, alias)}"""


def _dive_manifest(name: str, alias: str, *, input_ref: str | None, share_url: str | None) -> str:
    if input_ref:
        producer, output = _parse_input_ref(input_ref)
        contract = f"""inputs:
  data:
    blueprint: {producer}
    output: {json.dumps(output)}

"""
        required = "input: data"
    else:
        assert share_url is not None
        if not share_url.strip():
            raise ValidationError("--url must not be empty")
        contract = ""
        required = f"url: {json.dumps(share_url)}"
    return f"""schemaVersion: 1
name: {name}
title: {_title(name)}
description: Dive package backed by a declared data input.

{contract}resources:
  dives:
    dashboard:
      title: {_title(name)}
      source: src/dive.tsx
      requiredResources:
        - {required}
          alias: {alias}
      targets:
        preview:
          title: {_title(name)}:${{target.branch}} (Preview)
"""


def _parse_input_ref(input_ref: str) -> tuple[str, str]:
    producer, separator, output = input_ref.partition(".")
    if not separator or not SLUG.fullmatch(producer) or not output:
        raise ValidationError("--input must use BLUEPRINT.OUTPUT with a lowercase blueprint slug")
    return producer, output


def _required_database(
    root: Path,
    alias: str,
    *,
    input_ref: str | None,
    share_url: str | None,
) -> dict[str, str]:
    if share_url is not None:
        path = share_url.strip()
        if not path:
            raise ValidationError("--url must not be empty")
        return {"type": "share", "path": path, "alias": alias}

    assert input_ref is not None
    producer, output = _parse_input_ref(input_ref)

    from .project import Project

    project = Project(root)
    if producer not in project.all_blueprint_names():
        raise ValidationError(f"--input references missing blueprint {producer!r}")
    rendered_producer = project.render_all("prod", names=[producer])[0]
    rendered_output = rendered_producer.outputs.get(output)
    if rendered_output is None:
        raise ValidationError(f"--input references missing output {producer}.{output}")
    return {"type": "share", "shareName": str(rendered_output["name"]), "alias": alias}


def _guide_manifest(name: str) -> str:
    return f"""schemaVersion: 1
name: {name}
title: {_title(name)}
description: Version-controlled Guide for agents and collaborators.

resources:
  guides:
    guide:
      title: {_title(name)}
      topic: {name}
      source: guide.md
      deploy: false
"""


def _role_manifest(name: str) -> str:
    return f"""schemaVersion: 1
name: {name}
title: {_title(name)}
description: Version-controlled MotherDuck role and membership assignments.

resources:
  roles:
    role:
      name: {name}
      includedRoles: []
      members: []
      mode: additive
      deploy: true
"""


def _project_manifest(name: str, alias: str) -> str:
    base = _flight_manifest(name, alias)
    return base + f"""
  dives:
    dashboard:
      title: {_title(name)}
      source: src/dive.tsx
      requiredResources:
        - share: data
          alias: {alias}
      targets:
        preview:
          title: {_title(name)}:${{target.branch}} (Preview)
"""
