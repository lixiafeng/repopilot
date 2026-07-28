from dataclasses import dataclass,field
from pathlib import Path
from typing import Any

@dataclass
class AgentState:
    repo: Path
    issue: str
    test_command: str
    
    current_stage:str="initialization"
    iteration:int=0
    last_test_output:str=""



    repo_map: dict[str,Any]=field(default_factory=dict)
    symbol_index:list[dict[str,Any]]=field(default_factory=list)

    failures:list[dict[str,Any]]=field(default_factory=list)
    candidates:list[Path]=field(default_factory=list)
    
    context_pack:dict[str,Any]|None=None
    plan:dict[str,Any]|None=None
    patch:dict[str,Any]|None=None

    diff: str=""
    verification:dict[str,Any]|None=None

    attempts:list[dict[str,Any]]=field(default_factory=list)



