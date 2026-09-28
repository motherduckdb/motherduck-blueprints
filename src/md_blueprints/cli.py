from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

from .deploy import Deployer, PlanFormatter
from .diagnostics import report_error, validation_warnings
from .init import run_init
from .guides import run_guides
from .importer import run_import
from .maintenance import run_check_updates, run_doctor
from .migrations import run_migrate
from .project import CommandError, Project
from .scaffold import run_new
from .schema import ValidationError
from .upgrade import run_upgrade
from .motherduck_cli import install_cli


COMMANDS: dict[str, str] = {
    "init": "Create a new Blueprints repository from the packaged template",
    "guides": "Print read-only context and a task brief for an agent that writes Guides",
    "install-cli": "Install the MotherDuck CLI version tested with this release",
    "new": "Scaffold a Flight, Dive, Guide, role, or project package",
    "import": "Discover existing Flights, Dives, and Guides (writes only with --write)",
    "validate": "Validate all packages without contacting MotherDuck",
    "verify": "Check live resources against the rendered manifests (read-only)",
    "render": "Print rendered package manifests as JSON",
    "dive-source": "Print the source path of a package's Dive",
    "changed": "List packages changed between two Git revisions",
    "plan": "Preview deployment changes without writing",
    "deploy": "Deploy selected packages to a target",
    "cleanup": "Remove preview resources for a branch",
    "doctor": "Check CLI, schema, workflow, and pin health",
    "check-updates": "Compare the installed CLI with the latest release",
    "upgrade": "Update the Makefile CLI pin and workflow action pins together",
    "migrate": "Preview or write schemaVersion migrations",
}

# Specific guidance for flags that users commonly pass to the wrong command.
FLAG_HINTS: dict[tuple[str, str], str] = {
    ("deploy", "--dry-run"): "use `plan` to preview changes",
    ("deploy", "--json"): "use `plan --json` for machine-readable output",
    ("new", "--dry-run"): "new always writes the scaffold; review it with git status and delete it to undo",
    ("init", "--write"): "init always writes; generate into an empty directory to review the result",
    ("init", "--json"): "init prints a plain-text summary",
    ("init", "--root"): "pass the directory as an argument: md-blueprints init DIR",
    ("import", "--blueprints"): "import selects remote UUIDs: use --resource KIND:UUID",
    ("import", "--json"): "import always prints JSON",
    ("validate", "--dry-run"): "validate never writes or contacts MotherDuck",
    ("render", "--dry-run"): "render never writes or contacts MotherDuck",
    ("plan", "--dry-run"): "plan never writes",
    ("verify", "--dry-run"): "verify never writes",
}


