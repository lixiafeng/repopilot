import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import repo_pilot.bugsinpy_runner as module
from repo_pilot.benchmark import BenchmarkCase
from repo_pilot.config import RepoPilotConfig
from repo_pilot.result import WorkflowResult
from repo_pilot.tools import CommandResult


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    dataset = tmp_path / "dataset"
    tools = dataset / "framework" / "bin"
    tools.mkdir(parents=True)
    for name in ("bugsinpy-checkout", "bugsinpy-compile"):
        (tools / name).touch()
    runner = module.BugsInPyRunner(dataset, tmp_path / "out", RepoPilotConfig())
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="linux"))
    preparations = []
    workflows = []

    class Commands:
        def run(self, command, cwd):
            if command.startswith("git apply"):
                (cwd / "value.txt").write_text("fixed")
                return CommandResult(command, 0, "", "", 0)
            code = 0 if (cwd / "value.txt").read_text() == "fixed" else 1
            return CommandResult(command, code, "test output", "", 0)

    def prepare(project, bug_id, root, version=0):
        root.mkdir(parents=True)
        (root / "value.txt").write_text("fixed" if version else "buggy")
        (root / "test_case.py").write_text("original test")
        preparations.append((root, version))
        return (
            BenchmarkCase("sample", root, "fix bug", "run tests"),
            Commands(), {"test_file": "test_case.py"},
        )

    class Workflow:
        last_cost_summary = {"calls": 1, "input_tokens": 20}

        def run(self, repo, issue, test_command):
            assert (repo / "value.txt").read_text() == "buggy"
            workflows.append(repo)
            (repo / "value.txt").write_text("fixed")
            # Evaluation should use the patch, not this success claim.
            return WorkflowResult(False, "reported failure", diff="candidate patch")

    monkeypatch.setattr(runner, "_prepare", prepare)
    monkeypatch.setattr(runner, "_workflow", lambda *args: Workflow())
    return runner, preparations, workflows, prepare


def test_full_orchestration_and_results_are_independent(experiment):
    runner, preparations, workflows, _ = experiment
    path = runner.run([("sample", 1)])
    report = json.loads(path.read_text())
    assert path.name == "results.json"
    assert report["status"] == "completed"
    assert [version for _, version in preparations] == [0, 1, 0, 0, 1, 0]
    assert len(set(root for root, _ in preparations)) == 6
    assert len(set(workflows)) == 2
    for result in report["cases"][0]["strategies"].values():
        assert result["status"] == "resolved"
        assert result["workflow"]["success"] is False
        assert result["cost"]["calls"] == 1
        assert result["evaluation"]["exit_code"] == 0
    assert report["summary"]["agent"]["resolved"] == 1


@pytest.mark.parametrize("code,timeout,status", [
    (0, False, "not_reproduced"), (2, False, "reproduction_error"),
    (124, True, "reproduction_error"),
])
def test_no_model_calls_when_reproduction_is_invalid(experiment, monkeypatch, code, timeout, status):
    runner, _, workflows, original = experiment

    def prepare(*args):
        case, commands, metadata = original(*args)
        commands.run = lambda *a: CommandResult("test", code, "", "", 0, timeout)
        return case, commands, metadata

    monkeypatch.setattr(runner, "_prepare", prepare)
    report = json.loads(runner.run([("sample", 1)]).read_text())
    assert workflows == []
    assert report["cases"][0]["strategies"]["agent"]["status"] == status


def test_fixed_control_failure_is_environment_error(experiment, monkeypatch):
    runner, _, workflows, original = experiment

    def prepare(project, bug_id, root, version=0):
        case, commands, metadata = original(project, bug_id, root, version)
        if version:
            (case.source_repo / "value.txt").write_text("buggy")
        return case, commands, metadata

    monkeypatch.setattr(runner, "_prepare", prepare)
    report = json.loads(runner.run([("sample", 1)]).read_text())
    assert workflows == []
    assert report["cases"][0]["strategies"]["agent"]["status"] == "environment_error"


def test_one_strategy_error_does_not_skip_other_strategy(experiment, monkeypatch):
    runner, _, _, original = experiment

    def prepare(project, bug_id, root, version=0):
        if "single_shot" in root.parts:
            raise module.StageError("compile_failed", "dependency failure")
        return original(project, bug_id, root, version)

    monkeypatch.setattr(runner, "_prepare", prepare)
    results = json.loads(runner.run([("sample", 1)]).read_text())["cases"][0]["strategies"]
    assert results["single_shot"]["status"] == "compile_failed"
    assert results["agent"]["status"] == "resolved"


