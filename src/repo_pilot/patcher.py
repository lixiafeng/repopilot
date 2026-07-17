import json
from typing import Any

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


        




      
