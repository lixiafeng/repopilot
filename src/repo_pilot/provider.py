from dataclasses import dataclass
import os
from typing import Protocol
import httpx

@dataclass
class ModelResponse:
    content:str
    input_tokens:int=0
    output_tokens:int=0
    estimated_cost:float=0.0

class Provider(Protocol):
    def complete(
            self,
            prompt:str,
    )->ModelResponse:
        ...
        

class ProviderError(RuntimeError):
    pass



class FakeProvider:
    def __init__(self,model:str="fake-model"):
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

class OpenAICompatibleProvider:
    def __init__(
            self,
            api_key:str,
            base_url:str,
            model:str,
            timeout_sec:float=120.0,
    )->None:
        if not api_key.strip():
            raise ValueError(
                "Provider API key must not be empty. "
            )
        if not base_url.strip():
            raise ValueError(
                "Provider bse URL must be not empty."
            )

        if not model.strip():
            raise ValueError(
                "Provider model must be not empty."
            )

        self.api_key=api_key
        self.base_url=base_url.rstrip("/")
        self.model=model
        self.timeout_sec=timeout_sec

    def complete(
            self,
            prompt:str,         
    )->ModelResponse:

        url=(
            f"{self.base_url}/chat/completions"
        )

        headers={
            "Authorization":(
                f"Bearer {self.api_key}"
            ),
            "Content-Type":"application/json",
        }
        payload={
            "model":self.model,
            "messages":[
                {
                    "role":"system",
                    "content":(
                        "you are a precise repository"
                        "bug-fixing assistant."
                        "Follow the requested JSON schema"
                        "and return only valid JSON."
                    ),

                },
                {
                    "role":"user",
                    "content":prompt,
                },
            ],
            "temperature":0,
        }
        try:
            with httpx.Client(
                timeout=self.timeout_sec,
            )as client:
                response=client.post(
                    url=url,
                    headers=headers,
                    json=payload,
                )

                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "Model request timed out after"
                f"{self.timeout_sec}seconds."
            )from exc

        except httpx.HTTPStatusError as exc:
            status_code=(
                exc.response.status_code
            )
            response_text=(
                exc.response.text[:1000]
            )
            raise ProviderError(
                "Model API returned HTTP"
                f"{status_code}:{response_text}"
            )from exc
        
        except httpx.RequestError as exc:
            raise ProviderError (
                f"Model request failed:{exc}"
            )from exc

        try:
            data=response.json()
        except ValueError as exc:
            raise ProviderError(
                "Model API did not return valid JSON."
            )from exc

        try:
            content=(
                data["choices"][0]
                ["message"]["content"]
            )
        except(
            KeyError,
            IndexError,
            TypeError
        ) as exc:
            raise ProviderError(
                "Model API response does not contain"
                "choices[0].message.content."
            )from exc

        if not isinstance(content,str):
            raise ProviderError(
                "Model response content is  not a string."
            )

        if not content.strip():
            raise ProviderError(
                "Model returned empty content."
            )

        usage= data.get("usage") or {}

        input_tokens=int(
            usage.get(
                "prompt_tokens",
                usage.get("input_tokens",0),
            )
            or 0
        )

        output_tokens=int(
            usage.get(
                "completion_tokens",
                usage.get("output_tokens",0),
            )
            or 0

        )
        return ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=0.0,
        )
def _require_env(name:str)->str:
    value=os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(
            f"Required environment variable"
            f"{name}is not set."
        )
    return value.strip()
    

def create_provider(
        provider_name:str,
        model:str,
)->Provider:
    normalized_name=(
        provider_name.strip().lower()
    )
    
    if normalized_name=="fake":
        return FakeProvider(model=model)

    if normalized_name=="openai":
        return OpenAICompatibleProvider(
            api_key=_require_env(
                "OPENAI_API_KEY"
            ),
            base_url=os.gentenv(
                "OPENAI_BASE_URL",
                "https://api.openai.com/v1",
            ),
            model=model,
        )
    if normalized_name=="deepseek":
            return OpenAICompatibleProvider(
                api_key=_require_env(
                    "DEEPSEEK_API_KEY"
                ),
                base_url=os.getenv(
                    "DEEPSEEK_BASE_URL",
                    "https://api.deepseek.com",
                ),
                model=model,
            )
    if normalized_name in {
        "openai-compatible",
        "compatible",
    }:
        return OpenAICompatibleProvider(
            api_key=_require_env(
                "REPOPILOT_API_KEY"
            ),
            base_url=_require_env(
                "REPOPILOT_BASE_URL"
            ),
            model=model,
        )
    
    raise ValueError(
        f"Unsupported provider:{provider_name}"
        "Supported providers: "
        "fake, openai, deepseek, "
        "openai-compatible."
    )
    

    
        


