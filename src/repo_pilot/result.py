from dataclasses import dataclass


@dataclass
class WorkflowResult:
    success: bool
    message: str
    iteration: int=0
    diff: str=""
    test_output:str=""

