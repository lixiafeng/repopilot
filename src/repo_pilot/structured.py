from typing import Any
from repo_pilot.cost import CostTracker

from repo_pilot.json_utils import (
    ModelOutputError,
    parse_json_object,
)
from repo_pilot.provider import Provider

def complete_json_object(
        provider:Provider,
        prompt:str,
        call_name:str,
        output_description:str,
        cost_tracker:CostTracker|None=None,
)->dict[str,Any]:
    response=provider.complete(prompt)
    if cost_tracker is not None:
        cost_tracker.record(
            call_name=call_name,
            response=response,
        )

    try:
        return parse_json_object(
            text=response.content,
            source_name=output_description,
        )
    except ModelOutputError as first_error:
        repair_prompt=f"""
The following model output was intended to be:
{output_description}

Return only one valid JSON object.
Do not return Markdown fences.
Do not include explanations before or after the JSON.
Preserve the original meaning whenever possible.

INVALID MODEL OUTPUT:
{response.content[:20000]}
""".strip()
        repaired_response=provider.complete(
            repair_prompt
        )
        if cost_tracker is not None:
                cost_tracker.record(
                    call_name=(
                         f"{call_name} _json_repair"
                    ),
                    response=repaired_response,
                )
        
        try:
            return parse_json_object(
                text=repaired_response.content,
                source_name=(
                    f"repaired {output_description}"
                ),
            )

        except ModelOutputError as second_error:
            raise ModelOutputError(
                f"{output_description} parsing failed "
                "before and after JSON repair. "
                f"First error: {first_error}. "
                f"Second error: {second_error}."
            ) from second_error
