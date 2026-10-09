from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.mark.parametrize("prefix", ["", "reusable_"])
def test_cleanup_environment_error_does_not_require_new_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefix: str,
) -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / f".github/workflows/{prefix}cleanup_preview_blueprints.yaml"
    workflow = yaml.safe_load(path.read_text())
    steps = workflow["jobs"]["resolve-environment"]["steps"]
    step = next(step for step in steps if step.get("id") == "preview-target")
    source = heredoc(step["run"])
    assert "md_blueprints" not in source
    (tmp_path / "motherduck.yml").write_text("targets: {preview: {mode: preview}}\n")
    summary = tmp_path / "summary"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "outputs"))
    monkeypatch.delenv("PR_AUTHOR", raising=False)
    monkeypatch.setenv("ACTOR", "octocat")
    with pytest.raises(SystemExit, match="must declare environment"):
        exec(compile(source, "cleanup_preview_blueprints.yaml", "exec"), {})
    assert "Next: check targets.preview" in summary.read_text()


def test_canonical_template_validates_without_live_deployment() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / ".github/workflows/reusable_deploy_blueprints.yaml"
    jobs = yaml.safe_load(path.read_text())["jobs"]
    assert "if" not in jobs["compute_changes"]
    for name in ("deploy-preview", "deploy-stable", "deploy-release-production"):
        assert "github.repository != 'motherduckdb/blueprints-template' &&" in jobs[name]["if"]


@pytest.mark.parametrize("prefix", ["", "reusable_"])
@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_environment_migration_validates_without_deploying_untrusted_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefix: str, event: str,
) -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / f".github/workflows/{prefix}deploy_blueprints.yaml").read_text())
    step = next(step for step in workflow["jobs"]["compute_changes"]["steps"] if step.get("id") == "topology")
    source = heredoc(step["run"])
    manifest = yaml.safe_load((root / "motherduck.yml").read_text())
    legacy = {"targets": {"preview": {"mode": "preview"}}}
    if event == "push":
        manifest["targets"]["prod"].pop("environment")
    (tmp_path / "motherduck.yml").write_text(yaml.safe_dump(manifest))
    output = tmp_path / "outputs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVENT_NAME", event)
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    summary = tmp_path / "summary"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: yaml.safe_dump(legacy))

    if event == "push":
        with pytest.raises(SystemExit, match="must declare environment"):
            exec(compile(source, "deploy_blueprints.yaml", "exec"), {})
        assert not output.exists()
        assert "Next: check targets in motherduck.yml" in summary.read_text()
    else:
        exec(compile(source, "deploy_blueprints.yaml", "exec"), {})
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        assert values["deployment_enabled"] == "false"
        assert values["environment"] == ""
        assert values["target"] == "preview"


def test_customer_workflows_delegate_with_matching_permissions_and_inputs(tmp_path: Path) -> None:
    from md_blueprints.init import run_init

    run_init(tmp_path)
    root = Path(__file__).resolve().parents[1]
    for path in (tmp_path / '.github/workflows').glob('*.yaml'):
        caller = yaml.safe_load(path.read_text())
        assert len(caller['jobs']) == 1
        job = next(iter(caller['jobs'].values()))
        reference = job['uses'].split('@')[0]
        provider = yaml.safe_load((root / reference.split('motherduck-blueprints/', 1)[1]).read_text())
        assert caller['permissions'] == provider['permissions']
        # PyYAML's YAML 1.1 loader reads the unquoted GitHub `on` key as True.
        inputs = (provider[True]['workflow_call'] or {}).get('inputs', {})
        assert set(job.get('with', {})) <= set(inputs)
        assert {name for name, config in inputs.items() if 'default' not in config} <= set(job.get('with', {}))
        # Optional runner inputs are offered as commented examples without changing defaults.
        text = path.read_text()
        for name in ('runs-on', 'python-version'):
            assert name not in job.get('with', {})
            assert f'# {name}: ' in text or f'#   {name}: ' in text
        # GitHub resolves an environment secret to an empty string in a reusable workflow unless the
        # caller passes it, so callers pass exactly the secrets their provider declares, by name.
        declared = (provider[True]['workflow_call'] or {}).get('secrets') or {}
        assert job.get('secrets', {}) == {name: f'${{{{ secrets.{name} }}}}' for name in declared}
        assert all('steps' not in value for value in caller['jobs'].values())


