"""Assemble distribution assets from their authoritative repository files."""
import json
from pathlib import Path

from setuptools.command.build_py import build_py
from setuptools.command.egg_info import egg_info

ROOT = Path(__file__).resolve().parents[1]


def asset_map():
    return json.loads((ROOT / "src/md_blueprints/asset-map.json").read_text())


class EggInfo(egg_info):
    def find_sources(self):
        super().find_sources()
        self.filelist.files = sorted(set(self.filelist.files) | {
            "src/build_support.py", *asset_map().values(),
        })
        self.write_file(
            "manifest file", str(Path(self.egg_info) / "SOURCES.txt"),
            "\n".join(self.filelist.files) + "\n",
        )


class BuildPy(build_py):
    def run(self):
        super().run()
        for destination, source in asset_map().items():
            target = Path(self.build_lib) / 'md_blueprints' / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            self.copy_file(str(ROOT / source), str(target))
