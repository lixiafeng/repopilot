from pathlib import Path

from repo_pilot.context import ContextBuilder
from repo_pilot.state import AgentState


def test_plan_refresh_adds_planned_source_file(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "processor.py").write_text(
        "import importlib\n\n"
        "def normalize_and_score(value: str) -> int:\n"
        "    rules = importlib.import_module('score_rules')\n"
        "    return rules.score(value)\n",
        encoding="utf-8",
    )

    (repo / "score_rules.py").write_text(
        "def score(value: str) -> int:\n"
        "    \"\"\"Return the score.\"\"\"\n"
        "    return len(value) + 1\n",
        encoding="utf-8",
    )

    (repo / "test_02_score.py").write_text(
        "from processor import normalize_and_score\n\n"
        "def test_normal_score() -> None:\n"
        "    assert normalize_and_score('abc') == 3\n",
        encoding="utf-8",
    )

    state = AgentState(
        repo=repo,
        issue=(
            "normal scoring should return "
            "the expected score"
        ),
        test_command="python -m pytest -q",
    )

    state.repo_map = {
        "project_type": "python",
        "files": [
            "processor.py",
            "score_rules.py",
            "test_02_score.py",
        ],
        "python_files": [
            "processor.py",
            "score_rules.py",
            "test_02_score.py",
        ],
        "test_files": [
            "test_02_score.py",
        ],
        "config_files": [],
    }

    state.failures = []
    state.candidates = [
        Path("test_02_score.py"),
        Path("processor.py"),
    ]

    state.symbol_index = [
        {
            "type": "import_from",
            "name": (
                "processor."
                "normalize_and_score"
            ),
            "file": "test_02_score.py",
            "line": 1,
        },
        {
            "type": "import",
            "name": "importlib",
            "file": "processor.py",
            "line": 1,
        },
        {
            "type": "function",
            "name": "score",
            "file": "score_rules.py",
            "line": 1,
        },
    ]

    builder = ContextBuilder(
        max_files=5,
        max_chars_per_files=4000,
    )

    context = builder.build(state)

    # Dynamic import means score_rules.py is not discovered by the
    # initial static import expansion.
    assert "score_rules.py" not in (
        context["candidate_files"]
    )

    refreshed = builder.add_files(
        context_pack=context,
        state=state,
        file_names=[
            "processor.py",
            "score_rules.py",
        ],
    )

    assert "score_rules.py" in (
        refreshed["candidate_files"]
    )

    snippets = {
        snippet["path"]: snippet["content"]
        for snippet in refreshed["snippets"]
    }

    assert "score_rules.py" in snippets
    assert (
        "return len(value) + 1"
        in snippets["score_rules.py"]
    )
