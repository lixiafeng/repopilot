from pathlib import Path
from repo_pilot.config import RepoPilotConfig
from repo_pilot.result import WorkflowResult
from repo_pilot.state import AgentState
from repo_pilot.symbols import SymbolIndexer
from repo_pilot.tools import CommandTools
from repo_pilot.scanner import RepoScanner
from repo_pilot.failure import FailureAnalyzer
from repo_pilot.context import ContextBuilder
from repo_pilot.provider import create_provider
from repo_pilot.planner import PatchPlanner
from repo_pilot.patcher import Patcher
from repo_pilot.reviewer import PatchReviewer
from repo_pilot.verifier import Verifier
from repo_pilot.retry import RetryPolicy

class BugfixWorkflow:
    def __init__(self,config: RepoPilotConfig):
        self.config = config
        self.commands=CommandTools(timeout_sec=config.command_timeout_sec)
        self.scanner=RepoScanner()
        self.symbols_indexer=SymbolIndexer()
        self.failure_analyzer=FailureAnalyzer()
        self.context_builder=ContextBuilder(
            max_files=5,
            max_chars_per_files=4000,
        )
        self.provider=create_provider(
            provider_name=config.provider,
            model=config.model,
        )
        self.planner=PatchPlanner(provider=self.provider)
        
        self.patcher=Patcher(
            provider=self.provider,
        )
        self.reviewer=PatchReviewer()

        self.verifier=Verifier(
            commands=self.commands,
            )
        self.retry=RetryPolicy()

    def run(
            self,
            repo:Path,
            issue:str,
            test_command:str,
    )->WorkflowResult:
        repo=repo.resolve()
        state=AgentState(
            repo=repo,
            issue=issue,
            test_command=test_command,
        )
        

        print("AgentState started")
        print(f"repo={repo}")
        print(f"issue={issue}")
        

        print("Scanner repository")
        state.repo_map=self.scanner.scan(repo)
        print("Files")
        for file in state.repo_map["files"]:
            print(f"  -{file}")

        print("Python Files")
        for file in state.repo_map["python_files"]:
            print(f"  -{file}")

        print("Test Files")
        for file in state.repo_map["test_files"]:
            print(f"  -{file}")

        state.symbol_index=self.symbols_indexer.build(
            repo=repo,
            python_files=state.repo_map["python_files"]
        )

        print("Symbols:")
        for symbol in state.symbol_index:
            print(
                f"  - {symbol['type']}"
                f"{symbol['name']}"
                f"({symbol['file']}:{symbol['line']})"
            )




        print("Running initial test command...")
        test_result=self.commands.run(
            command=test_command,
            cwd=repo,
        )
        output=test_result.stdout+test_result.stderr

        print(f"exit_code={test_result.exit_code}")
        print(f"duration_seconds={test_result.duration_seconds:.2f}")
        print(output)

        print("Analyzing test failures...")
        state.failures,state.candidates=self.failure_analyzer.analyze(
            result=test_result,
            repo=repo,
        )
        print("Failures:")
        if state.failures:
            for failure in state.failures:
                print(f"  summary = {failure['summary']}")
                print(f"  exception_type = {failure['exception_type']}")
                print(f"  exception_message = {failure['exception_message']}")

                print("  failed_tests:")
                for failed_test in failure["failed_tests"]:
                    print(f"    - {failed_test}")

                print("  locations:")
                for location in failure["locations"]:
                   print(f"    - {location['file']}:{location['line']}")
        else:
            print("  No failures found.")

        print("Candidate files:")
        if state.candidates:
            for candidate in state.candidates:
                print(f"  - {candidate.as_posix()}")    
        else:
            print("  No candidate files found.")

        if test_result.success:
            return WorkflowResult(
                success=True,
                message=(
                    "Initial test command passed."
                    "No patch was required."
                ),
                iteration=0,
                test_output=output,
            )
        
        last_failure_output=output
        last_diff=""
        for iteration in range(1,self.config.max_iterations+1):
            print()
            print(
                f"=====Repair iteration"
                f"{iteration}/"
                f"{self.config.max_iterations}====="
            )
            

            print("Building context pack...")
            state.context_pack=self.context_builder.build(state)
     
            
            print("Creating repair plan...")
            state.plan=self.planner.plan(
                context_pack=state.context_pack,
            )
        
            print("Create JSON patch...")
            state.patch=self.patcher.propose_patch(
                context_pack=state.context_pack,
                plan=state.plan,     
            )
       
            print("Reviewing JSON patch...")
            review_result=self.reviewer.review(
                patch=state.patch,
            )
            print(
                f"Patch approved:"
                f"{review_result['approved']}"
            )
        
        
            if not review_result["approved"]:
                failure_type=(
                    self.retry.classify(
                    stage="patch_review",
                    output="\n".join(
                        review_result["issues"]
                    ),
                )
                )
                retry_allowed=(
                    self.retry.should_retry(
                    failure_type=failure_type,
                    iteration=iteration,
                    max_iterations=self.config.max_iterations,
                )
                )
                state.attempts.append({
                    "iteration":iteration,
                    "stage":"patch_review",
                    "failure_type": failure_type,
                    "retry_allowed": retry_allowed,
                    "issues": review_result["issues"],
                })
                print(
                    f"Failure type: {failure_type}"
                    f"Retry allowed: {retry_allowed}"
                )
                if retry_allowed:
                    continue

                return WorkflowResult(
                    success=False,
                    message=(
                        "Patch review failed. "
                    ),
                    iteration=iteration,
                    test_output=last_failure_output,
                )
            
            if not self.config.apply_patch:
                return WorkflowResult(
                    success=False,
                    message=(
                        "JSON patch generated and approved,"
                        "but patch application is disabled."
                        ),
                    iteration=iteration,
                    test_output=last_failure_output,
                )
            
            snapshot=self.patcher.create_snapshot(
                repo=repo,
                patch=state.patch,
            )
            
            print ("Applying JSON patch...")

            try:
                state.diff=self.patcher.apply(
                    repo=repo,
                    patch=state.patch,
                )
            except(
                ValueError,
                FileNotFoundError,
            ) as exc:
                self.patcher.restore_snapshot(
                    repo=repo,
                    snapshot=snapshot,
                )
            
                failure_type=(self.retry.classify(
                    stage="patch_apply",
                    output="",
                    error_message=str(exc),
                )
                )
                retry_allowed=(self.retry.should_retry(
                    failure_type=failure_type,
                    iteration=iteration,
                    max_iterations=self.config.max_iterations,
                )
                )

                state.attempts.append({
                    "iteration":iteration,
                    "stage":"patch_apply",
                    "failure_type":failure_type,
                    "error":str(exc),
                    "retry_allowed":retry_allowed,
                })

                print(f"Failure type: {failure_type}")
                print(f"Retry allowed: {retry_allowed}")
                if retry_allowed:
                    continue
                
                return WorkflowResult(
                    success=False,
                    message=( f"Patch application failed: {exc}. "
                f"Retry allowed: {retry_allowed}"),
                    iteration=iteration,
                    test_output=last_failure_output,
                )
        
            print("Patch applied successfully.")
            print("Generated diff:")
            print(state.diff)

            print("Verifying applied patch...")

            state.verification=self.verifier.verify(
                repo=repo,
                test_command=test_command,
            )
            print(  
                f"Verification stage: "
                f"{state.verification['stage']}"
            )
            print(
                f"Verification exit code: "
                f"{state.verification['exit_code']}"
            )
            print("Verification output:")
            print(state.verification["output"])

