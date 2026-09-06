"""Run explicitly with make journey-smoke; requires Node and npm for the README builds."""
from pathlib import Path
import re
import shlex
import subprocess
import sys

from md_blueprints.init import run_init
from md_blueprints.project import Project


def test_generated_readme_journey(tmp_path: Path) -> None:
    run_init(tmp_path)
    cli = Path(sys.executable).parent / "md-blueprints"

    def run(*args: str) -> str:
        return subprocess.check_output(args, cwd=tmp_path, text=True, stderr=subprocess.STDOUT)

    project = Project(tmp_path)
    starter = ["wikipedia-pageviews-ingest", "wikipedia-pageviews"]
    assert project.all_blueprint_names() == starter
    assert (tmp_path / "examples/ncs-field-recovery/blueprint.yml").is_file()
    assert not (tmp_path / "projects/ncs-field-recovery").exists()

    run("git", "init", "-b", "main")
    run("git", "config", "user.name", "Journey Test")
    run("git", "config", "user.email", "journey@example.test")
    run("git", "add", ".")
    run("git", "commit", "-m", "initial starter")
    base = run("git", "rev-parse", "HEAD").strip()

    # Execute README commands using the candidate CLI instead of downloading a released version.
    readme = (tmp_path / "README.md").read_text()
    fence = chr(96) * 3
    blocks = re.findall(fence + r"bash\n(.*?)" + fence, readme, flags=re.DOTALL)
    assert blocks
    commands = [line for block in blocks for line in block.splitlines() if line.strip()]
    assert "make validate" in commands and "make preview-smoke wikipedia-pageviews" in commands
    for command in commands:
        argv = shlex.split(command)
        assert argv[0] == "make", f"Add support for this README step: {command}"
        run("make", f"CLI={cli}", *argv[1:])

    run("git", "switch", "-c", "test/first-preview")
    manifest = tmp_path / "flights/wikipedia-pageviews-ingest/blueprint.yml"
    assert "flights/wikipedia-pageviews-ingest/blueprint.yml" in readme
    manifest.write_text(re.sub(r"^description:.*$", "description: My first deployment", manifest.read_text(), flags=re.M))
    run("git", "add", str(manifest))
    run("git", "commit", "-m", "customize starter")
    project = Project(tmp_path)
    changed = project.changed_blueprints(base=base, head="HEAD")
    assert changed == ["wikipedia-pageviews-ingest"]
    for target in ("preview", "prod"):
        assert project.deployment_blueprint_names(target, changed) == starter
        project.validate(targets=[target], branch="test/first-preview")
    assert (tmp_path / ".dive-preview/dist/index.html").is_file()
