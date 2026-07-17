from dataclasses import dataclass

@dataclass
class ModelResponse:
    content:str
    input_tokens:int=0
    output_tokens:int=0
    estimated_cost:float=0.0


class FakeProvider:
    def __init__(self,model:str):
        self.model=model

    def complete(self,prompt:str)->ModelResponse:
        if "TASK: CREATE_REPAIR_PLAN" in prompt:
            content="""
{
"root_cause_hypothesis":"divide function does not handle zero explicity",
"files_to_inspect":[
"calculator.py",
"tests/test_calculator.py"
],
"files_to_modify":[
"calculator.py"
],
"patch_strategy":"check whether b is zero and rsise ValueError before division.",
"verification_commands":[
"pytest -q"
],
"risks":[
"The change should not affect normal division."]
}
""".strip()
            return ModelResponse(
                content=content,
                input_tokens=20,
                output_tokens=10,
                estimated_cost=0.0,
            )
        
        if"TASK: CREATE_JSON_PATCH" in prompt:
            content="""
{"operations":[{
"type":"replace_text",
"path":"calculator.py",
"old":"def divide(a,b):\\n    return a / b\\n",
"new":"def divide(a,b):\\n    if b == 0:\\n        raise ValueError('Division by zero')\\n    return a / b\\n"
}
],
"notes":"Add an explicit zero check before division." 
}""".strip()
            return ModelResponse(
                content=content,
                input_tokens=20,
                output_tokens=10,
                estimated_cost=0.0,
            )

        return ModelResponse(
            content="FakeProvider received the prompt successfully.",
                input_tokens=20,
                output_tokens=10,
                estimated_cost=0.0,
            )
    

def create_provider(
        provider_name:str,
        model:str,
)->FakeProvider:
    
    if provider_name=="fake":
        return FakeProvider(model=model)
    raise ValueError(
        f"Unsupported provider:{provider_name}"
    )
    

    
        


