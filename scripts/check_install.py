"""Build sdist -> wheel, install outside the checkout, and exercise shipped resources.

Run after installing .[dev]. The temporary venv shares dependency packages, but the
project itself must resolve to its freshly installed wheel, never an editable copy.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "ipatlas"


def run(*args: str, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True)


def main() -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONUTF8"] = "1"
    with tempfile.TemporaryDirectory(prefix=PACKAGE + "-install-") as temporary:
        work = Path(temporary)
        artifacts = work / "artifacts"
        run(sys.executable, "-m", "build", "--sdist", "--outdir", str(artifacts),
            str(ROOT), cwd=work, env=env)
        with tarfile.open(next(artifacts.glob("*.tar.gz"))) as archive:
            archive.extractall(work / "source", filter="data")
        source = next((work / "source").iterdir())
        run(sys.executable, "-m", "build", "--wheel", "--outdir", str(artifacts),
            str(source), cwd=work, env=env)
        venv_path = work / "venv"
        venv.EnvBuilder(with_pip=True, system_site_packages=True).create(venv_path)
        scripts = venv_path / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        run(str(python), "-m", "pip", "install", "--no-deps", "--force-reinstall",
            str(next(artifacts.glob("*.whl"))), cwd=work, env=env)
        check = (
            "import sys; from pathlib import Path; import " + PACKAGE + "; "
            "assert Path(" + PACKAGE + ".__file__).is_relative_to(Path(sys.prefix))"
        )
        run(str(python), "-c", check, cwd=work, env=env)
        cli = scripts / ("ipatlas.exe" if os.name == "nt" else "ipatlas")
        run(str(cli), "compare", "trade_mark", "SG", "US", "CN", "-a", "term",
            cwd=work, env=env)
        run(str(cli), "offices", cwd=work, env=env)
        run(str(cli), "routes", "trade_mark", "SG", "US", "CN", cwd=work, env=env)
        run(str(python), "-c", "from ipatlas.core import load_atlas; "
            "assert set(load_atlas().codes) >= {'SG', 'US', 'CN'}", cwd=work, env=env)
    print("Installed distribution checks passed.")


if __name__ == "__main__":
    main()
