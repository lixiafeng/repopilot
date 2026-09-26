from pathlib import Path
from typing import Any

from repo_pilot.state import AgentState


class ContextBuilder:

    def __init__(
        self,
        max_files: int = 5,
        max_chars_per_files: int = 4000,
    ) -> None:
        self.max_files = max_files
        self.max_chars_per_files = (
            max_chars_per_files
        )

    def build(
        self,
        state: AgentState,
    ) -> dict[str, Any]:

        candidate_files = (
            self._select_candidate_files(
                state
            )
        )

        snippets = self._read_snippets(
            repo=state.repo,
            candidate_files=candidate_files,
        )

        symbol_hits = (
            self._select_symbol_hits(
                symbol_index=(
                    state.symbol_index
                ),
                candidate_files=(
                    candidate_files
                ),
            )
        )

        repo_summary = {
            "project_type": (
                state.repo_map.get(
                    "project_type",
                    "unknown",
                )
            ),
            "file_count": len(
                state.repo_map.get(
                    "files",
                    [],
                )
            ),
            "python_files": (
                state.repo_map.get(
                    "python_files",
                    [],
                )
            ),
            "test_files": (
                state.repo_map.get(
                    "test_files",
                    [],
                )
            ),
            "config_files": (
                state.repo_map.get(
                    "config_files",
                    [],
                )
            ),
        }

        context_pack = {
            "issue": state.issue,
            "repo_summary": repo_summary,
            "failures": state.failures,
            "candidate_files": [
                path.as_posix()
                for path in candidate_files
            ],
            "snippets": snippets,
            "symbol_hits": symbol_hits,
            "previous_attempts": (
                state.attempts
            ),
        }

        return context_pack

    def _select_candidate_files(
        self,
        state: AgentState,
    ) -> list[Path]:
        """
        选择当前 Agent Context 中应该读取的文件。

        顺序：
        1. FailureAnalyzer 给出的 candidates
        2. candidates 中本地 import 的源码文件
        3. 如果一个 candidate 都没有，则退化为普通 Python 文件

        例如：

        test_age.py
            from age import is_adult

        会扩展为：

        [
            test_age.py,
            age.py,
        ]
        """

        selected: list[Path] = []
        selected_names: set[str] = set()

        python_files = [
            self._normalize_path(
                file_name
            )
            for file_name
            in state.repo_map.get(
                "python_files",
                [],
            )
        ]

        python_file_names = {
            path.as_posix()
            for path in python_files
        }

        def add_candidate(
            candidate: Path | str,
        ) -> bool:
            """
            尝试加入一个 candidate。

            返回 True 表示成功加入，
            False 表示被过滤或已经存在。
            """

            if (
                len(selected)
                >= self.max_files
            ):
                return False

            path = self._normalize_path(
                candidate
            )

            if path.suffix != ".py":
                return False

            name = path.as_posix()

            if name in selected_names:
                return False

            # 只加入仓库中真实存在的 Python 文件。
            if (
                python_file_names
                and name
                not in python_file_names
            ):
                return False

            selected.append(path)
            selected_names.add(name)

            return True

        # --------------------------------------------------
        # 1. FailureAnalyzer 原始 candidates
        # --------------------------------------------------
        for candidate in state.candidates:
            add_candidate(candidate)

            if (
                len(selected)
                >= self.max_files
            ):
                break

        # --------------------------------------------------
        # 2. 根据 import 关系扩展 candidate
        #
        # 例如：
        #
        # test_age.py
        #   from age import is_adult
        #
        # =>
        #
        # age.py
        # --------------------------------------------------
        index = 0

        while (
            index < len(selected)
            and len(selected)
            < self.max_files
        ):
            candidate = selected[index]

            imported_files = (
                self._find_local_import_files(
                    candidate_file=(
                        candidate
                    ),
                    symbol_index=(
                        state.symbol_index
                    ),
                    python_files=(
                        python_files
                    ),
                )
            )

            for imported_file in (
                imported_files
            ):
                add_candidate(
                    imported_file
                )

                if (
                    len(selected)
                    >= self.max_files
                ):
                    break

            index += 1

        # --------------------------------------------------
        # 3. 为以后 Retry 强制上下文预留接口
        #
        # 当前 AgentState 即使没有这个字段，
        # getattr 也会返回空列表。
        # --------------------------------------------------
        forced_files = getattr(
            state,
            "forced_context_files",
            [],
        )

        for forced_file in forced_files:
            add_candidate(forced_file)

            if (
                len(selected)
                >= self.max_files
            ):
                break

        # --------------------------------------------------
        # 4. 如果 FailureAnalyzer 完全没有 candidate，
        #    就退化为普通源码文件。
        # --------------------------------------------------
        if not selected:
            for path in python_files:

                if self._is_test_file(
                    path
                ):
                    continue

                if (
                    path.name
                    == "conftest.py"
                ):
                    continue

                add_candidate(path)

                if (
                    len(selected)
                    >= self.max_files
                ):
                    break

        return selected

    def _find_local_import_files(
        self,
        candidate_file: Path,
        symbol_index: list[
            dict[str, Any]
        ],
        python_files: list[Path],
    ) -> list[Path]:
        """
        从 candidate 文件里的 import symbol，
        找到仓库内对应的 Python 源文件。

        例：

        Symbol:
        {
            "type": "import_from",
            "name": "age.is_adult",
            "file": "test_age.py"
        }

        仓库：
        age.py

        返回：
        [Path("age.py")]
        """

        candidate_name = (
            candidate_file.as_posix()
        )

        module_map = (
            self._build_module_map(
                python_files
            )
        )

        results: list[Path] = []
        seen: set[str] = set()

        for symbol in symbol_index:

            symbol_file = self._normalize_text_path(
                symbol.get(
                    "file",
                    "",
                )
            )

            if (
                symbol_file
                != candidate_name
            ):
                continue

            symbol_type = str(
                symbol.get(
                    "type",
                    "",
                )
            )

            if symbol_type not in {
                "import",
                "import_from",
            }:
                continue

            imported_name = str(
                symbol.get(
                    "name",
                    "",
                )
            ).strip()

            if not imported_name:
                continue

            matched_file = (
                self._match_import_to_file(
                    imported_name=(
                        imported_name
                    ),
                    module_map=(
                        module_map
                    ),
                )
            )

            if matched_file is None:
                continue

            matched_name = (
                matched_file.as_posix()
            )

            if (
                matched_name
                == candidate_name
            ):
                continue

            if matched_name in seen:
                continue

            seen.add(matched_name)
            results.append(
                matched_file
            )

        return results

    def _build_module_map(
        self,
        python_files: list[Path],
    ) -> dict[str, Path]:
        """
        把 Python 文件映射为 import module name。

        age.py
        -> age

        app/services/user.py
        -> app.services.user

        app/__init__.py
        -> app
        """

        module_map: dict[
            str,
            Path
        ] = {}

        for path in python_files:

            if path.name == "__init__.py":
                module_parts = list(
                    path.parent.parts
                )

            else:
                module_parts = list(
                    path.with_suffix(
                        ""
                    ).parts
                )

            if not module_parts:
                continue

            module_name = ".".join(
                module_parts
            )

            if not module_name:
                continue

            module_map[
                module_name
            ] = path

        return module_map

    def _match_import_to_file(
        self,
        imported_name: str,
        module_map: dict[
            str,
            Path
        ],
    ) -> Path | None:
        """
        把 SymbolIndexer 产生的 import name
        映射回本地源码文件。

        age.is_adult
        可以匹配 module:
        age

        package.service.run
        会优先匹配最长 module：
        package.service
        而不是 package。
        """

        module_names = sorted(
            module_map.keys(),
            key=len,
            reverse=True,
        )

        for module_name in module_names:
            if (
                imported_name
                == module_name
                or imported_name.startswith(
                    module_name + "."
                )
            ):
                return module_map[
                    module_name
                ]

        return None

    def _read_snippets(
        self,
        repo: Path,
        candidate_files: list[Path],
    ) -> list[dict[str, Any]]:

        snippets: list[
            dict[str, Any]
        ] = []

        for relative_path in (
            candidate_files
        ):
            full_path = (
                repo / relative_path
            )

            if not full_path.exists():
                continue

            if not full_path.is_file():
                continue

            content = (
                full_path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
            )

            limited_content = (
                content[
                    :self.max_chars_per_files
                ]
            )

            snippets.append(
                {
                    "path": (
                        relative_path
                        .as_posix()
                    ),
                    "content": (
                        limited_content
                    ),
                    "truncated": (
                        len(content)
                        > self.max_chars_per_files
                    ),
                }
            )

        return snippets

    def _select_symbol_hits(
        self,
        symbol_index: list[
            dict[str, Any]
        ],
        candidate_files: list[Path],
    ) -> list[dict[str, Any]]:

        candidate_names = {
            path.as_posix()
            for path in candidate_files
        }

        symbol_hits: list[
            dict[str, Any]
        ] = []

        for symbol in symbol_index:
            symbol_file = (
                self._normalize_text_path(
                    symbol.get(
                        "file",
                        "",
                    )
                )
            )

            if (
                symbol_file
                in candidate_names
            ):
                symbol_hits.append(
                    symbol
                )

        return symbol_hits

    def _normalize_path(
        self,
        value: Path | str,
    ) -> Path:
        """
        将不同平台的路径分隔符统一成
        相对 Path。
        """

        text = str(value).replace(
            "\\",
            "/",
        )

        return Path(text)

    def _normalize_text_path(
        self,
        value: Any,
    ) -> str:
        return (
            str(value)
            .replace(
                "\\",
                "/",
            )
        )

    def _is_test_file(
        self,
        path: Path,
    ) -> bool:
        """
        判断是否为测试文件。

        同时处理：
        tests/test_x.py
        test_x.py
        x_test.py
        """

        if "tests" in path.parts:
            return True

        if path.name.startswith(
            "test_"
        ):
            return True

        if path.name.endswith(
            "_test.py"
        ):
            return True

        return False