# 测试通过后，整个 bug 修复任务才算成功。
            if state.verification["success"]:
                return WorkflowResult(
                    success=True,
                    message="Patch applied and verified successfully.",
                    iteration=iteration,
                    diff=state.diff,
                    test_output=state.verification["output"],
                )
            
            failure_type = self.retry_policy.classify(
                stage=state.verification["stage"],
                output=state.verification["output"],
            )

# 判断是否还有下一轮机会。
            retry_allowed = (self.retry_policy.should_retry(
                failure_type=failure_type,
                iteration=1,
                max_iterations=self.config.max_iterations,
            )
            )

# 把本轮失败信息保存到 AgentState。
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

            last_failure_output=(
                state.verification["output"]
            )
            last_diff=state.diff

            print(f"Failure type: {failure_type}")
            print(f"Retry allowed: {retry_allowed}")
            self.patcher.restore_snapshot(
                repo=repo,
                snapshot=snapshot,
            )

            print(
                "Repository restored to the state "
                "before this iteration."
            )

            if retry_allowed:
                continue

            return WorkflowResult(
                success=False,
                message=(
                    "Patch verification failed during "
                    f"{state.verification['stage']} "
                    "stage."
                ),
                iteration=iteration,
                diff=last_diff,
                test_output=last_failure_output,
            )
        
        return WorkflowResult(
            success=False,
            message="Maximum repair iterations reached.",
            iteration=self.config,
            diff=last_diff,
            test_output=last_failure_output,
        )
                        


   

    
  
  


