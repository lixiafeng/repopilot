from pathlib import Path

from repo_pilot.context import (
    ContextBuilder,
)
from repo_pilot.state import AgentState


def test_context_expands_local_import(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "age.py").write_text(
        "def is_adult(age: int) -> bool:\n"
        "    return age > 18\n",
        encoding="utf-8",
    )

    (
        repo / "test_age.py"
    ).write_text(
        "from age import is_adult\n",
        encoding="utf-8",
    )

    state = AgentState(
        repo=repo,
        issue=(
            "age 18 should be adult"
        ),
        test_command=(
            "python -m pytest -q"
        ),
    )

    state.repo_map = {
        "project_type": "python",
        "files": [
            "age.py",
            "test_age.py",
        ],
        "python_files": [
            "age.py",
            "test_age.py",
        ],
        "test_files": [
            "test_age.py",
        ],
        "config_files": [],
    }

    state.candidates = [
        Path("test_age.py")
    ]

    state.failures = []

    state.symbol_index = [
        {
            "type": "import_from",
            "name": "age.is_adult",
            "file": "test_age.py",
            "line": 1,
        },
        {
            "type": "function",
            "name": "is_adult",
            "file": "age.py",
            "line": 1,
        },
    ]

    builder = ContextBuilder()

    context = builder.build(
        state
    )

    assert context[
        "candidate_files"
    ] == [
        "test_age.py",
        "age.py",
    ]

    snippet_paths = {
        snippet["path"]
        for snippet
        in context["snippets"]
    }

    assert snippet_paths == {
        "test_age.py",
        "age.py",
    }