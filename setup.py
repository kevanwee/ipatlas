"""Include the canonical, reviewable data directories in built distributions."""
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithResources(build_py):
    def run(self):
        super().run()
        root = Path(__file__).parent
        for folder in ['data']:
            for source in (root / folder).rglob("*"):
                if source.is_file() and source.suffix in {".yaml", ".json"}:
                    destination = (
                        Path(self.build_lib) / "ipatlas" / "_resources"
                        / source.relative_to(root)
                    )
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    self.copy_file(str(source), str(destination))


setup(cmdclass={"build_py": BuildWithResources})
