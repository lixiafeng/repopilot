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
        self.max_chars_per_files = max_chars_per_files

    def build(
        self,
        state: AgentState,
    ) -> dict[str, Any]:
        candidate_files = self._select_candidate_files(
            state
        )

        snippets = self._read_snippets(
            repo=state.repo,
            candidate_files=candidate_files,
        )

        symbol_hits = self._select_symbol_hits(
            symbol_index=state.symbol_index,
            candidate_files=candidate_files,
        )

        repo_summary = {
            "project_type": state.repo_map.get(
                "project_type",
                "unknown",
            ),
            "file_count": len(
                state.repo_map.get(
                    "files",
                    [],
                )
            ),
            "python_files": state.repo_map.get(
                "python_files",
                [],
            ),
            "test_files": state.repo_map.get(
                "test_files",
                [],
            ),
            "config_files": state.repo_map.get(
                "config_files",
                [],
            ),
        }

        return {
            "issue": state.issue,
            "repo_summary": repo_summary,
            "failures": state.failures,
            "candidate_files": [
                path.as_posix()
                for path in candidate_files
            ],
            "snippets": snippets,
            "symbol_hits": symbol_hits,
            "previous_attempts": state.attempts,
        }

    def add_files(
        self,
        context_pack: dict[str, Any],
        state: AgentState,
        file_names: list[str],
    ) -> dict[str, Any]:
        """
        Refresh context after planning.

        Any file selected by the planner for modification must have its
        real source loaded before patch generation. This prevents the patch
        model from inventing an `old` string for a file it has not actually
        seen.

        Planner-selected modification targets have higher priority than
        ordinary candidate files when max_files is reached.
        """

        python_files = [
            self._normalize_path(file_name)
            for file_name in state.repo_map.get(
                "python_files",
                [],
            )
        ]

        python_file_names = {
            path.as_posix()
            for path in python_files
        }

        candidate_files = [
            self._normalize_path(file_name)
            for file_name in context_pack.get(
                "candidate_files",
                [],
            )
        ]

        planned_files: list[Path] = []
        planned_names: set[str] = set()

        for file_name in file_names:
            path = self._normalize_path(
                file_name
            )

            if path.suffix != ".py":
                continue

            normalized = path.as_posix()

            if normalized not in python_file_names:
                continue

            if normalized in planned_names:
                continue

            planned_files.append(path)
            planned_names.add(normalized)

        candidate_names = {
            path.as_posix()
            for path in candidate_files
        }

        for planned_file in planned_files:
            planned_name = (
                planned_file.as_posix()
            )

            if planned_name in candidate_names:
                continue

            if (
                self.max_files > 0
                and len(candidate_files)
                >= self.max_files
            ):
                remove_index = (
                    self._find_context_file_to_replace(
                        candidate_files=(
                            candidate_files
                        ),
                        protected_names=(
                            planned_names
                        ),
                    )
                )

                if remove_index is not None:
                    removed = candidate_files.pop(
                        remove_index
                    )
                    candidate_names.discard(
                        removed.as_posix()
                    )

            if (
                self.max_files <= 0
                or len(candidate_files)
                < self.max_files
            ):
                candidate_files.append(
                    planned_file
                )
                candidate_names.add(
                    planned_name
                )

        # Re-read snippets after the candidate set changes so planned
        # modification targets always use the exact current source.
        snippets = self._read_snippets(
            repo=state.repo,
            candidate_files=candidate_files,
        )

        symbol_hits = self._select_symbol_hits(
            symbol_index=state.symbol_index,
            candidate_files=candidate_files,
        )

        context_pack["candidate_files"] = [
            path.as_posix()
            for path in candidate_files
        ]
        context_pack["snippets"] = snippets
        context_pack["symbol_hits"] = (
            symbol_hits
        )

        return context_pack

    def _select_candidate_files(
        self,
        state: AgentState,
    ) -> list[Path]:
        selected: list[Path] = []
        selected_names: set[str] = set()

        python_files = [
            self._normalize_path(file_name)
            for file_name in state.repo_map.get(
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
            if (
                self.max_files > 0
                and len(selected)
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

            if (
                python_file_names
                and name not in python_file_names
            ):
                return False

            selected.append(path)
            selected_names.add(name)

            return True

        # 1. FailureAnalyzer candidates.
        for candidate in state.candidates:
            add_candidate(candidate)

            if (
                self.max_files > 0
                and len(selected)
                >= self.max_files
            ):
                break

        # 2. Static local-import expansion.
        index = 0

        while (
            index < len(selected)
            and (
                self.max_files <= 0
                or len(selected)
                < self.max_files
            )
        ):
            candidate = selected[index]

            imported_files = (
                self._find_local_import_files(
                    candidate_file=candidate,
                    symbol_index=(
                        state.symbol_index
                    ),
                    python_files=(
                        python_files
                    ),
                )
            )

            for imported_file in imported_files:
                add_candidate(imported_file)

                if (
                    self.max_files > 0
                    and len(selected)
                    >= self.max_files
                ):
                    break

            index += 1

        # 3. Retry feedback expansion.
        retry_files = (
            self._find_retry_feedback_files(
                state=state,
                python_files=python_files,
            )
        )

        for retry_file in retry_files:
            add_candidate(retry_file)

            if (
                self.max_files > 0
                and len(selected)
                >= self.max_files
            ):
                break

        # 4. Optional forced context files.
        forced_files = getattr(
            state,
            "forced_context_files",
            [],
        )

        for forced_file in forced_files:
            add_candidate(forced_file)

            if (
                self.max_files > 0
                and len(selected)
                >= self.max_files
            ):
                break

        # 5. Fallback when failure analysis found nothing.
        if not selected:
            for path in python_files:
                if self._is_test_file(path):
                    continue

                if path.name == "conftest.py":
                    continue

                add_candidate(path)

                if (
                    self.max_files > 0
                    and len(selected)
                    >= self.max_files
                ):
                    break

        return selected

    def _find_context_file_to_replace(
        self,
        candidate_files: list[Path],
        protected_names: set[str],
    ) -> int | None:
        """
        If context is full, prefer replacing a test file before a source
        file. Never evict a planner-selected modification target.
        """

        for index in range(
            len(candidate_files) - 1,
            -1,
            -1,
        ):
            path = candidate_files[index]
            name = path.as_posix()

            if name in protected_names:
                continue

            if self._is_test_file(path):
                return index

        for index in range(
            len(candidate_files) - 1,
            -1,
            -1,
        ):
            path = candidate_files[index]

            if (
                path.as_posix()
                not in protected_names
            ):
                return index

        return None

    def _find_local_import_files(
        self,
        candidate_file: Path,
        symbol_index: list[
            dict[str, Any]
        ],
        python_files: list[Path],
    ) -> list[Path]:
        candidate_name = (
            candidate_file.as_posix()
        )

        module_map = self._build_module_map(
            python_files
        )

        results: list[Path] = []
        seen: set[str] = set()

        for symbol in symbol_index:
            symbol_file = (
                self._normalize_text_path(
                    symbol.get(
                        "file",
                        "",
                    )
                )
            )

            if symbol_file != candidate_name:
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
                    module_map=module_map,
                )
            )

            if matched_file is None:
                continue

            matched_name = (
                matched_file.as_posix()
            )

            if matched_name == candidate_name:
                continue

            if matched_name in seen:
                continue

            seen.add(matched_name)
            results.append(
                matched_file
            )

        return results

    def _find_retry_feedback_files(
        self,
        state: AgentState,
        python_files: list[Path],
    ) -> list[Path]:
        """
        Extract repository Python files mentioned by previous verification
        output or patch/review errors.
        """

        if not state.attempts:
            return []

        results: list[Path] = []
        seen: set[str] = set()

        for attempt in state.attempts:
            texts: list[str] = []

            verification = attempt.get(
                "verification"
            )

            if isinstance(
                verification,
                dict,
            ):
                texts.append(
                    str(
                        verification.get(
                            "output",
                            "",
                        )
                    )
                )

            texts.append(
                str(
                    attempt.get(
                        "error",
                        "",
                    )
                )
            )

            texts.append(
                str(
                    attempt.get(
                        "issues",
                        "",
                    )
                )
            )

            combined = "\n".join(
                texts
            ).replace(
                "\\",
                "/",
            )

            for path in python_files:
                file_name = path.as_posix()

                if file_name not in combined:
                    continue

                if file_name in seen:
                    continue

                seen.add(file_name)
                results.append(path)

        return results

    def _build_module_map(
        self,
        python_files: list[Path],
    ) -> dict[str, Path]:
        module_map: dict[
            str,
            Path,
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
        module_map: dict[str, Path],
    ) -> Path | None:
        module_names = sorted(
            module_map.keys(),
            key=len,
            reverse=True,
        )

        for module_name in module_names:
            if (
                imported_name == module_name
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

        for relative_path in candidate_files:
            full_path = (
                repo / relative_path
            )

            if not full_path.exists():
                continue

            if not full_path.is_file():
                continue

            content = full_path.read_text(
                encoding="utf-8",
                errors="ignore",
            )

            limited_content = content[
                :self.max_chars_per_files
            ]

            snippets.append(
                {
                    "path": (
                        relative_path.as_posix()
                    ),
                    "content": limited_content,
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

            if symbol_file in candidate_names:
                symbol_hits.append(
                    symbol
                )

        return symbol_hits

    def _normalize_path(
        self,
        value: Path | str,
    ) -> Path:
        text = str(value).replace(
            "\\",
            "/",
        )

        return Path(text)

    def _normalize_text_path(
        self,
        value: Any,
    ) -> str:
        return str(value).replace(
            "\\",
            "/",
        )

    def _is_test_file(
        self,
        path: Path,
    ) -> bool:
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