class UsageError(Exception):
    """A command line that does not match a command's supported arguments."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(f"{self.prog}: {message}")


def parse_blueprints(value: str | None) -> list[str] | None:
    if value is None:
        return None
    names = [item.strip() for item in value.split(",") if item.strip()]
    if not names:
        raise ValidationError("--blueprints must contain at least one blueprint name; omit it to select all")
    return names


def require_known_blueprints(project: Project, names: list[str] | None) -> None:
    if not names:
        return
    known = project.all_blueprint_names()
    missing = [name for name in names if name not in known]
    if missing:
        valid = ", ".join(sorted(known)) or "none discovered"
        raise ValidationError(f"Unknown blueprint(s): {', '.join(missing)}. Valid names: {valid}")


def _root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=os.getcwd(), help="Repository directory containing motherduck.yml (default: current directory)")


def _target(parser: argparse.ArgumentParser, default: str) -> None:
    parser.add_argument("--target", help=f"Target from motherduck.yml (default: {default})")


def _branch(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--branch", help="Branch name used to scope preview resources")


def _blueprints(parser: argparse.ArgumentParser, text: str = "Comma-separated package names (default: all)") -> None:
    parser.add_argument("--blueprints", help=text)


def _json(parser: argparse.ArgumentParser, text: str = "Print JSON instead of text") -> None:
    parser.add_argument("--json", action="store_true", help=text)


def _format(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=["text", "github-summary"], default="text", help="Output format (default: text)")


def build_parser() -> _Parser:
    parser = _Parser(
        prog="md-blueprints",
        description="Validate, preview, and deploy MotherDuck Blueprints.",
        epilog="Run md-blueprints <command> --help for the options of a command.",
    )
    parser.add_argument("--version", action="store_true", help="Print the md-blueprints version and exit")
    commands = parser.add_subparsers(dest="command", metavar="<command>", parser_class=_Parser)

    def command(name: str) -> _Parser:
        sub: _Parser = commands.add_parser(name, help=COMMANDS[name], description=COMMANDS[name] + ".")
        return sub

    sub = command("init")
    sub.add_argument("directory", nargs="?", default=".", help="Directory to initialize (default: current directory)")
    sub.add_argument(
        "--force", action="store_true",
        help="Allow a non-empty directory. Only missing files are written; existing files are never overwritten",
    )

    sub = command("guides")
    sub.add_argument("action", nargs="?", default="context", help="context (default), init, or update")
    _root(sub)
    sub.add_argument("--dbt", metavar="PATH", help="Include YAML documentation from a dbt project in Guide discovery")
    sub.add_argument("--dry-run", action="store_true", help="Accepted for compatibility; guides never writes files")

    sub = command("install-cli")
    sub.add_argument("--root", help=argparse.SUPPRESS)

    sub = command("new")
    sub.add_argument("kind", nargs="?", help="flight, dive, guide, role, or project")
    sub.add_argument("name", nargs="?", help="Lowercase package slug, for example events-ingest")
    _root(sub)
    sub.add_argument("--input", dest="input_ref", metavar="BLUEPRINT.OUTPUT", help="new dive: read a producer output from this repository")
    sub.add_argument("--url", dest="share_url", metavar="SHARE_URL", help="new dive: read an existing share by URL")
    sub.add_argument("--alias", help="Database alias used by the Flight, share, or Dive (default: name with underscores)")

    sub = command("import")
    _root(sub)
    _target(sub, "prod")
    sub.add_argument("--resource", action="append", default=[], metavar="KIND:UUID", help="Select one resource; repeat for more")
    sub.add_argument("--all", action="store_true", dest="all_blueprints", help="Select every visible Flight, Dive, and Guide")
    sub.add_argument("--write", action="store_true", help="Write disabled packages (default: report only)")
    sub.add_argument("--dry-run", action="store_true", help="Report only, even when --write is passed")
    sub.add_argument("--snapshot", metavar="PATH", help="Read resources from a local JSON snapshot instead of MotherDuck")

    sub = command("validate")
    _root(sub)
    _target(sub, "every target")
    _branch(sub)
    _blueprints(sub, "Comma-separated package names that must exist; validation always covers the whole repository")

    sub = command("verify")
    _root(sub)
    _target(sub, "prod")
    _branch(sub)
    _blueprints(sub)
    _json(sub)

    sub = command("render")
    _root(sub)
    _target(sub, "prod")
    _branch(sub)
    _blueprints(sub)

    sub = command("dive-source")
    _root(sub)
    _blueprints(sub, "Exactly one package name")
    sub.add_argument("--dive", metavar="RESOURCE_KEY", help="Dive resource key when the package declares several")

    sub = command("changed")
    _root(sub)
    sub.add_argument("--base", help="Base Git revision (default: select all packages)")
    sub.add_argument("--head", help="Head Git revision (default: HEAD)")
    sub.add_argument("--all", action="store_true", dest="all_blueprints", help="Select every package")
    _json(sub, "Print a JSON array")

    sub = command("plan")
    _root(sub)
    _target(sub, "prod")
    _branch(sub)
    _blueprints(sub)
    _json(sub)

    sub = command("deploy")
    _root(sub)
    _target(sub, "prod")
    _branch(sub)
    _blueprints(sub)
    sub.add_argument("--verify", dest="verify", action="store_true", default=True, help="Verify live resources after deploying (default)")
    sub.add_argument("--skip-verification", dest="verify", action="store_false", help="Skip post-deploy verification; preflight still runs")

    sub = command("cleanup")
    _root(sub)
    _target(sub, "preview")
    _branch(sub)
    _blueprints(sub)
    sub.add_argument("--dry-run", action="store_true", help="Print the cleanup plan without removing anything")
    _json(sub, "With --dry-run, print the cleanup plan as JSON")

    sub = command("doctor")
    _root(sub)
    _format(sub)
    sub.add_argument("--check-updates", action="store_true", help="Fail when a newer release or pin drift is found")
    sub.add_argument("--offline", action="store_true", help="Never contact GitHub for the latest release")

    sub = command("check-updates")
    sub.add_argument("--root", help=argparse.SUPPRESS)
    _format(sub)
    sub.add_argument("--offline", action="store_true", help="Never contact GitHub for the latest release")

    sub = command("upgrade")
    _root(sub)
    sub.add_argument("--to", dest="to_version", default="latest", metavar="X.Y.Z", help="Release to pin (default: latest)")
    sub.add_argument("--write", action="store_true", help="Write the pins (default: print the diff only)")
    sub.add_argument("--dry-run", action="store_true", help="Print the diff only, even when --write is passed")
    sub.add_argument("--offline", action="store_true", help="Never contact GitHub; requires --to X.Y.Z")

    sub = command("migrate")
    _root(sub)
    sub.add_argument("--from", dest="from_version", type=int, metavar="N", help="Expected current schemaVersion")
    sub.add_argument("--to", dest="to_version", default="latest", metavar="N", help="Target schemaVersion (default: latest)")
    sub.add_argument("--write", action="store_true", help="Write the migration (default: print the diff only)")
    sub.add_argument("--dry-run", action="store_true", help="Print the diff only, even when --write is passed")
    return parser


def _hoist_command(argv: list[str]) -> list[str]:
    """Keep the historical `md-blueprints --root DIR validate` form working."""
    if not argv or not argv[0].startswith("-") or argv[0] in {"--version", "-h", "--help"}:
        return argv
    for index, token in enumerate(argv):
        if token in COMMANDS:
            return [token, *argv[:index], *argv[index + 1:]]
    return argv


def _unsupported(command: str, extras: list[str]) -> UsageError:
    token = extras[0]
    if not token.startswith("-"):
        return UsageError(
            f"unexpected argument {token!r} for {command}. Run md-blueprints {command} --help for usage."
        )
    flag = token.split("=", 1)[0]
    hint = FLAG_HINTS.get((command, flag))
    if hint is None and flag == "--dbt":
        hint = "--dbt is only supported by guides"
    message = f"{command} does not support {flag}"
    return UsageError(
        f"{message}; {hint}" if hint else f"{message}. Run md-blueprints {command} --help for supported options."
    )


def main(argv: list[str] | None = None) -> int:
    args = _hoist_command(list(sys.argv[1:] if argv is None else argv))
    parser = build_parser()
    if args and not args[0].startswith("-") and args[0] not in COMMANDS:
        print(
            f"Error: unknown command {args[0]!r}. Choose one of: {', '.join(COMMANDS)}.\n"
            "Run md-blueprints --help for details.",
            file=sys.stderr,
        )
        return 2
    try:
        options, extras = parser.parse_known_args(args)
        if extras and options.command:
            raise _unsupported(options.command, extras)
        if extras:
            raise UsageError(f"unrecognized arguments: {' '.join(extras)}")
    except UsageError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except SystemExit as exc:  # --help
        return exc.code if isinstance(exc.code, int) else 0

    if options.version:
        from . import __version__

        print(__version__)
        return 0

    command = options.command
    if not command:
        parser.print_usage(sys.stderr)
        return 2

    try:
        handler = HANDLERS[command]
        handler(options)
        return 0
    except UsageError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyError as exc:
        key = exc.args[0] if exc.args else "unknown"
        report_error(ValidationError(
            f"Missing required value {key!r}. A manifest, target, or rendered resource does not declare it. "
            "Run md-blueprints validate for details; if validation passes, report this as a Blueprints bug."
        ))
        return 1
    except (ValidationError, CommandError, ValueError, OSError) as exc:
        report_error(exc)
        return 1


def _init(options: argparse.Namespace) -> None:
    run_init(Path(options.directory), force=options.force)


def _guides(options: argparse.Namespace) -> None:
    if options.dbt is not None and not options.dbt.strip():
        raise ValidationError("--dbt must name a dbt project directory or dbt_project.yml")
    run_guides(
        Path(options.root), options.action,
        dbt_path=Path(options.dbt) if options.dbt else None, dry_run=options.dry_run,
    )


def _install_cli(options: argparse.Namespace) -> None:
    install_cli()


def _new(options: argparse.Namespace) -> None:
    if not options.kind or not options.name:
        raise UsageError("Usage: md-blueprints new <flight|dive|guide|role|project> NAME [options]")
    run_new(
        Path(options.root), options.kind, options.name,
        input_ref=options.input_ref, share_url=options.share_url, alias=options.alias,
    )


def _doctor(options: argparse.Namespace) -> None:
    run_doctor(
        Path(options.root), output_format=options.format,
        check_updates=options.check_updates, offline=options.offline,
    )


def _check_updates(options: argparse.Namespace) -> None:
    run_check_updates(offline=options.offline, output_format=options.format)


def _migrate(options: argparse.Namespace) -> None:
    run_migrate(
        Path(options.root), from_version=options.from_version, to_version=options.to_version,
        write=options.write and not options.dry_run,
    )


def _upgrade(options: argparse.Namespace) -> None:
    run_upgrade(
        Path(options.root), to_version=options.to_version,
        write=options.write and not options.dry_run, offline=options.offline,
    )


def _import(options: argparse.Namespace) -> None:
    report = run_import(
        Project(Path(options.root)), target=options.target or "prod", selectors=options.resource,
        all_resources=options.all_blueprints, write=options.write and not options.dry_run,
        snapshot_path=Path(options.snapshot) if options.snapshot else None,
    )
    print(json.dumps(report, indent=2))


def _project(options: argparse.Namespace) -> tuple[Project, list[str] | None]:
    names = parse_blueprints(getattr(options, "blueprints", None))
    project = Project(Path(options.root))
    require_known_blueprints(project, names)
    return project, names


def _validate(options: argparse.Namespace) -> None:
    project, _ = _project(options)
    targets = [options.target] if options.target else project.target_names()
    project.validate(targets=targets, branch=options.branch)
    for warning in validation_warnings(project):
        print(f"warning: {warning}", file=sys.stderr)
    print(f"Validation passed for {len(project.all_blueprint_names())} blueprint(s).")


def _render(options: argparse.Namespace) -> None:
    project, names = _project(options)
    target = options.target or "prod"
    project.validate(targets=[target], branch=options.branch)
    expanded_names = project.deployment_blueprint_names(target, names)
    rendered = project.render_all(target, branch=options.branch, names=expanded_names)
    print(json.dumps([blueprint.to_dict() for blueprint in rendered], indent=2))


def _dive_source(options: argparse.Namespace) -> None:
    names = parse_blueprints(options.blueprints)
    if not names or len(names) != 1:
        raise ValidationError("dive-source requires exactly one --blueprints NAME")
    project, _ = _project(options)
    project.validate(targets=["prod"])
    rendered = project.render_all("prod", names=names)
    dives = rendered[0].dives
    if options.dive:
        if options.dive not in dives:
            raise ValidationError(
                f"Unknown Dive {options.dive!r} in blueprint {names[0]!r}. Valid keys: {', '.join(dives) or 'none'}"
            )
        selected_dive = dives[options.dive]
    elif len(dives) == 1:
        selected_dive = next(iter(dives.values()))
    elif not dives:
        raise ValidationError(f"Blueprint {names[0]!r} does not declare a Dive")
    else:
        raise ValidationError(
            f"Blueprint {names[0]!r} declares multiple Dives; select one with --dive RESOURCE_KEY "
            f"({', '.join(dives)})"
        )
    print(Path(str(selected_dive["sourcePath"])).relative_to(project.root))


def _changed(options: argparse.Namespace) -> None:
    project = Project(Path(options.root))
    changed = (
        project.all_blueprint_names()
        if options.all_blueprints
        else project.changed_blueprints(base=options.base, head=options.head or "HEAD")
    )
    print(json.dumps(changed) if options.json else "\n".join(changed))


def _plan(options: argparse.Namespace) -> None:
    project, names = _project(options)
    deployer = Deployer(project)
    records = deployer.plan(target=options.target or "prod", branch=options.branch, names=names)
    print(
        json.dumps([record.to_dict() for record in records], indent=2)
        if options.json
        else PlanFormatter.format(records, title="Deployment Plan")
    )
    deployer.ensure_plan_succeeds(records)


def _deploy(options: argparse.Namespace) -> None:
    project, names = _project(options)
    Deployer(project).deploy(
        target=options.target or "prod", branch=options.branch, names=names, verify=options.verify,
    )


def _verify(options: argparse.Namespace) -> None:
    project, names = _project(options)
    records = Deployer(project).verify(target=options.target or "prod", branch=options.branch, names=names)
    print(
        json.dumps([record.to_dict() for record in records], indent=2)
        if options.json else PlanFormatter.format(records, title="Live Verification")
    )


def _cleanup(options: argparse.Namespace) -> None:
    if options.json and not options.dry_run:
        raise UsageError("cleanup --json requires --dry-run; cleanup itself prints a text log")
    project, names = _project(options)
    deployer = Deployer(project)
    target = options.target or "preview"
    if options.dry_run:
        records = deployer.cleanup_plan(target=target, branch=options.branch, names=names)
        print(
            json.dumps([record.to_dict() for record in records], indent=2)
            if options.json
            else PlanFormatter.format(records, title="Cleanup Plan")
        )
        deployer.ensure_plan_succeeds(records)
    else:
        deployer.cleanup(target=target, branch=options.branch, names=names)


HANDLERS: dict[str, Callable[[argparse.Namespace], None]] = {
    "init": _init,
    "guides": _guides,
    "install-cli": _install_cli,
    "new": _new,
    "import": _import,
    "validate": _validate,
    "verify": _verify,
    "render": _render,
    "dive-source": _dive_source,
    "changed": _changed,
    "plan": _plan,
    "deploy": _deploy,
    "cleanup": _cleanup,
    "doctor": _doctor,
    "check-updates": _check_updates,
    "upgrade": _upgrade,
    "migrate": _migrate,
}
