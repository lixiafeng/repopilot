import re
from pathlib import Path
from typing import Any

from repo_pilot.tools import CommandResult


class FailureAnalyzer:
    """从测试命令输出中提取结构化失败信息。"""

    # 匹配 pytest 最后的失败摘要，例如：
    #
    # FAILED tests/test_counter.py::test_count_three_items - assert 2 == 3
    #
    # \S+ 表示连续匹配所有非空白字符，
    # 因此会提取完整的测试节点名称。
    FAILED_TEST_RE = re.compile(
        r"^FAILED\s+(?P<node_id>\S+)",
        re.MULTILINE,
    )

    # 匹配 pytest 输出中的文件和行号，例如：
    #
    # tests/test_counter.py:11
    # D:\project\tests\test_counter.py:11
    FILE_LINE_RE = re.compile(
        r"(?P<path>(?:[A-Za-z]:)?[^:\s]+\.py)"
        r":(?P<line>\d+)"
    )

    # 匹配 Python traceback 中的文件位置，例如：
    #
    # File "counter.py", line 3
    TRACEBACK_FILE_RE = re.compile(
        r'File\s+"(?P<path>[^"]+\.py)",'
        r"\s+line\s+(?P<line>\d+)"
    )

    # 匹配 pytest 展示的异常行，例如：
    #
    # E   ValueError: invalid value
    EXCEPTION_RE = re.compile(
        r"^E\s+"
        r"(?P<type>[A-Za-z_][\w.]*(?:Error|Exception))"
        r"(?::\s*(?P<message>.*))?$",
        re.MULTILINE,
    )

    # 匹配 pytest 输出末尾的异常类型，例如：
    #
    # tests/test_counter.py:11: AssertionError
    PYTEST_EXCEPTION_RE = re.compile(
        r"^[^\n]*\.py:\d+:\s*"
        r"(?P<type>[A-Za-z_][\w.]*(?:Error|Exception))"
        r"(?::\s*(?P<message>.*))?$",
        re.MULTILINE,
    )

    def analyze(
        self,
        result: CommandResult,
        repo: Path,
    ) -> tuple[
        list[dict[str, Any]],
        list[Path],
    ]:
        """分析测试命令执行结果。"""

        # 合并标准输出和标准错误。
        output = "\n".join(
            part
            for part in [
                result.stdout,
                result.stderr,
            ]
            if part
        )

        # 命令已经成功，不需要分析失败。
        if result.success:
            return [], []

        # 提取 pytest 失败测试名称。
        failed_tests = self._extract_failed_tests(
            output
        )

        # 提取异常类型和异常消息。
        exception_type, exception_message = (
            self._extract_exception(output)
        )

        # 提取相关文件和行号。
        locations = self._extract_locations(
            output=output,
            repo=repo,
        )

        # 当前一次命令失败对应一条结构化失败记录。
        failures: list[dict[str, Any]] = [
            {
                "exit_code": result.exit_code,
                "timeout": result.timeout,
                "failed_tests": failed_tests,
                "exception_type": exception_type,
                "exception_message": exception_message,
                "locations": locations,
                "summary": self._build_summary(
                    failed_tests=failed_tests,
                    exception_type=exception_type,
                    exception_message=exception_message,
                ),
            }
        ]

        # 根据失败位置构造候选文件。
        candidates = self._build_candidates(
            locations
        )

        return failures, candidates

    def _extract_failed_tests(
        self,
        output: str,
    ) -> list[str]:
        """提取 pytest 的失败测试节点名称。"""

        failed_tests: list[str] = []

        for match in self.FAILED_TEST_RE.finditer(
            output
        ):
            node_id = match.group("node_id")

            # 避免同一个测试被重复记录。
            if node_id not in failed_tests:
                failed_tests.append(node_id)

        return failed_tests

    def _extract_exception(
        self,
        output: str,
    ) -> tuple[str | None, str | None]:
        """提取异常类型和异常消息。"""

        # 优先匹配：
        #
        # E   ValueError: invalid value
        match = self.EXCEPTION_RE.search(output)

        # 普通 pytest 断言失败可能没有上面的格式，
        # 因此继续匹配：
        #
        # tests/test_counter.py:11: AssertionError
        if match is None:
            match = self.PYTEST_EXCEPTION_RE.search(
                output
            )

        if match is None:
            return None, None

        exception_type = match.group("type")
        exception_message = match.group(
            "message"
        )

        return (
            exception_type,
            exception_message,
        )

    def _extract_locations(
        self,
        output: str,
        repo: Path,
    ) -> list[dict[str, Any]]:
        """提取输出中出现的仓库文件位置。"""

        locations: list[dict[str, Any]] = []

        # 用集合避免重复记录相同文件和行号。
        seen: set[tuple[str, int]] = set()

        for match in self.FILE_LINE_RE.finditer(
            output
        ):
            self._append_location(
                locations=locations,
                seen=seen,
                raw_path=match.group("path"),
                line=int(
                    match.group("line")
                ),
                repo=repo,
            )

        for match in (
            self.TRACEBACK_FILE_RE.finditer(
                output
            )
        ):
            self._append_location(
                locations=locations,
                seen=seen,
                raw_path=match.group("path"),
                line=int(
                    match.group("line")
                ),
                repo=repo,
            )

        return locations

    def _append_location(
        self,
        locations: list[dict[str, Any]],
        seen: set[tuple[str, int]],
        raw_path: str,
        line: int,
        repo: Path,
    ) -> None:
        """验证并追加一个仓库内文件位置。"""

        # 把 Windows 反斜杠统一转换成正斜杠。
        normalized = raw_path.replace(
            "\\",
            "/",
        )

        path = Path(normalized)

        if path.is_absolute():
            try:
                # 绝对路径必须位于目标仓库内。
                relative_path = (
                    path.resolve()
                    .relative_to(
                        repo.resolve()
                    )
                )
            except ValueError:
                # 仓库外文件不作为候选文件。
                return
        else:
            relative_path = path

        # 检查文件在目标仓库中是否真实存在。
        target = repo / relative_path

        if not target.exists():
            return

        relative_text = (
            relative_path.as_posix()
        )

        key = (
            relative_text,
            line,
        )

        if key in seen:
            return

        seen.add(key)

        locations.append(
            {
                "file": relative_text,
                "line": line,
            }
        )

    def _build_summary(
        self,
        failed_tests: list[str],
        exception_type: str | None,
        exception_message: str | None,
    ) -> str:
        """构造供 ContextBuilder 和模型使用的失败摘要。"""

        parts: list[str] = []

        # 记录失败测试数量和名称。
        if failed_tests:
            failed_test_text = ", ".join(
                failed_tests
            )

            parts.append(
                f"{len(failed_tests)} test(s) failed: "
                f"{failed_test_text}"
            )

        # 默认没有解析到明确异常。
        # 这保证变量在所有分支中都已定义。
        exception_text = ""

        if exception_type:
            exception_text = exception_type

            if exception_message:
                exception_text += (
                    f": {exception_message}"
                )

        # 只有非空异常文本才加入摘要。
        if exception_text:
            parts.append(exception_text)

        # 什么都没有提取到时返回通用说明。
        if not parts:
            return (
                "Test command failed, but no "
                "structured failure was extracted."
            )

        return "; ".join(parts)

    def _build_candidates(
        self,
        locations: list[dict[str, Any]],
    ) -> list[Path]:
        """根据失败位置生成候选文件列表。"""

        candidates: list[Path] = []

        for location in locations:
            path = Path(
                location["file"]
            )

            if path not in candidates:
                candidates.append(path)

        return candidates