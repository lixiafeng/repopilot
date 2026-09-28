import subprocess
import sys
from pathlib import Path

import pytest

from repo_pilot.benchmark import BenchmarkCase, EvalRunner
from repo_pilot.bugsinpy import BugsInPyAdapter
from repo_pilot.result import WorkflowResult


@pytest.fixture
def prepared_bug(tmp_path: Path):
    dataset = tmp_path / "BugsInPy"
    bug = dataset / "projects" / "sample" / "bugs" / "1"
    bug.mkdir(parents=True)
    info = (
        'python_version="3.11"\n'
        'buggy_commit_id="buggy-revision"\n'
        'fixed_commit_id="secret-gold-revision"\n'
        'test_file="test_sample.py"\n'
    )
    (bug / "bug.info").write_text(info, encoding="utf-8")
    (bug / "run_test.sh").write_text(
        "python -m unittest -q test_sample\n", encoding="utf-8"
    )
    repo = tmp_path / "checkout with spaces"
    repo.mkdir()
    (repo / "bugsinpy_compile_flag").touch()
    (repo / "bugsinpy_bug.info").write_text(info, encoding="utf-8")
    (repo / "value.py").write_text("VALUE = 0\n", encoding="utf-8")
    (repo / "test_sample.py").write_text(
        "import unittest\nfrom value import VALUE\n"
        "class TestValue(unittest.TestCase):\n"
        "    def test_value(self):\n"
        "        self.assertEqual(VALUE, 1)\n",
        encoding="utf-8",
    )
    return dataset, bug, repo


def test_case_runs_in_eval_copy_and_preserves_failure_exit_code(prepared_bug, tmp_path):
    dataset, bug, repo = prepared_bug
    # A later passing command must not mask the first failure.
    (bug / "run_test.sh").write_text(
        "python -m unittest -q test_sample\npython -m unittest -q\n",
        encoding="utf-8",
    )
    case = BugsInPyAdapter(dataset, python_executable=sys.executable).to_case(
        "sample", 1, source_repo=repo
    )
    assert isinstance(case, BenchmarkCase)
    assert case.name == "bugsinpy_sample_1"
    assert "secret-gold-revision" not in case.issue

    class RepairWorkflow:
        def run(self, repo, issue, test_command):
            failed = subprocess.run(test_command, cwd=repo, shell=True, capture_output=True)
            assert failed.returncode != 0
            (repo / "value.py").write_text("VALUE = 100 - 99\n", encoding="utf-8")
            passed = subprocess.run(test_command, cwd=repo, shell=True, capture_output=True)
            return WorkflowResult(
                success=passed.returncode == 0,
                message="checked real tests",
                iteration=1,
            )

    report = EvalRunner(RepairWorkflow, tmp_path / "reports").run([case])
    assert report.summary["passed_cases"] == 1
    assert (repo / "value.py").read_text() == "VALUE = 0\n"


@pytest.mark.parametrize("invocation", ["pytest", "py.test", "python -m pytest", "python3 -m pytest"])
def test_pytest_commands_preserve_arguments(prepared_bug, invocation):
    dataset, bug, repo = prepared_bug
    (bug / "run_test.sh").write_text(
        f'#!/bin/bash\n# relevant tests\n{invocation} -q "tests/test file.py::test_one"\n',
        encoding="utf-8",
    )
    case = BugsInPyAdapter(dataset).to_case("sample", "1", source_repo=repo)
    assert case.test_command.startswith("python -m pytest -q ")
    assert "tests/test file.py::test_one" in case.test_command


@pytest.mark.parametrize("script", ["", "# comment\n", "pytest a; pytest b", "export X=1\npytest", "bash tests.sh"])
def test_unsupported_scripts_require_override(prepared_bug, script):
    dataset, bug, repo = prepared_bug
    (bug / "run_test.sh").write_text(script, encoding="utf-8")
    adapter = BugsInPyAdapter(dataset)
    with pytest.raises(ValueError):
        adapter.to_case("sample", 1, source_repo=repo)
    case = adapter.to_case(
        "sample", 1, source_repo=repo, issue="Specific bug report",
        test_command="python -m unittest -q",
    )
    assert case.issue == "Specific bug report"
    assert case.test_command == "python -m unittest -q"


@pytest.mark.parametrize("project,bug_id", [("../sample", 1), ("sample", "../1"), ("sample", 0)])
def test_invalid_identifiers(prepared_bug, project, bug_id):
    dataset, _, repo = prepared_bug
    with pytest.raises(ValueError):
        BugsInPyAdapter(dataset).to_case(project, bug_id, source_repo=repo)


def test_mismatched_checkout(prepared_bug):
    dataset, _, repo = prepared_bug
    info = repo / "bugsinpy_bug.info"
    info.write_text(info.read_text().replace("buggy-revision", "another-bug"))
    with pytest.raises(ValueError, match="Checkout metadata differs"):
        BugsInPyAdapter(dataset).to_case("sample", 1, source_repo=repo)


def test_missing_metadata_and_checkout(prepared_bug):
    dataset, bug, repo = prepared_bug
    adapter = BugsInPyAdapter(dataset)
    with pytest.raises(FileNotFoundError):
        adapter.to_case("sample", 2, source_repo=repo)
    with pytest.raises(FileNotFoundError, match="checkout"):
        adapter.to_case("sample", 1, source_repo=repo / "missing")
    (bug / "bug.info").write_text('python_version="3.11"\n')
    with pytest.raises(ValueError, match="buggy_commit_id"):
        adapter.to_case("sample", 1, source_repo=repo)


def test_missing_regression_test(prepared_bug):
    dataset, _, repo = prepared_bug
    (repo / "test_sample.py").unlink()
    with pytest.raises(FileNotFoundError, match="regression test missing"):
        BugsInPyAdapter(dataset).to_case("sample", 1, source_repo=repo)


@pytest.mark.parametrize("is_directory", [False, True])
@pytest.mark.parametrize("test_command", [None, "python -m unittest -q"])
def test_compile_flag_required(prepared_bug, is_directory, test_command):
    dataset, _, repo = prepared_bug
    flag = repo / "bugsinpy_compile_flag"
    flag.unlink()
    if is_directory:
        flag.mkdir()
    with pytest.raises(FileNotFoundError, match="Run bugsinpy-compile") as error:
        BugsInPyAdapter(dataset).to_case(
            "sample", 1, source_repo=repo, test_command=test_command,
        )
    assert str(flag) in str(error.value)


def test_custom_pythonpath_requires_explicit_command(prepared_bug):
    dataset, bug, repo = prepared_bug
    with (bug / "bug.info").open("a") as info:
        info.write('pythonpath="src;lib"\n')
    adapter = BugsInPyAdapter(dataset)
    with pytest.raises(ValueError, match="PYTHONPATH"):
        adapter.to_case("sample", 1, source_repo=repo)
    case = adapter.to_case(
        "sample", 1, source_repo=repo,
        test_command="PYTHONPATH=src:lib python -m unittest -q",
    )
    assert case.test_command.startswith("PYTHONPATH=")
