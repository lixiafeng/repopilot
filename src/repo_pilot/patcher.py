import json
from typing import Any
import difflib
from pathlib import Path

from repo_pilot.provider import FakeProvider

class Patcher:

    def __init__(self,provider:FakeProvider):
        self.provider=provider

    def propose_patch(
            self,
            context_pack:dict[str,Any],
            plan:dict[str,Any],     
    )->dict[str,Any]:
        
        context_json=json.dumps(
            context_pack,
            ensure_ascii=False,
            indent=2,
        )

        plan_json=json.dumps(
            plan,
            ensure_ascii=False,
            indent=2,
        )  

        prompt=f"""
TASK: CREATE_JSON_PATCH

Generate a minimal JSON patch for the repository.

Return JSON only. Do not return Markdown.

Allowed schema:{{
"operations":[
{{
"type":"replace_text",
"path":"relative/files.py",
"old":"exact_text",
"new":"new_text"
}}
],
"notes""explanation of the patch"
}}

Rules:
-Use repository-relative paths.
-The old text must exactly match the candidate file.
-Keep the modification minimal.
-Do not modify test files unless necessary.

Repair plan:
{plan_json}


Repository context:
{context_json}
""".strip()
        response=self.provider.complete(prompt)

        try:
            patch_data=json.loads(response.content)

        except  json.JSONDecodeError as exc:
            raise ValueError(
                "Provider returned invalid JSON patch.\n"
                f"Original response:\n{response.context}"
            ) from exc
        
        if not isinstance(patch_data,dict):
            raise ValueError(
                "Patch must be a JSON object."
            )
        
        if "operations" not in patch_data:
            raise ValueError(
                "Patch is missing the 'operations' filed."
            )
        operations=patch_data["operations"]

        if not isinstance(operations,list):
            raise ValueError(
                "Patch 'operations' must be a list."
            )
        
        for operation in operations:
            self._validate_operations(operation)

        return patch_data
    
    def _validate_operations(
            self,
            operation:Any
    )->None:
        
        if not isinstance(operation,dict):
            raise ValueError(
                "Each patch operation must be an object."
            )        
        
        operation_type=operation.get("type")

        if operation_type != "replace_text":
            raise ValueError(
                f"Unsupported patch operation: {operation_type}"
            )

        required_fields={
            "path",
            "old",
            "new",
        }

        for filed_name in required_fields:
            if filed_name not in operation:
                raise ValueError(
                    f"replace_text operation is missing"
                    f"the '{filed_name}'  filed."

                )
    
    def apply(
            self,
            repo:Path,
            patch:dict[str,Any]     
    )->str:
        
        all_diffs:list[str]=[]

        operations=patch.get("operations",[])

        for operation in operations:
            operation_type=operation["type"]

            if operation_type!="replace_text":
                raise ValueError(
                    f"Unsupported patch iperation:{operation_type}"
                )
            
            operation_diff=self._apply_replace_text(
                repo=repo,
                operation=operation,
            )
            all_diffs.append(operation_diff)

        return "\n".join(all_diffs)
    
    def _apply_replace_text(
            self,
            repo:Path,
            operation:dict[str,Any],
    )->str:
        
        relative_path=Path(operation["path"])

        target_path=repo/relative_path

        resolved_repo=repo.resolve()
        resolved_target=target_path.resolve()
        print(f"resolved_repo: {resolved_repo}")
        print(f"resolved_target: {resolved_target}")
        try:

            resolved_target.relative_to(resolved_repo)
        except ValueError as exc:
            raise ValueError(
                f"Patch target is outside repository:"
                f"{relative_path.as_posix()}"
            )
        
        if not resolved_target.is_file():
            raise ValueError(
                f"Path target is not a file:"
                f"{relative_path.as_posix()}"
            )
        
        before=resolved_target.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        old_text=operation["old"]
        new_text=operation["new"]

        occurrence_count=before.count(old_text)

        if occurrence_count==0:
            raise ValueError(
                f"Old text not found in file:"
                f"{relative_path.as_posix()}"
            )
        
        if occurrence_count>1:
            raise ValueError(
                f"Old text found multiple times in file:"
                f"{relative_path.as_posix()}"
                f"replacement is ambingopus."
            )
        
        after=before.replace(
            old_text,
            new_text,
            1,
        )

        resolved_target.write_text(
            after,
            encoding="utf-8",
        )

        diff_lines=difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{relative_path.as_posix()}",
            tofile=f"b/{relative_path.as_posix()}",

        )

        return "".join(diff_lines)






        




      
