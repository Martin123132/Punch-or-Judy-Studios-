from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "PuppetForge"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def app_data_dir() -> Path:
    override = os.getenv("PUPPET_FORGE_HOME")
    if override:
        root = Path(override).expanduser()
    elif os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        root = base / APP_NAME
    else:
        root = Path.home() / ".local" / "share" / "puppet-forge"
    root.mkdir(parents=True, exist_ok=True)
    return root


def db_path() -> Path:
    return app_data_dir() / "puppet_forge.sqlite3"


def outputs_dir() -> Path:
    path = app_data_dir() / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def render_dir(render_id: str) -> Path:
    path = outputs_dir() / render_id
    path.mkdir(parents=True, exist_ok=True)
    return path

