import json
from typing import Any

from repo_pilot.provider import FakeProvider

class PatchPlanner:
    def __init__(self,provider:FakeProvider):
        self.provider=provider



    def plan(
            self,
            context_pack:dict[str,Any],
    )->dict[str,Any]:
        
        context_json=json.dumps(
            context_pack,
            ensure_ascii=False,
            indent=2,
        )

        prompt=f"""
TASK: CREATE_REPAIR_PLAN

You are planning a minimal bug fix for a python repository.

Return JSON  only.

Required fields:
-root_casue_hypothesis
-files_to_inspect
-files_to_modify
-patch_strategy
-verification_commands
-risks

Repository context:
{context_json}  ##插入prompt中
""".strip()
        
        response=self.provider.complete(prompt)

        try:
            plan_data=json.loads(response.content)  ##把 JSON 字符串转换成 Python 字典。 response.content 当前是 JSON 格式的字符串。
        
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Provider returned invalid JSON for repair plan."
                f"Original response:{response.content}"
            )from exc
        
        if not isinstance(plan_data,dict):
            raise ValueError(
                "Repair plan must be a JSON object."
            )
        return plan_data 





                    