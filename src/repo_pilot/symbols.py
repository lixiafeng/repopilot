import ast
from pathlib import Path
from typing import Any

class SymbolIndexer:
    def build(self,
              repo:Path,
              python_files:list[str],
              )->list[dict[str,Any]]:
        symbols:list[dict[str,Any]]=[]

        for  rel_path in python_files:
            file_path=repo/rel_path
            if not file_path.exists() or not file_path.is_file():
                continue

            source=file_path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
            

            try:
                tree=ast.parse(source,filename=str(file_path))

            except SyntaxError:

                continue
            symbols.append(
                {
                    "type":"module",
                    "name":rel_path,
                    "file":rel_path,
                    "line":1,
                }
            )

            for node in ast.walk(tree):
                if isinstance(node,ast.FunctionDef):
                    symbols.append(
                        {
                        "type":"function",
                        "name":node.name,
                        "file":rel_path,
                        "line":node.lineno,
                        }

                    )
                elif isinstance(node,ast.AsyncFunctionDef):
                    symbols.append(
                        {
                         "type":"async_function",
                        "name":node.name,
                        "file":rel_path,
                        "line":node.lineno,

                        }
                    )
                elif isinstance(node,ast.ClassDef):
                    symbols.append(
                        {
                        "type":"class",
                        "name":node.name,
                        "file":rel_path,
                        "line":node.lineno,

                        }
                    )
                elif isinstance(node,ast.Import):
                    for alias in node.names:
                        symbols.append(
                            {
                                "type":"import",
                                "name":alias.name,
                                "file":rel_path,
                                "line":node.lineno,
                            }
                        )
                elif isinstance(node,ast.ImportFrom):
                    module_name=node.module or ""
                    for alias in node.names:
                        full_name=(
                            f"{module_name}.{alias.name}"
                            if module_name
                            else alias.name
                        )
                        symbols.append(
                            {
                                "type":"import_from",
                                "name":full_name,
                                "file":rel_path,
                                "line":node.lineno,
                            }
                        )
        return symbols


                           



                 
                