def test_reusable_jobs_preserve_environment_secrets_and_verification() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ('deploy_blueprints', 'cleanup_preview_blueprints'):
        workflow = yaml.safe_load((root / f'.github/workflows/reusable_{name}.yaml').read_text())
        # Optional so Dependabot and fork runs, which receive no secrets, still validate.
        secrets = workflow[True]['workflow_call']['secrets']
        assert set(secrets) == {'MOTHERDUCK_TOKEN'}
        assert secrets['MOTHERDUCK_TOKEN']['required'] is False
        for job in workflow['jobs'].values():
            for step in job.get('steps', []):
                command = step.get('with', {}).get('command')
                if command in ('plan', 'deploy', 'cleanup'):
                    assert 'environment' in job
                    assert step['env']['MOTHERDUCK_TOKEN'] == '${{ secrets.MOTHERDUCK_TOKEN }}'
                if command == 'deploy':
                    assert step['with']['verify-after-deploy'] == 'true'


def test_reusable_action_pins_match_the_release() -> None:
    from md_blueprints import __version__

    root = Path(__file__).resolve().parents[1]
    for path in (root / '.github/workflows').glob('reusable_*.yaml'):
        workflow = yaml.safe_load(path.read_text())
        pins = [
            step['uses']
            for job in workflow['jobs'].values()
            for step in job.get('steps', [])
            if step.get('uses', '').startswith('motherduckdb/motherduck-blueprints@')
        ]
        assert pins
        assert set(pins) == {f'motherduckdb/motherduck-blueprints@v{__version__}'}


ROOT = Path(__file__).resolve().parents[1]
RUNS_ON = "${{ startsWith(inputs.runs-on, '[') && fromJSON(inputs.runs-on) || inputs.runs-on || 'ubuntu-latest' }}"


def heredoc(script: str) -> str:
    return script.split("<<'PY'\n", 1)[1].split("\nPY")[0]


def reusable(name: str) -> Any:
    return yaml.safe_load((ROOT / f".github/workflows/reusable_{name}.yaml").read_text())


def run_topology(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, prefix: str = "reusable_", manifest: dict[str, Any] | None = None,
    **env: str,
) -> dict[str, str]:
    workflow = yaml.safe_load((ROOT / f".github/workflows/{prefix}deploy_blueprints.yaml").read_text())
    step = next(step for step in workflow["jobs"]["compute_changes"]["steps"] if step.get("id") == "topology")
    manifest = manifest or yaml.safe_load((ROOT / "motherduck.yml").read_text())
    (tmp_path / "motherduck.yml").write_text(yaml.safe_dump(manifest))
    output = tmp_path / "outputs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    monkeypatch.setenv("DEFAULT_BRANCH", "main")
    for key in ("INPUT_TARGET", "GIT_REF", "PR_AUTHOR", "BASE_REF", "RELEASE_PRERELEASE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    base = yaml.safe_dump(manifest)
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: base)
    exec(compile(heredoc(step["run"]), "deploy_blueprints.yaml", "exec"), {})
    return dict(line.split("=", 1) for line in output.read_text().splitlines())


