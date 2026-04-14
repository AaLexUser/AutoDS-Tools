"""Virtual environment resolution for agent subprocesses."""

from __future__ import annotations

import os
import venv
from pathlib import Path


def resolve_venv_env(project_path: Path) -> dict[str, str]:
    """Return env vars that make child processes use the project venv."""
    venv_dir = project_path.resolve() / ".venv"
    if not (venv_dir / ("Scripts" if os.name == "nt" else "bin")).exists():
        venv.create(venv_dir, with_pip=True, symlinks=(os.name != "nt"))

    bin_dir = str(venv_dir / ("Scripts" if os.name == "nt" else "bin"))
    env = dict(os.environ)
    env["VIRTUAL_ENV"] = str(venv_dir)
    env.pop("PYTHONHOME", None)
    path = env.get("PATH", "")
    if not path.startswith(bin_dir):
        env["PATH"] = bin_dir + os.pathsep + path
    return env
