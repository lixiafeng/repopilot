import traceback
from pathlib import Path

from repo_pilot.config import RepoPilotConfig
from repo_pilot.context import ContextBuilder
from repo_pilot.cost import CostTracker
from repo_pilot.failure import FailureAnalyzer
from repo_pilot.output import OutputWriter
from repo_pilot.patcher import Patcher
from repo_pilot.planner import PatchPlanner
from repo_pilot.provider import ProviderError, create_provider
from repo_pilot.result import WorkflowResult
from repo_pilot.retry import RetryPolicy
from repo_pilot.reviewer import PatchReviewer
from repo_pilot.scanner import RepoScanner
from repo_pilot.state import AgentState
from repo_pilot.symbols import SymbolIndexer
from repo_pilot.tools import CommandTools
from repo_pilot.trace import TraceRecorder
from repo_pilot.verifier import Verifier


class BugfixWorkflow:
    def __init__(
        self,
        config: RepoPilotConfig,
    ) -> None:
        self.config = config
        self.commands = CommandTools(
            timeout_sec=config.command_timeout_sec
        )
        self.scanner = RepoScanner()
        self.symbols_indexer = SymbolIndexer()
        self.failure_analyzer = FailureAnalyzer()
        self.context_builder = ContextBuilder(
            max_files=5,
            max_chars_per_files=4000,
        )
        self.provider = create_provider(
            provider_name=config.provider,
            model=config.model,
        )
        self.planner = PatchPlanner(
            provider=self.provider
        )
        self.patcher = Patcher(
            provider=self.provider,
        )
        self.reviewer = PatchReviewer()
        self.verifier = Verifier(
            commands=self.commands,
        )
        self.retry = RetryPolicy()
        self.output_writer = OutputWriter()
        self.last_cost_summary: dict = {}

    def _finish(
        self,
        trace: TraceRecorder,
        result: WorkflowResult,
        cost_tracker: CostTracker,
    ) -> WorkflowResult:
        cost_summary = cost_tracker.summary()
        self.last_cost_summary = cost_summary

        trace.add(
            event_type="cost_summary",
            payload=cost_summary,
        )
        trace.add(
            event_type="workflow_finished",
            payload={
                "success": result.success,
                "message": result.message,
                "iteration": result.iteration,
                "diff": bool(result.diff.strip()),
            },
        )

        cost_path = cost_tracker.save(
            run_dir=trace.run_dir
        )
        output_paths = self.output_writer.save(
            run_dir=trace.run_dir,
            result=result,
            cost_summary=cost_summary,
        )
        trace_path = trace.save()

        print(f"Cost saved to: {cost_path}")
        print(
            f"Summary saved to: "
            f"{output_paths['summary']}"
        )
        if output_paths["diff"] is not None:
            print(
                f"Diff saved to: "
                f"{output_paths['diff']}"
            )
        print(f"Trace saved to: {trace_path}")

        return result

    def run(
        self,
        repo: Path,
        issue: str,
        test_command: str,
    ) -> WorkflowResult:
        self.last_cost_summary = {}
        repo = repo.resolve()

        state = AgentState(
            repo=repo,
            issue=issue,
            test_command=test_command,
        )
        trace = TraceRecorder(
            trace_root=self.config.trace_dir,
        )
        cost_tracker = CostTracker()

        trace.add(
            event_type="workflow_started",
            payload={
                "repo": repo,
                "issue": issue,
                "test_command": test_command,
                "provider": self.config.provider,
                "model": self.config.model,
                "apply_patch": self.config.apply_patch,
                "max_iterations": self.config.max_iterations,
            },
        )

        try:
            return self._run_pipeline(
                repo=repo,
                issue=issue,
                test_command=test_command,
                state=state,
                trace=trace,
                cost_tracker=cost_tracker,
            )
        except (
            ProviderError,
            ValueError,
            OSError,
        ) as exc:
            trace.add(
                event_type="workflow_error",
                payload={
                    "stage": state.current_stage,
                    "iteration": state.iteration,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )
            return self._finish(
                trace=trace,
                cost_tracker=cost_tracker,
                result=WorkflowResult(
                    success=False,
                    message=(
                        "Workflow failed during "
                        f"{state.current_stage}: {exc}"
                    ),
                    iteration=state.iteration,
                    diff=state.diff,
                    test_output=state.last_test_output,
                ),
            )
        except Exception as exc:
            trace.add(
                event_type="workflow_error",
                payload={
                    "stage": state.current_stage,
                    "iteration": state.iteration,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "unexpected": True,
                    "traceback": traceback.format_exc(),
                },
            )
            return self._finish(
                trace=trace,
                cost_tracker=cost_tracker,
                result=WorkflowResult(
                    success=False,
                    message=(
                        "Unexpected workflow error during "
                        f"{state.current_stage}: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                    iteration=state.iteration,
                    diff=state.diff,
                    test_output=state.last_test_output,
                ),
            )

    def _run_pipeline(
        self,
        repo: Path,
        issue: str,
        test_command: str,
        state: AgentState,
        trace: TraceRecorder,
        cost_tracker: CostTracker,
    ) -> WorkflowResult:
        print("AgentState started")
        print(f"repo={repo}")
        print(f"issue={issue}")

        state.current_stage = "repo_scan"
        state.repo_map = self.scanner.scan(repo)
        trace.add(
            event_type="repo_scanned",
            payload={
                "file_count": len(state.repo_map["files"]),
                "python_files": state.repo_map["python_files"],
                "test_files": state.repo_map["test_files"],
                "config_files": state.repo_map["config_files"],
            },
        )

        state.current_stage = "symbol_index"
        state.symbol_index = self.symbols_indexer.build(
            repo=repo,
            python_files=state.repo_map["python_files"],
        )
        trace.add(
            event_type="symbols_indexed",
            payload={
                "symbol_count": len(state.symbol_index),
                "symbols": state.symbol_index,
            },
        )

        print("Running initial test command...")
        state.current_stage = "initial_test"
        test_result = self.commands.run(
            command=test_command,
            cwd=repo,
        )
        output = test_result.stdout + test_result.stderr
        state.last_test_output = output

        trace.add(
            event_type="initial_test_finished",
            payload={
                "success": test_result.success,
                "exit_code": test_result.exit_code,
                "duration_seconds": test_result.duration_seconds,
                "timeout": test_result.timeout,
                "output": output,
            },
        )

        print(f"exit_code={test_result.exit_code}")
        print(
            f"duration_seconds="
            f"{test_result.duration_seconds:.2f}"
        )
        print(output)

        if test_result.success:
            state.current_stage = "finished"
            return self._finish(
                cost_tracker=cost_tracker,
                trace=trace,
                result=WorkflowResult(
                    success=True,
                    message=(
                        "Initial test command passed. "
                        "No patch was required."
                    ),
                    iteration=0,
                    test_output=output,
                ),
            )

        print("Analyzing test failures...")
        state.current_stage = "failure_analysis"
        (
            state.failures,
            state.candidates,
        ) = self.failure_analyzer.analyze(
            result=test_result,
            repo=repo,
        )
        trace.add(
            event_type="failure_analyzed",
            payload={
                "failures": state.failures,
                "candidates": [
                    path.as_posix()
                    for path in state.candidates
                ],
            },
        )

        last_failure_output = output
        last_diff = ""

        for iteration in range(
            1,
            self.config.max_iterations + 1,
        ):
            state.iteration = iteration
            trace.add(
                event_type="iteration_started",
                payload={"iteration": iteration},
            )

            print()
            print(
                "===== Repair iteration "
                f"{iteration}/"
                f"{self.config.max_iterations} ====="
            )

            state.current_stage = "context_build"
            state.context_pack = self.context_builder.build(
                state
            )
            trace.add(
                event_type="context_built",
                payload={
                    "iteration": iteration,
                    "candidate_files": state.context_pack[
                        "candidate_files"
                    ],
                    "snippet_count": len(
                        state.context_pack["snippets"]
                    ),
                    "previous_attempt_count": len(
                        state.context_pack["previous_attempts"]
                    ),
                },
            )

            print("Creating repair plan...")
            state.current_stage = "repair_plan"
            state.plan = self.planner.plan(
                context_pack=state.context_pack,
                cost_tracker=cost_tracker,
            )
            trace.add(
                event_type="plan_created",
                payload={
                    "iteration": iteration,
                    "plan": state.plan,
                },
            )

            # --------------------------------------------------
            # Plan-driven context refresh
            # --------------------------------------------------
            # The planner may discover that a file needs to be
            # modified even though that file was not present in
            # the original failure-driven context. Before asking
            # the patch model to edit it, load its real source.
            planned_files = state.plan.get(
                "files_to_modify",
                [],
            )

            if not isinstance(
                planned_files,
                list,
            ):
                planned_files = []

            planned_files = [
                str(file_name)
                for file_name in planned_files
            ]

            before_refresh = list(
                state.context_pack.get(
                    "candidate_files",
                    [],
                )
            )

            state.context_pack = (
                self.context_builder.add_files(
                    context_pack=(
                        state.context_pack
                    ),
                    state=state,
                    file_names=(
                        planned_files
                    ),
                )
            )

            after_refresh = list(
                state.context_pack.get(
                    "candidate_files",
                    [],
                )
            )

            added_files = [
                file_name
                for file_name in after_refresh
                if file_name not in before_refresh
            ]

            trace.add(
                event_type=(
                    "context_refreshed_from_plan"
                ),
                payload={
                    "iteration": iteration,
                    "planned_files_to_modify": (
                        planned_files
                    ),
                    "added_files": added_files,
                    "candidate_files": (
                        after_refresh
                    ),
                    "snippet_count": len(
                        state.context_pack.get(
                            "snippets",
                            [],
                        )
                    ),
                },
            )

            if added_files:
                print(
                    "Context refreshed from plan: "
                    + ", ".join(added_files)
                )

            print("Creating JSON patch...")
            state.current_stage = "patch_generation"
            state.patch = self.patcher.propose_patch(
                context_pack=state.context_pack,
                plan=state.plan,
                cost_tracker=cost_tracker,
            )
            trace.add(
                event_type="patch_created",
                payload={
                    "iteration": iteration,
                    "patch": state.patch,
                },
            )

            print("Reviewing JSON patch...")
            state.current_stage = "patch_review"
            review_result = self.reviewer.review(
                patch=state.patch,
            )
            trace.add(
                event_type="patch_reviewed",
                payload={
                    "iteration": iteration,
                    "approved": review_result["approved"],
                    "issues": review_result["issues"],
                },
            )
            print(
                "Patch approved: "
                f"{review_result['approved']}"
            )

            if not review_result["approved"]:
                review_output = "\n".join(
                    review_result["issues"]
                )
                failure_type = self.retry.classify(
                    stage="patch_review",
                    output=review_output,
                )
                retry_allowed = self.retry.should_retry(
                    failure_type=failure_type,
                    iteration=iteration,
                    max_iterations=self.config.max_iterations,
                )
                state.attempts.append(
                    {
                        "iteration": iteration,
                        "stage": "patch_review",
                        "failure_type": failure_type,
                        "retry_allowed": retry_allowed,
                        "issues": review_result["issues"],
                    }
                )
                trace.add(
                    event_type="retry_decision",
                    payload={
                        "iteration": iteration,
                        "stage": "patch_review",
                        "failure_type": failure_type,
                        "retry_allowed": retry_allowed,
                        "output": review_output,
                    },
                )
                if retry_allowed:
                    continue
                return self._finish(
                    cost_tracker=cost_tracker,
                    trace=trace,
                    result=WorkflowResult(
                        success=False,
                        message="Patch review failed.",
                        iteration=iteration,
                        test_output=last_failure_output,
                    ),
                )

            if not self.config.apply_patch:
                return self._finish(
                    cost_tracker=cost_tracker,
                    trace=trace,
                    result=WorkflowResult(
                        success=False,
                        message=(
                            "JSON patch generated and approved, "
                            "but patch application is disabled."
                        ),
                        iteration=iteration,
                        test_output=last_failure_output,
                    ),
                )

            snapshot = self.patcher.create_snapshot(
                repo=repo,
                patch=state.patch,
            )

            print("Applying JSON patch...")
            try:
                state.current_stage = "patch_apply"
                state.diff = self.patcher.apply(
                    repo=repo,
                    patch=state.patch,
                )
                trace.add(
                    event_type="patch_applied",
                    payload={
                        "iteration": iteration,
                        "diff": state.diff,
                    },
                )
            except (
                ValueError,
                FileNotFoundError,
            ) as exc:
                self.patcher.restore_snapshot(
                    repo=repo,
                    snapshot=snapshot,
                )
                trace.add(
                    event_type="snapshot_restored",
                    payload={"iteration": iteration},
                )

                failure_type = self.retry.classify(
                    stage="patch_apply",
                    output="",
                    error_message=str(exc),
                )
                retry_allowed = self.retry.should_retry(
                    failure_type=failure_type,
                    iteration=iteration,
                    max_iterations=self.config.max_iterations,
                )
                state.attempts.append(
                    {
                        "iteration": iteration,
                        "stage": "patch_apply",
                        "failure_type": failure_type,
                        "error": str(exc),
                        "retry_allowed": retry_allowed,
                    }
                )
                trace.add(
                    event_type="retry_decision",
                    payload={
                        "iteration": iteration,
                        "stage": "patch_apply",
                        "failure_type": failure_type,
                        "retry_allowed": retry_allowed,
                        "output": str(exc),
                    },
                )
                if retry_allowed:
                    continue
                return self._finish(
                    cost_tracker=cost_tracker,
                    trace=trace,
                    result=WorkflowResult(
                        success=False,
                        message=(
                            "Patch application failed: "
                            f"{exc}. Retry allowed: "
                            f"{retry_allowed}"
                        ),
                        iteration=iteration,
                        diff=last_diff,
                        test_output=last_failure_output,
                    ),
                )

            print("Patch applied successfully.")
            print("Generated diff:")
            print(state.diff)

            print("Verifying applied patch...")
            state.current_stage = "verification"
            state.verification = self.verifier.verify(
                repo=repo,
                test_command=test_command,
            )
            state.last_test_output = state.verification["output"]

            trace.add(
                event_type="verification_finished",
                payload={
                    "iteration": iteration,
                    "success": state.verification["success"],
                    "stage": state.verification["stage"],
                    "exit_code": state.verification["exit_code"],
                    "output": state.verification["output"],
                },
            )

            print(
                "Verification stage: "
                f"{state.verification['stage']}"
            )
            print(
                "Verification exit code: "
                f"{state.verification['exit_code']}"
            )
            print("Verification output:")
            print(state.verification["output"])

            if state.verification["success"]:
                state.current_stage = "finished"
                return self._finish(
                    cost_tracker=cost_tracker,
                    trace=trace,
                    result=WorkflowResult(
                        success=True,
                        message=(
                            "Patch applied and "
                            "verified successfully."
                        ),
                        iteration=iteration,
                        diff=state.diff,
                        test_output=state.verification["output"],
                    ),
                )

            failure_type = self.retry.classify(
                stage=state.verification["stage"],
                output=state.verification["output"],
            )
            retry_allowed = self.retry.should_retry(
                failure_type=failure_type,
                iteration=iteration,
                max_iterations=self.config.max_iterations,
            )

            state.attempts.append(
                {
                    "iteration": iteration,
                    "stage": state.verification["stage"],
                    "failure_type": failure_type,
                    "retry_allowed": retry_allowed,
                    "verification": state.verification,
                    "diff": state.diff,
                }
            )
            trace.add(
                event_type="retry_decision",
                payload={
                    "iteration": iteration,
                    "stage": state.verification["stage"],
                    "failure_type": failure_type,
                    "retry_allowed": retry_allowed,
                    "output": state.verification["output"],
                },
            )

            last_failure_output = state.verification["output"]
            last_diff = state.diff

            print(f"Failure type: {failure_type}")
            print(f"Retry allowed: {retry_allowed}")

            state.current_stage = "rollback"
            self.patcher.restore_snapshot(
                repo=repo,
                snapshot=snapshot,
            )
            trace.add(
                event_type="snapshot_restored",
                payload={"iteration": iteration},
            )
            print(
                "Repository restored to the state "
                "before this iteration."
            )

            if retry_allowed:
                continue

            return self._finish(
                cost_tracker=cost_tracker,
                trace=trace,
                result=WorkflowResult(
                    success=False,
                    message=(
                        "Patch verification failed during "
                        f"{state.verification['stage']} stage."
                    ),
                    iteration=iteration,
                    diff=last_diff,
                    test_output=last_failure_output,
                ),
            )

        return self._finish(
            cost_tracker=cost_tracker,
            trace=trace,
            result=WorkflowResult(
                success=False,
                message="Maximum repair iterations reached.",
                iteration=state.iteration,
                diff=last_diff,
                test_output=last_failure_output,
            ),
        )
