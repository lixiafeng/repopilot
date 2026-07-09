from pathlib import Path
from repo_pilot.config import RepoPilotConfig
from repo_pilot.result import WorkflowResult
from repo_pilot.state import AgentState
from repo_pilot.tools import CommandTools
from repo_pilot.scanner import RepoScanner

class BugfixWorkflow:
    def __init__(self,config: RepoPilotConfig):
        self.config = config
        self.commands=CommandTools(timeout_sec=config.command_timeout_sec)
        self.scanner=RepoScanner()
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



        print("Running initial test command...")
        test_result=self.commands.run(
            command=test_command,
            cwd=repo,
        )
        output=test_result.stdout+test_result.stderr

        print(f"exit_code={test_result.exit_code}")
        print(output)

        return WorkflowResult(
            success=test_result.success,
            message="AgentState created successfully",
            iteration=0,
            test_output=output,
        )

    
  
  


