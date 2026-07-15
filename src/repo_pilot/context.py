from pathlib import Path
from typing import Any

from repo_pilot.state import AgentState

class ContextBuilder:

    def __init__(
            self,
            max_files:int=5,
            max_chars_per_files=4000,
    ):
        self.max_files=max_files
        self.max_chars_per_files=max_chars_per_files

    def build(
            self,
            state:AgentState,
    )->dict[str:Any]:
        
        candidate_files=self._select_candidate_files(state)

        snippets=self._read_snippets(
            repo=state.repo,
            candidate_files=candidate_files,
        )

        symbol_hits=self._select_symbol_hits(
            symbol_index=state.symbol_index,
            candidate_files=candidate_files,
        )

        repo_summary={
            "project_type":state.repo_map.get(
                "project_type",
                "unknown",
            ),
             "file_count": len(
                state.repo_map.get("files", [])
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

        context_pack={
            "issue":state.issue,
            "repo_summary":repo_summary,
            "failures":state.failures,
            "candidate_files":[
                path.as_posix() 
                for path in candidate_files
            ],
            "snippets":snippets,
            "symbol_hits":symbol_hits,
            "previous_attempts":state.attempts,
        }
        return context_pack

    def _select_candidate_files(
            self,
            state:AgentState,
    )->list[Path]:
        
    
        selected:list[Path]=[]

        for candidate in state.candidates:
            if candidate.suffix !=".py":
                continue

            if candidate not in selected:
                selected.append(candidate)
            
            if len(selected) >=self.max_files:
                break
        
        if not selected:
            python_files=state.repo_map.get(
                "python_files",
                [],
            )
            for file_name in python_files:
                path=Path(file_name)

                if "tests" in path.parts:
                    continue
                if path.name=="conftest.py":
                    continue

                selected.append(path)

                if len(selected)>=self.max_files:
                    break
        
        return selected
    
    def _read_snippets(
        self,
        repo:Path,
        candidate_files:list[Path],
    )->list[dict[str,Any]]:
        
        snippets:list[dict[str,Any]]=[]

        for relative_path in candidate_files:
            full_path=repo/relative_path

            if not full_path.exists():
                continue
            if not full_path.is_file():
                continue

            content=full_path.read_text(
                encoding="utf-8",
                errors="ignore",
            )

            limited_content=content[:self.max_chars_per_files]

            snippets.append(
                {
                    "path":relative_path.as_posix(),
                    "content":limited_content,
                    "truncated":(
                        len(content)>self.max_chars_per_files
                    ),
                }    
            )
        return snippets
    
    def _select_symbol_hits(
            self,
            symbol_index:list[dict[str,Any]],
            candidate_files:list[Path],
        )->list[dict[str,Any]]:

        candidate_names={
            path.as_posix() for path in candidate_files
        }

        symbol_hits:list[dict[str,Any]]=[]

        for symbol in  symbol_index:
            symbol_file=symbol.get("file")

            print(symbol_file)

            if symbol_file  in candidate_names:
                symbol_hits.append(symbol)
        return symbol_hits





        



                



        


        
