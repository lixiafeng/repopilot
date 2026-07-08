from pathlib import Path
from repo_pilot.config import RepoPilotConfig
from repo_pilot.result import WorkflowResult
from repo_pilot.state import AgentState

class BugfixWorkflow:
    def __init__(self,config: RepoPilotConfig):
        self.config = config
    def run(
            self,
            repo:Path,
            issue:str,
            test_command:str,

    )->WorkflowResult:
        state=AgentState(
            repo=repo,
            issue=issue,
            test_command=test_command,
        )
        

        print("Workflow started")
        print(f"repo={repo}")
        print(f"issue={issue}")
        print(f"test_command={test_command}")
        print(f"provider={self.config.provider}")
        print(f"model={self.config.model}")
        print(f"apply_patch={self.config.apply_patch}")
        print(f"max_iterations={self.config.max_iterations}")

        return WorkflowResult(
            success=True,
            message="AgentState created successfully",
            iteration=0,
        )

    
  
  