@pytest.mark.parametrize("prefix", ["", "reusable_"])
@pytest.mark.parametrize("target", ["prod", "staging"])
def test_stable_dispatch_requires_default_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefix: str, target: str,
) -> None:
    manifest = yaml.safe_load((ROOT / "motherduck.yml").read_text())
    manifest["targets"]["staging"] = {**manifest["targets"]["prod"], "environment": "motherduck-staging"}
    with pytest.raises(SystemExit, match="must run from the default branch 'main'"):
        run_topology(
            tmp_path, monkeypatch, prefix=prefix, manifest=manifest,
            EVENT_NAME="workflow_dispatch", INPUT_TARGET=target, GIT_REF="refs/heads/feature/x",
        )
    assert "choose target preview" in (tmp_path / "summary").read_text()
    values = run_topology(
        tmp_path, monkeypatch, prefix=prefix, manifest=manifest,
        EVENT_NAME="workflow_dispatch", INPUT_TARGET=target, GIT_REF="refs/heads/main",
    )
    assert values["target"] == target
    assert values["deployment_enabled"] == "true"


def test_preview_dispatch_is_allowed_from_any_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    values = run_topology(
        tmp_path, monkeypatch, EVENT_NAME="workflow_dispatch", INPUT_TARGET="preview", GIT_REF="refs/heads/feature/x",
    )
    assert values["target"] == "preview"
    assert values["deployment_enabled"] == "true"


def test_staging_dispatch_without_staging_target_explains_choices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SystemExit, match="Choose preview or prod, or add targets.staging"):
        run_topology(
            tmp_path, monkeypatch, EVENT_NAME="workflow_dispatch", INPUT_TARGET="staging", GIT_REF="refs/heads/main",
        )


@pytest.mark.parametrize("prefix", ["", "reusable_"])
def test_dependabot_pull_requests_validate_without_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefix: str,
) -> None:
    values = run_topology(
        tmp_path, monkeypatch, prefix=prefix, EVENT_NAME="pull_request", BASE_REF="main", PR_AUTHOR="dependabot[bot]",
    )
    assert values["target"] == "preview"
    assert values["deployment_enabled"] == "false"
    assert "Dependabot pull requests are validated without a preview" in (tmp_path / "summary").read_text()
    values = run_topology(
        tmp_path, monkeypatch, prefix=prefix, EVENT_NAME="pull_request", BASE_REF="main", PR_AUTHOR="octocat",
    )
    assert values["deployment_enabled"] == "true"


@pytest.mark.parametrize("prefix", ["", "reusable_"])
@pytest.mark.parametrize("author, actor, skip", [
    ("dependabot[bot]", "octocat", "true"),
    ("", "dependabot[bot]", "true"),
    ("octocat", "octocat", "false"),
])
def test_cleanup_skips_dependabot_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefix: str, author: str, actor: str, skip: str,
) -> None:
    workflow = yaml.safe_load((ROOT / f".github/workflows/{prefix}cleanup_preview_blueprints.yaml").read_text())
    step = next(step for step in workflow["jobs"]["resolve-environment"]["steps"] if step.get("id") == "preview-target")
    manifest = yaml.safe_load((ROOT / "motherduck.yml").read_text())
    (tmp_path / "motherduck.yml").write_text(yaml.safe_dump(manifest))
    output = tmp_path / "outputs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    monkeypatch.setenv("PR_AUTHOR", author)
    monkeypatch.setenv("ACTOR", actor)
    with pytest.raises(SystemExit) if skip == "true" else contextlib.nullcontext() as result:
        exec(compile(heredoc(step["run"]), "cleanup_preview_blueprints.yaml", "exec"), {})
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert values["skip"] == skip
    if skip == "true":
        assert result is not None and result.value.code == 0
        assert "environment" not in values
        assert "Dependabot" in (tmp_path / "summary").read_text()
    assert workflow["jobs"]["cleanup"]["if"] == "needs.resolve-environment.outputs.skip != 'true'"


