from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


class PatchReviewer:
    """
    在补丁真正应用之前进行基础安全检查。

    当前版本会检查：

    1. patch 中是否包含 operations。
    2. operation 是否是字典。
    3. operation 类型是否为 replace_text / write_file。
    4. path 是否为空。
    5. path 是否为 Windows / Linux 绝对路径。
    6. path 是否包含 ..，尝试跳出仓库目录。
    7. path 是否指向禁止修改的目录。
    8. replace_text 的 old / new 是否合法。
    9. write_file 的 content 是否合法。
    10. 修改内容中是否包含明显危险代码。
    """

    FORBIDDEN_PATH_PARTS = {
        ".git",
        ".venv",
        ".venv-1",
        "venv",
        "venv-1",
        "__pycache__",
    }

    DANGEROUS_PATTERNS = {
        "os.system(",
        "subprocess.popen(",
        "eval(",
        "exec(",
        "rm -rf",
    }

    def review(
        self,
        patch: dict[str, Any],
    ) -> dict[str, Any]:

        issues: list[str] = []

        operations = patch.get("operations", [])

        # patch 中没有任何修改操作。
        if not operations:
            issues.append(
                "Patch does not contain any operations."
            )

        for index, operation in enumerate(
            operations,
            start=1,
        ):
            # operation 必须是 JSON object，也就是 Python dict。
            if not isinstance(operation, dict):
                issues.append(
                    f"Operation {index} must be an object."
                )
                continue

            operation_type = operation.get("type")

            # RepoPilot 当前允许两种补丁操作。
            if operation_type not in {
                "replace_text",
                "write_file",
            }:
                issues.append(
                    f"Operation {index} has unsupported type: "
                    f"{operation_type}"
                )
                continue

            raw_path = operation.get("path")

            # path 必须存在，并且必须是字符串。
            if not isinstance(raw_path, str):
                issues.append(
                    f"Operation {index} path must be a string."
                )
                continue

            if not raw_path.strip():
                issues.append(
                    f"Operation {index} path cannot be empty."
                )
                continue

            # --------------------------------------------------
            # 1. 检查绝对路径
            # --------------------------------------------------
            #
            # 不能直接使用：
            #
            # Path(raw_path).is_absolute()
            #
            # 因为 Path 会根据当前操作系统解释路径。
            #
            # GitHub Actions 使用 Linux：
            #
            # C:/Windows/system.ini
            #
            # 在 Linux Path 看来不是绝对路径。
            #
            # 所以这里同时使用 Windows 和 POSIX 规则检查。
            # --------------------------------------------------

            if (
                PureWindowsPath(raw_path).is_absolute()
                or PurePosixPath(raw_path).is_absolute()
            ):
                issues.append(
                    f"Operation {index} uses an absolute path: "
                    f"{raw_path}"
                )

            # --------------------------------------------------
            # 2. 检查 ../
            # --------------------------------------------------
            #
            # Windows 可能使用：
            #
            # ..\\secret.py
            #
            # Linux / 模型通常可能生成：
            #
            # ../secret.py
            #
            # 所以先统一成 / 再分析。
            # --------------------------------------------------

            normalized_path = raw_path.replace("\\", "/")

            path_parts = PurePosixPath(
                normalized_path
            ).parts

            if ".." in path_parts:
                issues.append(
                    f"Operation {index} attempts to leave "
                    f"the repository: {raw_path}"
                )

            # --------------------------------------------------
            # 3. 检查禁止修改的目录
            # --------------------------------------------------

            for part in path_parts:
                if part.lower() in self.FORBIDDEN_PATH_PARTS:
                    issues.append(
                        f"Operation {index} targets forbidden "
                        f"directory '{part}': {raw_path}"
                    )

            # --------------------------------------------------
            # replace_text
            # --------------------------------------------------

            if operation_type == "replace_text":
                old_text = operation.get("old")
                new_text = operation.get("new")

                if not isinstance(old_text, str):
                    issues.append(
                        f"Operation {index} old text must be a string."
                    )

                if not isinstance(new_text, str):
                    issues.append(
                        f"Operation {index} new text must be a string."
                    )
                    continue

                # old == new 说明补丁实际上什么都没修改。
                if (
                    isinstance(old_text, str)
                    and old_text == new_text
                ):
                    issues.append(
                        f"Operation {index} does not change the file."
                    )

                content_to_check = new_text

            # --------------------------------------------------
            # write_file
            # --------------------------------------------------

            else:
                content = operation.get("content")

                if not isinstance(content, str):
                    issues.append(
                        f"Operation {index} content must be a string."
                    )
                    continue

                content_to_check = content

            # --------------------------------------------------
            # 4. 简单危险内容检查
            # --------------------------------------------------

            lower_content = content_to_check.lower()

            for pattern in self.DANGEROUS_PATTERNS:
                if pattern in lower_content:
                    issues.append(
                        f"Operation {index} contains dangerous "
                        f"pattern: {pattern}"
                    )

        # issues 为空才批准补丁。
        approved = not issues

        return {
            "approved": approved,
            "issues": issues,
        }