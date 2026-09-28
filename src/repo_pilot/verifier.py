from pathlib import Path
from typing import Any
import shlex

from repo_pilot.tools import CommandTools


class Verifier:
    def __init__(self, commands: CommandTools):
        self.commands = commands

    def verify(
        self,
        repo: Path,
        test_command: str,
        changed_files: list[str] | None = None,
    ) -> dict[str, Any]:

        changed_files = changed_files or []

        # 只检查本次 Patch 修改过的 Python 文件
        python_files = [
            file
            for file in changed_files
            if file.endswith(".py")
            and (repo / file).is_file()
        ]

        if python_files:
            compile_command = shlex.join(
                [
                    "python",
                    "-m",
                    "py_compile",
                    *python_files,
                ]
            )

            compile_result = self.commands.run(
                command=compile_command,
                cwd=repo,
            )

            if not compile_result.success:
                compile_output = (
                    compile_result.stdout
                    + compile_result.stderr
                )

                return {
                    "success": False,
                    "stage": "compile",
                    "output": compile_output,
                    "exit_code": compile_result.exit_code,
                }

        # 语法检查通过后，再运行真正的测试
        test_result = self.commands.run(
            command=test_command,
            cwd=repo,
        )

        test_output = (
            test_result.stdout
            + test_result.stderr
        )

        return {
            "success": test_result.success,
            "stage": "tests",
            "output": test_output,
            "exit_code": test_result.exit_code,
        }