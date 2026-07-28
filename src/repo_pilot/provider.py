from dataclasses import dataclass
import os
from typing import Protocol
import httpx
import time

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
    RETRYABLE_STATUS_CODES={
        408,
        429,
        500,
        502,
        503,
        504,
    }
    def __init__(
            self,
            api_key:str,
            base_url:str,
            model:str,
            timeout_sec:float=120.0,
            max_retries:int=2, #最多发送3次请求
            backoff_base_sec:float=1.0,
            transport:httpx.BaseTransport|None=None,
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
        if max_retries<0:
            raise ValueError(
                "max_retries must be at least 0."
            )
        if backoff_base_sec<0:
            raise ValueError(
                "backoff_base_sec must be not be negative"
            )
        self.max_retries=max_retries
        self.backoff_base_sec=backoff_base_sec
        self.transport = transport

    def complete(
            self,
            prompt:str,         
    )->ModelResponse:
        last_error:Exception |None=None
        with httpx.Client(
            timeout=self.timeout_sec,
            transport=self.transport,
        )as client:
            for attempt in range(self.max_retries+1):
                try:
                    return self._complete_once(
                        client=client,
                        prompt=prompt,
                    )
                except httpx.HTTPStatusError as exc:
                    last_error=exc

                    status_code=(
                        exc.response.status_code
                    )
                    retryable=(
                        status_code
                        in self.RETRYABLE_STATUS_CODES
                    )
                    if (
                        not retryable
                        or attempt>=self.max_retries
                    ):
                        break

                    self._wait_before_retry(
                        attempt=attempt,
                        reason=(
                            f"HTTP{status_code}"
                        )
                    )
                except httpx.TimeoutException as exc:
                    last_error=exc

                    if attempt>=self.max_retries:
                        break

                    self._wait_before_retry(
                        attempt=attempt,
                        reason="request timeout",
                    )
                except httpx.RequestError as exc:
                    last_error=exc
                    
                    if attempt>=self.max_retries:
                        break

                    self._wait_before_retrey(
                        attempt=attempt,
                        reason=str(exc),
                    )

        if isinstance(
            last_error,
            httpx.HTTPStatusError ,
        ):
            status_code = (
                last_error.response.status_code
            )

            response_text = (
                last_error.response.text[:1000]
            )

            raise ProviderError(
                "Model API returned HTTP "
                f"{status_code}: {response_text}"
            ) from last_error
        if isinstance(
            last_error,
            httpx.TimeoutException,
        ):
            raise ProviderError(
                "Model request timed out after "
                f"{self.timeout_sec} seconds."
            ) from last_error

        if isinstance(
            last_error,
            httpx.RequestError,
        ):
            raise ProviderError(
                f"Model request failed: {last_error}"
            ) from last_error

        raise ProviderError(
            "Model request failed for an unknown reason."
        )
    def _complete_once(
            self,
            client:httpx.Client,
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
        
        response=client.post(
            url=url,
            headers=headers,
            json=payload,
        )

        response.raise_for_status()
        try:
            data=response.json()

        except ValueError as exc:
            raise ProviderError(
                "Model API did not return valid JSON."
            )from exc

        if not isinstance(data,dict):
            raise ProviderError(
                "Model API response must be a JSON object."
            )

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

    def _wait_before_retry(
            self,
            attempt:int,
            reason:str,
    )->None:
        delay=(
            self.backoff_base_sec*(2**attempt)
        )
        print(
        "Model request failed temporarily. "
        f"Reason: {reason}. "
        f"Retrying in {delay:.1f} seconds." 
    )

        time.sleep(delay)


        
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
    

    
        


