from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .deploy import Deployer, PlanFormatter
from .init import run_init
from .maintenance import run_check_updates, run_doctor
from .migrations import run_migrate
from .project import CommandError, Project
from .schema import ValidationError


def parse_blueprints(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--target")
    parser.add_argument("--branch")
    parser.add_argument("--blueprints")
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--all", action="store_true", dest="all_blueprints")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from", dest="from_version", type=int)
    parser.add_argument("--to", dest="to_version", default="latest")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--format", choices=["text", "github-summary"], default="text")
    parser.add_argument("--check-updates", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--version", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="md-blueprints",
        usage="md-blueprints <init|validate|render|changed|plan|deploy|cleanup|doctor|check-updates|migrate> [options]",
    )
    parser.add_argument("command", nargs="?")
    parser.add_argument("init_dir", nargs="?")
    add_common_options(parser)
    options = parser.parse_args(argv)

    if options.version:
        from . import __version__

        print(__version__)
        return 0

    command = options.command
    if not command:
        parser.print_usage(sys.stderr)
        return 2

    try:
        root = Path(options.root)
        names = parse_blueprints(options.blueprints)
        if command == "init":
            run_init(Path(options.init_dir or "."), force=options.force)
        elif command == "doctor":
            run_doctor(
                root,
                output_format=options.format,
                check_updates=options.check_updates,
                offline=options.offline,
            )
        elif command == "check-updates":
            run_check_updates(offline=options.offline, output_format=options.format)
        elif command == "migrate":
            run_migrate(root, from_version=options.from_version, to_version=options.to_version, write=options.write)
        else:
            project = Project(root)
            if command == "validate":
                targets = [options.target] if options.target else ["preview", "prod"]
                project.validate(targets=targets)
                print(f"Validation passed for {len(project.all_blueprint_names())} blueprint(s).")
            elif command == "render":
                target = options.target or "prod"
                rendered = project.render_all(target, branch=options.branch, names=names)
                print(json.dumps([blueprint.to_dict() for blueprint in rendered], indent=2))
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
            else:
                parser.print_usage(sys.stderr)
                return 2
        return 0
    except (ValidationError, CommandError, KeyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
