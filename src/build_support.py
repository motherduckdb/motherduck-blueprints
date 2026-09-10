"""Assemble distribution assets from their authoritative repository files."""
import json
from pathlib import Path

from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()
        root = Path(__file__).resolve().parents[1]
        mapping = json.loads((root / 'src/md_blueprints/asset-map.json').read_text())
        for destination, source in mapping.items():
            target = Path(self.build_lib) / 'md_blueprints' / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            self.copy_file(str(root / source), str(target))
