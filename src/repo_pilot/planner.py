import json
from typing import Any

from repo_pilot.provider import Provider
from repo_pilot.cost import CostTracker

from repo_pilot.structured import complete_json_object
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
        
        plan=complete_json_object(
            provider=self.provider,
            prompt=prompt,
            call_name="repair_plan",
            output_description="repair plan",
            cost_tracker=cost_tracker,
        )
        return plan 





                    