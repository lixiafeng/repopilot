from pathlib import Path
from typing import Any

class RepoScanner:
    IGNORED_DIRS = {
        ".git",
        ".venv",
        ".venv-1",
        "__pycache__",
        ".pytest_cache",
        "build",
        "dist",
    }
    def scan(self,repo:Path)->dict[str,Any]:
        files:list[str]=[]
        python_files:list[str]=[]
        test_files:list[str]=[]
        config_files:list[str]=[]

        for path in repo.rglob("*"):
            if path.is_dir():
                continue

            relative_path=path.relative_to(repo)
            if any(part in  self.IGNORED_DIRS for part in relative_path.parts):
                continue

            rel=relative_path.as_posix()

            files.append(rel)

            if path.suffix==".py":
                python_files.append(rel)

            if path.name.startswith("test_") or "tests" in relative_path.parts:
                test_files.append(rel)

            if path.name in {"pyproject.toml","setup.py","requirements.txt"}:
                config_files.append(rel)

        return{
            "files":files,
            "python_files":python_files,
            "test_files":test_files,
            "config_files":config_files,
            "project_type":"python",

        }
