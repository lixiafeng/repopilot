from pathlib import Path

from repo_pilot.config import RepoPilotConfig
from repo_pilot.context import ContextBuilder
from repo_pilot.cost import CostTracker
from repo_pilot.failure import FailureAnalyzer
from repo_pilot.patcher import Patcher
from repo_pilot.provider import create_provider
from repo_pilot.result import WorkflowResult
from repo_pilot.reviewer import PatchReviewer
from repo_pilot.scanner import RepoScanner
from repo_pilot.state import AgentState
from repo_pilot.symbols import SymbolIndexer
from repo_pilot.tools import CommandTools
from repo_pilot.verifier import Verifier


class SingleShotWorkflow:
    """
    Context-aware single-shot baseline.

    与 RepoPilot Agent 共享：
    - RepoScanner
    - SymbolIndexer
    - FailureAnalyzer
    - ContextBuilder
    - Patcher
    - PatchReviewer
    - Verifier
    - 相同模型

    区别：
    - 不调用 LLM Planner
    - 只进行一次 Patch Generation Attempt
    - 不做 Workflow-level Retry
    - 不做 Reflection / Test Feedback 后再次生成补丁

    注意：structured output 内部如果为了修复 JSON 格式而再次请求模型，
    model_calls 可能大于 1。因此这里的 single-shot 指的是
    “单次 Patch Generation Attempt”，而不是绝对只发生一次 HTTP 调用。
    """

    def __init__(
        self,
        config: RepoPilotConfig,
    ) -> None:
        self.config = config

        self.commands = CommandTools(
            timeout_sec=(
                config.command_timeout_sec
            )
        )

        self.scanner = RepoScanner()
        self.symbol_indexer = SymbolIndexer()
        self.failure_analyzer = FailureAnalyzer()

        self.context_builder = ContextBuilder(
            max_files=5,
            max_chars_per_files=4000,
        )

        self.provider = create_provider(
            provider_name=config.provider,
            model=config.model,
        )

        self.patcher = Patcher(
            provider=self.provider,
        )

        self.reviewer = PatchReviewer()

        self.verifier = Verifier(
            commands=self.commands,
        )

        self.last_cost_summary: dict = {}

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

        cost_tracker = CostTracker()

        state.repo_map = self.scanner.scan(
            repo
        )

        state.symbol_index = (
            self.symbol_indexer.build(
                repo=repo,
                python_files=(
                    state.repo_map[
                        "python_files"
                    ]
                ),
            )
        )

        test_result = self.commands.run(
            command=test_command,
            cwd=repo,
        )

        initial_output = (
            test_result.stdout
            + test_result.stderr
        )

        state.last_test_output = (
            initial_output
        )

        if test_result.success:
            self.last_cost_summary = (
                cost_tracker.summary()
            )

            return WorkflowResult(
                success=True,
                message=(
                    "Initial test command passed. "
                    "No patch was required."
                ),
                iteration=0,
                diff="",
                test_output=initial_output,
            )

        (
            state.failures,
            state.candidates,
        ) = self.failure_analyzer.analyze(
            result=test_result,
            repo=repo,
        )

        state.context_pack = (
            self.context_builder.build(
                state
            )
        )

        baseline_plan = {
            "root_cause_hypothesis": (
                "Infer the root cause directly "
                "from the supplied repository "
                "context and test failure."
            ),
            "files_to_inspect": (
                state.context_pack.get(
                    "candidate_files",
                    [],
                )
            ),
            "files_to_modify": (
                state.context_pack.get(
                    "candidate_files",
                    [],
                )
            ),
            "patch_strategy": (
                "Produce one minimal repair "
                "without workflow-level retry "
                "or reflection."
            ),
            "verification_commands": [
                test_command
            ],
            "risks": [],
        }

        try:
            patch = self.patcher.propose_patch(
                context_pack=(
                    state.context_pack
                ),
                plan=baseline_plan,
                cost_tracker=cost_tracker,
            )
            print("Generated single-shot patch:")
            print(patch)

            review_result = (
                self.reviewer.review(
                    patch=patch,
                )
            )

            if not review_result[
                "approved"
            ]:
                self.last_cost_summary = (
                    cost_tracker.summary()
                )

                return WorkflowResult(
                    success=False,
                    message=(
                        "Single-shot patch "
                        "review failed: "
                        + "; ".join(
                            review_result[
                                "issues"
                            ]
                        )
                    ),
                    iteration=1,
                    diff="",
                    test_output=(
                        initial_output
                    ),
                )

            if not self.config.apply_patch:
                self.last_cost_summary = (
                    cost_tracker.summary()
                )

                return WorkflowResult(
                    success=False,
                    message=(
                        "Single-shot patch "
                        "was generated and approved, "
                        "but patch application "
                        "is disabled."
                    ),
                    iteration=1,
                    diff="",
                    test_output=(
                        initial_output
                    ),
                )

            diff = self.patcher.apply(
                repo=repo,
                patch=patch,
            )

        except Exception as exc:
            self.last_cost_summary = (
                cost_tracker.summary()
            )

            return WorkflowResult(
                success=False,
                message=(
                    "Single-shot patch failed: "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
                iteration=1,
                diff="",
                test_output=initial_output,
            )

        verification = (
            self.verifier.verify(
                repo=repo,
                test_command=test_command,
            )
        )

        self.last_cost_summary = (
            cost_tracker.summary()
        )

        return WorkflowResult(
            success=bool(
                verification["success"]
            ),
            message=(
                "Single-shot repair succeeded."
                if verification["success"]
                else
                "Single-shot repair failed "
                "verification."
            ),
            iteration=1,
            diff=diff,
            test_output=str(
                verification["output"]
            ),
        )