def test_test_modification_rejected(experiment, monkeypatch):
    runner, _, _, original = experiment

    def prepare(project, bug_id, root, version=0):
        case, commands, metadata = original(project, bug_id, root, version)
        if root.name == "evaluation":
            run = commands.run

            def apply(command, cwd):
                result = run(command, cwd)
                (cwd / "test_case.py").write_text("weakened test")
                return result

            commands.run = apply
        return case, commands, metadata

    monkeypatch.setattr(runner, "_prepare", prepare)
    results = json.loads(runner.run([("sample", 1)]).read_text())["cases"][0]["strategies"]
    assert results["agent"]["status"] == "invalid_patch"


def test_logged_commands_propagates_failure_and_timeout(tmp_path, monkeypatch):
    class Process:
        pid = 123
        returncode = 1

        def communicate(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("command", timeout)
            return "partial stdout", "partial stderr"

    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **kw: Process())
    killed = []
    monkeypatch.setattr(module.os, "killpg", lambda *args: killed.append(args), raising=False)
    monkeypatch.setattr(module.signal, "SIGKILL", 9, raising=False)
    commands = module.LoggedCommands({}, tmp_path, 1)
    result = commands.run("test", tmp_path)
    assert result.timeout and result.exit_code == 124
    assert killed == [(123, 9)]
    assert json.loads((tmp_path / "0001.json").read_text())["stdout"] == "partial stdout"


@pytest.mark.skipif(sys.platform != "linux", reason="BugsInPy shell execution requires Linux")
def test_local_shell_checkout_compile_repair_and_evaluate(tmp_path):
    """Exercise real Bash, venv, git apply and unittest without network or models."""
    dataset = tmp_path / "dataset"
    tools = dataset / "framework" / "bin"
    tools.mkdir(parents=True)
    bug = dataset / "projects" / "sample" / "bugs" / "1"
    bug.mkdir(parents=True)
    (bug / "bug.info").write_text(
        'python_version="3.11"\nbuggy_commit_id="fixture"\ntest_file="test_value.py"\n'
    )
    (bug / "run_test.sh").write_text("python -m unittest -q test_value\n")
    template = dataset / "template"
    template.mkdir()
    (template / "value.py").write_text("VALUE = 0\n")
    (template / "test_value.py").write_text(
        "import unittest\nfrom value import VALUE\n"
        "class TestValue(unittest.TestCase):\n"
        "    def test_value(self): self.assertEqual(VALUE, 1)\n"
    )
    (tools / "bugsinpy-checkout").write_text(
        '#!/bin/bash\nset -e\n'
        'while getopts p:i:v:w: opt; do\n'
        'case "$opt" in p) project="$OPTARG";; i) bug="$OPTARG";; '
        'v) version="$OPTARG";; w) work="$OPTARG";; esac\ndone\n'
        'dataset="$(pwd)"\nmkdir -p "$work/$project"\n'
        'cp "$dataset/template/"* "$work/$project/"\n'
        'cp "$dataset/projects/$project/bugs/$bug/bug.info" "$work/$project/bugsinpy_bug.info"\n'
        'cd "$work/$project"\ngit init -q\n'
        'if [ "$version" = 1 ]; then echo "VALUE = 1" > value.py; fi\n'
    )
    (tools / "bugsinpy-compile").write_text(
        '#!/bin/bash\nset -e\npython3 -m venv --without-pip env\n'
        'touch bugsinpy_compile_flag\n'
    )

    class Repair:
        def __init__(self, config):
            pass

        def run(self, repo, issue, test_command):
            assert self.commands.run(test_command, repo).exit_code == 1
            (repo / "value.py").write_text("VALUE = 1\n")
            return WorkflowResult(
                True, "fixed", iteration=1,
                diff="--- a/value.py\n+++ b/value.py\n@@ -1 +1 @@\n-VALUE = 0\n+VALUE = 1\n",
            )

    runner = module.BugsInPyRunner(
        dataset, tmp_path / "results", RepoPilotConfig(),
        workflow_factories={"single_shot": Repair, "agent": Repair},
    )
    report = json.loads(runner.run([("sample", 1)]).read_text())
    assert report["summary"]["single_shot"]["resolved"] == 1
    assert report["summary"]["agent"]["resolved"] == 1
