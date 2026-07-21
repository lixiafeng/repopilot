from pathlib import Path
from typing import Any

from repo_pilot.tools import CommandTools

class Verifier:
    def __init__(self,commands:CommandTools):
        self.commands=commands

    def verify(
            self,
            repo:Path,
            test_command:str,
    )->dict[str,Any]:
        

        compile_result=self.commands.run(
            command="python -m compileall . -q",
            cwd=repo,
        )

        if not compile_result.success:
            compile_output=(
                compile_result.stdout
                + compile_result.stderr
            )
            return {
                "success":False,
                "stage":"compile",
                "output":compile_output,
                "exit_code":compile_result.exit_code,
            }
        
        test_result=self.commands.run(
            command=test_command,
            cwd=repo,
        )
        test_output=(
            test_result.stdout
            +test_result.stderr
        )
        return {
            "success":test_result.success,
            "stage":"tests",
            "output":test_output,
            "exit_code":test_result.exit_code,
        }