@pytest.mark.parametrize("prefix", ["", "reusable_"])
def test_cleanup_skips_dependabot_before_checkout_and_supports_older_base_actions(prefix: str) -> None:
    job = yaml.safe_load((ROOT / f".github/workflows/{prefix}cleanup_preview_blueprints.yaml").read_text())["jobs"][
        "resolve-environment"
    ]
    # PRs opened before a release run the job logic from their merge ref, so the guard must not need a checkout.
    assert job["if"].startswith("github.actor != 'dependabot[bot]' && (")
    assert "github.event.pull_request.user.login != 'dependabot[bot]'" in job["if"]
    step = next(step for step in job["steps"] if step.get("id") == "preview-target")
    # The base commit's action may predate the python output and install into the job Python instead.
    assert '"${MD_BLUEPRINTS_PYTHON:-python}" - <<\'PY\'' in step["run"]


@pytest.mark.parametrize("prefix", ["", "reusable_"])
def test_preview_deploy_and_cleanup_share_one_branch_concurrency_group(prefix: str) -> None:
    deploy = yaml.safe_load((ROOT / f".github/workflows/{prefix}deploy_blueprints.yaml").read_text())
    cleanup = yaml.safe_load((ROOT / f".github/workflows/{prefix}cleanup_preview_blueprints.yaml").read_text())
    deploy_group = deploy["jobs"]["deploy-preview"]["concurrency"]
    cleanup_group = cleanup["jobs"]["cleanup"]["concurrency"]
    assert "concurrency" not in cleanup
    # pull_request events share github.head_ref. Manual previews use the branch input; delete events use the ref.
    assert deploy_group["group"] == "md-blueprints-preview-${{ github.head_ref || inputs.branch }}"
    assert cleanup_group["group"] == "md-blueprints-preview-${{ github.head_ref || github.event.ref }}"
    assert cleanup_group["cancel-in-progress"] is False
    assert "environment" in cleanup["jobs"]["cleanup"]


def test_reusable_workflows_expose_runner_inputs_and_isolate_checkouts() -> None:
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    for name in ("deploy_blueprints", "cleanup_preview_blueprints", "blueprints_doctor", "prepare_guide_context"):
        workflow = reusable(name)
        inputs = workflow[True]["workflow_call"]["inputs"]
        assert inputs["runs-on"] == {
            "description": inputs["runs-on"]["description"], "type": "string", "default": "ubuntu-latest",
        }
        assert inputs["python-version"]["default"] == action["inputs"]["python-version"]["default"]
        for job_name, job in workflow["jobs"].items():
            assert job["runs-on"] == RUNS_ON
            for step in job["steps"]:
                uses = step.get("uses", "")
                if uses.startswith("motherduckdb/motherduck-blueprints@"):
                    assert step["with"]["python-version"] == "${{ inputs.python-version }}"
                if uses.startswith("actions/checkout@") and job_name != "deploy-release-production":
                    assert step["with"]["persist-credentials"] is False, (name, job_name)
            if "timeout-minutes" in job:
                assert inputs["timeout-minutes"]["default"] == 10
                assert job["timeout-minutes"] == "${{ inputs.timeout-minutes || 10 }}"


def test_python_helpers_use_the_action_environment() -> None:
    for name, job, step_id in (
        ("deploy_blueprints", "compute_changes", "topology"),
        ("cleanup_preview_blueprints", "resolve-environment", "preview-target"),
    ):
        steps = reusable(name)["jobs"][job]["steps"]
        step = next(step for step in steps if step.get("id") == step_id)
        assert step["env"]["MD_BLUEPRINTS_PYTHON"] == "${{ steps.validate.outputs.python }}"
        assert any(line in step["run"] for line in (
            "\"$MD_BLUEPRINTS_PYTHON\" - <<'PY'",
            "\"${MD_BLUEPRINTS_PYTHON:-python}\" - <<'PY'",
        ))
        assert any(step.get("id") == "validate" and "motherduck-blueprints@" in step["uses"] for step in steps)


def test_generated_repository_jobs_use_reusable_input_defaults() -> None:
    for name in ("deploy_blueprints", "cleanup_preview_blueprints", "blueprints_doctor", "prepare_guide_context"):
        text = (ROOT / f".github/workflows/{name}.yaml").read_text()
        for field in ("runs-on", "python-version", "timeout-minutes"):
            assert f"inputs.{field}" not in text
        workflow = yaml.safe_load(text)
        assert all(job["runs-on"] == "ubuntu-latest" for job in workflow["jobs"].values())


