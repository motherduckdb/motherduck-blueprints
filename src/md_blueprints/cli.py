from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .deploy import Deployer, PlanFormatter
from .diagnostics import report_error
from .init import run_init
from .importer import run_import
from .maintenance import run_check_updates, run_doctor
from .migrations import run_migrate
from .project import CommandError, Project
from .scaffold import run_new
from .schema import ValidationError
from .upgrade import run_upgrade
from .motherduck_cli import install_cli


def parse_blueprints(value: str | None) -> list[str] | None:
    if value is None:
        return None
    names = [item.strip() for item in value.split(",") if item.strip()]
    if not names:
        raise ValidationError("--blueprints must contain at least one blueprint name; omit it to select all")
    return names


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
    parser.add_argument("--input", dest="input_ref")
    parser.add_argument("--url", dest="share_url")
    parser.add_argument("--alias")
    parser.add_argument("--dive")
    parser.add_argument("--resource", action="append", default=[])
    parser.add_argument("--snapshot")
    parser.add_argument("--verify", dest="verify", action="store_true", default=True)
    parser.add_argument("--skip-verification", dest="verify", action="store_false")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="md-blueprints",
        usage=(
            "md-blueprints <init|install-cli|new|import|validate|verify|render|dive-source|changed|plan|deploy|cleanup|doctor|"
            "check-updates|upgrade|migrate> [options]"
        ),
    )
    parser.add_argument("command", nargs="?")
    parser.add_argument("init_dir", nargs="?")
    parser.add_argument("new_name", nargs="?")
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
        elif command == "install-cli":
            install_cli()
        elif command == "new":
            if not options.init_dir or not options.new_name:
                raise ValidationError("Usage: md-blueprints new <flight|dive|guide|role|project> NAME [options]")
            run_new(
                root,
                options.init_dir,
                options.new_name,
                input_ref=options.input_ref,
                share_url=options.share_url,
                alias=options.alias,
            )
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
        elif command == "upgrade":
            run_upgrade(root, to_version=options.to_version, write=options.write and not options.dry_run)
        elif command == "import":
            if options.blueprints is not None:
                raise ValidationError("Import selects remote UUIDs: use --resource KIND:UUID, not --blueprints")
            report = run_import(
                Project(root), target=options.target or "prod", selectors=options.resource,
                all_resources=options.all_blueprints, write=options.write and not options.dry_run,
                snapshot_path=Path(options.snapshot) if options.snapshot else None,
            )
            print(json.dumps(report, indent=2))
        else:
            project = Project(root)
            if command == "validate":
                targets = [options.target] if options.target else project.target_names()
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
                Deployer(project).deploy(
                    target=options.target or "prod", branch=options.branch, names=names, verify=options.verify,
                )
            elif command == "verify":
                records = Deployer(project).verify(target=options.target or "prod", branch=options.branch, names=names)
                print(
                    json.dumps([record.to_dict() for record in records], indent=2)
                    if options.json else PlanFormatter.format(records, title="Live Verification")
                )
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
    except (ValidationError, CommandError, KeyError, ValueError, OSError) as exc:
        report_error(exc)
        return 1
