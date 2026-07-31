from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .deploy import Deployer, PlanFormatter
from .init import run_init
from .maintenance import run_check_updates, run_doctor
from .migrations import run_migrate
from .project import CommandError, Project
from .scaffold import run_new
from .schema import ValidationError


def parse_blueprints(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def add_root_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=os.getcwd())


def add_target_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target")
    parser.add_argument("--branch")
    parser.add_argument("--blueprints")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md-blueprints",
        description="Validate, preview, and deploy MotherDuck blueprint packages.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser("init", help="Initialize a customer blueprint repository.")
    init_parser.add_argument("directory", nargs="?", default=".")
    init_parser.add_argument("--force", action="store_true")

    new_parser = commands.add_parser("new", help="Scaffold a typed blueprint package.")
    new_parser.add_argument("kind", choices=["flight", "dive", "guide", "role", "project"])
    new_parser.add_argument("name")
    add_root_option(new_parser)
    new_parser.add_argument("--input", dest="input_ref")
    new_parser.add_argument("--url", dest="share_url")
    new_parser.add_argument("--alias")

    validate_parser = commands.add_parser("validate", help="Validate manifests without contacting MotherDuck.")
    add_root_option(validate_parser)
    validate_parser.add_argument("--target")

    render_parser = commands.add_parser("render", help="Render selected packages for a target.")
    add_root_option(render_parser)
    add_target_options(render_parser)

    dive_source_parser = commands.add_parser("dive-source", help="Print the source path for one Dive.")
    add_root_option(dive_source_parser)
    dive_source_parser.add_argument("--blueprints", required=True)
    dive_source_parser.add_argument("--dive")

    changed_parser = commands.add_parser("changed", help="List packages changed between Git revisions.")
    add_root_option(changed_parser)
    changed_parser.add_argument("--base")
    changed_parser.add_argument("--head")
    changed_parser.add_argument("--all", action="store_true", dest="all_blueprints")
    changed_parser.add_argument("--json", action="store_true")

    plan_parser = commands.add_parser("plan", help="Inspect live changes without applying them.")
    add_root_option(plan_parser)
    add_target_options(plan_parser)
    plan_parser.add_argument("--json", action="store_true")

    deploy_parser = commands.add_parser("deploy", help="Apply selected packages to MotherDuck.")
    add_root_option(deploy_parser)
    add_target_options(deploy_parser)

    cleanup_parser = commands.add_parser("cleanup", help="Remove branch-scoped preview resources.")
    add_root_option(cleanup_parser)
    add_target_options(cleanup_parser)
    cleanup_parser.add_argument("--dry-run", action="store_true")
    cleanup_parser.add_argument("--json", action="store_true")

    doctor_parser = commands.add_parser("doctor", help="Check CLI, schema, and upgrade status.")
    add_root_option(doctor_parser)
    doctor_parser.add_argument("--format", choices=["text", "github-summary"], default="text")
    doctor_parser.add_argument("--check-updates", action="store_true")
    doctor_parser.add_argument("--offline", action="store_true")

    updates_parser = commands.add_parser("check-updates", help="Check for a newer CLI release.")
    updates_parser.add_argument("--format", choices=["text", "github-summary"], default="text")
    updates_parser.add_argument("--offline", action="store_true")

    migrate_parser = commands.add_parser("migrate", help="Inspect or apply manifest schema migrations.")
    add_root_option(migrate_parser)
    migrate_parser.add_argument("--from", dest="from_version", type=int)
    migrate_parser.add_argument("--to", dest="to_version", default="latest")
    migrate_parser.add_argument("--write", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        options = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1

    try:
        command = str(options.command)
        if command == "init":
            run_init(Path(options.directory), force=options.force)
        elif command == "new":
            run_new(
                Path(options.root),
                options.kind,
                options.name,
                input_ref=options.input_ref,
                share_url=options.share_url,
                alias=options.alias,
            )
        elif command == "doctor":
            run_doctor(
                Path(options.root),
                output_format=options.format,
                check_updates=options.check_updates,
                offline=options.offline,
            )
        elif command == "check-updates":
            run_check_updates(offline=options.offline, output_format=options.format)
        elif command == "migrate":
            run_migrate(
                Path(options.root),
                from_version=options.from_version,
                to_version=options.to_version,
                write=options.write,
            )
        else:
            root = Path(options.root)
            names = parse_blueprints(getattr(options, "blueprints", None))
            project = Project(root)
            if command == "validate":
                targets = [options.target] if options.target else ["preview", "prod"]
                project.validate(targets=targets)
                print(f"Validation passed for {len(project.all_blueprint_names())} blueprint(s).")
            elif command == "render":
                target = options.target or "prod"
                project.validate(targets=[target], branch=options.branch)
                expanded_names = project.deployment_blueprint_names(target, names)
                rendered = project.render_all(target, branch=options.branch, names=expanded_names)
                print(json.dumps([blueprint.to_dict() for blueprint in rendered], indent=2))
            elif command == "dive-source":
                if not names or len(names) != 1:
                    raise ValidationError("dive-source requires exactly one --blueprints NAME")
                project.validate(targets=["prod"])
                rendered = project.render_all("prod", names=names)
                dives = rendered[0].dives
                if options.dive:
                    if options.dive not in dives:
                        raise ValidationError(f"Unknown Dive {options.dive!r} in blueprint {names[0]!r}")
                    selected_dive = dives[options.dive]
                elif len(dives) == 1:
                    selected_dive = next(iter(dives.values()))
                elif not dives:
                    raise ValidationError(f"Blueprint {names[0]!r} does not declare a Dive")
                else:
                    raise ValidationError(
                        f"Blueprint {names[0]!r} declares multiple Dives; select one with --dive RESOURCE_KEY"
                    )
                print(Path(str(selected_dive["sourcePath"])).relative_to(project.root))
            elif command == "changed":
                changed = (
                    project.all_blueprint_names()
                    if options.all_blueprints
                    else project.changed_blueprints(base=options.base, head=options.head or "HEAD")
                )
                print(json.dumps(changed) if options.json else "\n".join(changed))
            elif command == "plan":
                deployer = Deployer(project)
                records = deployer.plan(target=options.target or "prod", branch=options.branch, names=names)
                print(
                    json.dumps([record.to_dict() for record in records], indent=2)
                    if options.json
                    else PlanFormatter.format(records, title="Deployment Plan")
                )
                deployer.ensure_plan_succeeds(records)
            elif command == "deploy":
                Deployer(project).deploy(target=options.target or "prod", branch=options.branch, names=names)
            elif command == "cleanup":
                deployer = Deployer(project)
                if options.dry_run:
                    records = deployer.cleanup_plan(target=options.target or "preview", branch=options.branch, names=names)
                    print(
                        json.dumps([record.to_dict() for record in records], indent=2)
                        if options.json
                        else PlanFormatter.format(records, title="Cleanup Plan")
                    )
                    deployer.ensure_plan_succeeds(records)
                else:
                    deployer.cleanup(target=options.target or "preview", branch=options.branch, names=names)
        return 0
    except (ValidationError, CommandError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
