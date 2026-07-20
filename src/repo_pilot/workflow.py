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

        print("Building context pack...")
        state.context_pack=self.context_builder.build(state)
        print("ContextPack:")

        print(f"  issue: {state.context_pack['issue']}")

        print("  candidate files:")
        for file_name in state.context_pack["candidate_files"]:
            print(f"    - {file_name}")

        print("  snippets:")    
        for snippet in state.context_pack["snippets"]:
            print(f"    file: {snippet['path']}")
            print(f"    truncated: {snippet['truncated']}")
            print("    content:")
            print(snippet["content"])

        print("  symbol hits:")
        for symbol in state.context_pack["symbol_hits"]:
            print(
            f"    - {symbol['type']} "
            f"{symbol['name']} "
            f"({symbol['file']}:{symbol['line']})"
            )
            
        print("Creating repair plan...")
        state.plan=self.planner.plan(
            context_pack=state.context_pack,
        )
        print("Repair plan:")
        print(
            f"  root cause: "
            f"{state.plan['root_cause_hypothesis']}"
        )

        print("  files to inspect:")
        for file_name in state.plan["files_to_inspect"]:
            print(f"    - {file_name}")

        print("  files to modify:")
        for file_name in state.plan["files_to_modify"]:
            print(f"    - {file_name}")

        print(
            f"  patch strategy: "
            f"{state.plan['patch_strategy']}"
        )

        print("  verification commands:")
        for command in state.plan["verification_commands"]:
            print(f"    - {command}")

        print("  risks:")
        for risk in state.plan["risks"]:
            print(f"    - {risk}")

        print("Create JSON patch...")
        state.patch=self.patcher.propose_patch(
            context_pack=state.context_pack,
            plan=state.plan,     
        )
        print("JSON patch:")
        print(f"  notes: {state.patch.get('notes', '')}")
        print("  operations:")
        for operation in state.patch["operations"]:
            print(f"    type: {operation['type']}")
            print(f"    path: {operation['path']}")

            print("    old:")
            print(operation["old"])

            print("    new:")
            print(operation["new"])
        
        print("Reviewing JSON patch...")
        review_result=self.reviewer.review(
            patch=state.patch,
        )
        print(
            f"Patch approved:"
            f"{review_result['approved']}"
        )
        print("Review issues:")

        if review_result["issues"]:
            for issue_text in review_result["issues"]:
                print(f"  - {issue_text}")
        else:
            print("  No issues found.") 
        
        if not review_result["approved"]:
            return WorkflowResult(
                success=False,
                message=(
                    "Patch review failed. "
                ),
                iteration=0,
                test_output=output,
            )
        
        if not self.config.apply_patch:
            return WorkflowResult(
                success=False,
                message=(
                    "JSON patch generated and approved,"
                    "but patch application is disabled."
                    ),
                iteration=0,
                test_output=output,
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
            return WorkflowResult(
                success=False,
                message=f"Patch application failed:{exc}",
                iteration=1,
                test_output=output,
            )
        
        print("Patch applied successfully.")
        print("Generated diff:")
        print(state.diff)

        return WorkflowResult(
    success=False,
    message=(
        "Patch applied successfully, "
        "but verification has not run yet."
    ),
    iteration=1,
    diff=state.diff,
    test_output=output,
)

    
  
  


