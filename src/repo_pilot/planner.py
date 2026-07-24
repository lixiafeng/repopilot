import json
from typing import Any

from repo_pilot.provider import Provider
from repo_pilot.cost import CostTracker

class PatchPlanner:
    def __init__(self,provider:Provider):
        self.provider=provider



    def plan(
            self,
            context_pack:dict[str,Any],
            cost_tracker:CostTracker|None=None,
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
        if cost_tracker is not None:
            cost_tracker.record(
                call_name="repair_plan",
                response=response,
            )

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





                    