@pytest.mark.parametrize("name, lookup", [
    ("deploy_blueprints", "github.rest.issues.listComments"),
    ("blueprints_doctor", "github.rest.issues.listForRepo"),
])
def test_github_script_lookups_paginate_and_truncate(name: str, lookup: str) -> None:
    scripts = [
        step["with"]["script"]
        for job in reusable(name)["jobs"].values() for step in job["steps"]
        if step.get("uses", "").startswith("actions/github-script@")
    ]
    assert len(scripts) == 1
    script = scripts[0]
    assert f"github.paginate.iterator({lookup}" in script
    assert "per_page: 100" in script
    assert "const limit = 65000 -" in script
    assert "Output truncated" in script


def test_customer_template_only_watches_customer_paths(tmp_path: Path) -> None:
    from md_blueprints.init import run_init

    run_init(tmp_path)
    workflow = yaml.safe_load((tmp_path / ".github/workflows/deploy_blueprints.yaml").read_text())
    for event in ("push", "pull_request"):
        paths = workflow[True][event]["paths"]
        for path in paths:
            root = path.split("/**")[0]
            assert (tmp_path / root).exists() or root in {"blueprints", "guides", "roles", "projects"}, path
        for maintainer_path in ("src/**", "tools/**", "scripts/**", "action.yml", "pyproject.toml"):
            assert maintainer_path not in paths
    codeowners = (tmp_path / ".github/CODEOWNERS").read_text()
    for line in codeowners.splitlines():
        if line.startswith("# /"):
            owned = line[2:].split()[0].strip("/")
            assert (tmp_path / owned).exists() or owned in {"guides", "roles", "projects", "blueprints"}, owned


def preview_comment_step() -> dict[str, Any]:
    steps = reusable("deploy_blueprints")["jobs"]["deploy-preview"]["steps"]
    return next(step for step in steps if step.get("name") == "Comment on pull request")


def test_preview_comment_uses_the_deploy_report_and_moves_the_plan_to_the_run_summary() -> None:
    steps = reusable("deploy_blueprints")["jobs"]["deploy-preview"]["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Summarize preview plan") < names.index("Deploy preview blueprints")
    assert "GITHUB_STEP_SUMMARY" in steps[names.index("Summarize preview plan")]["run"]
    assert set(preview_comment_step()["env"]) == {"DEPLOY_OUTPUT"}


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("report, closes_details", [
    ("**Selected:** `listings`\n\n#### Listings\n\n<details>\n<summary>Verified</summary>\n\n" + "| row |\n" * 20000, True),
    ("#### Listings\n\n" + "| link |\n" * 20000, False),
])
def test_preview_comment_truncation_keeps_the_notice_outside_details(report: str, closes_details: bool) -> None:
    script = preview_comment_step()["with"]["script"]
    body_script = script[: script.index("let existing;")]
    # Pass the report on stdin: Linux caps a single environment string at 128 KiB.
    harness = (
        "process.env.DEPLOY_OUTPUT = require('fs').readFileSync(0, 'utf8');\n"
        "const context = {serverUrl: 'https://github.com', repo: {owner: 'o', repo: 'r'}, runId: 1};\n"
        + body_script
        + "\nprocess.stdout.write(JSON.stringify(body));\n"
    )
    node = shutil.which("node")
    assert node is not None
    result = subprocess.run(
        [node, "-e", harness], input=report, env={},
        capture_output=True, text=True, check=True,
    )
    body = json.loads(result.stdout)

    assert len(body) <= 65000
    assert body.startswith("<!-- preview-blueprints-comment -->\n### Preview Blueprints\n")
    assert body.endswith("for the full plan and deployment log._")
    assert ("</details>\n\n_Output truncated." in body) is closes_details
