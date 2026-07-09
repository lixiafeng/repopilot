import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

@dataclass
class CommandResult:
    command:str
    exit_code:int 
    stdout:str
    stderr:str
    duration_seconds:float
    timeout:bool=False

    @property
    def success(self)->bool:
        return self.exit_code==0

class CommandTools:
    def __init__(self,timeout_sec:int=30):
        self.timeout_sec=timeout_sec
        
    def run(self,command:str,cwd:Path)->CommandResult:
        start=time.time()

        try:
            proc=subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                text=True,
                capture_output=True,
                timeout=self.timeout_sec,
            )
            return CommandResult(
                command=command,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_seconds=time.time()-start,
                timeout=False,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                command=command,
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                duration_seconds=time.time()-start,
                timeout=True,
            )