import json
from typing import Any

class ModelOutputError(ValueError):
    """
    模型输出无法解析成要求的 JSON 对象。
    """
    pass

def _strip_markdown_fence(text:str)->str:

    lines=text.strip().splitlines()
    if len(lines)<2:
        return text.strip()

    first_line=lines[0].strip()
    last_line=lines[-1].strip()

    if(
        first_line.startswith("'''")
        and last_line=="'''"
    ):
        return "\n".join(lines[1:-1]).strip()
    return text.strip()

def parse_json_object(
        text:str,
        source_name:str,
)->dict[str,Any]:
    
    if not isinstance(text,str):
        raise ModelOutputError(
            f"{source_name} output is not a string."
        )

    stripped =text.strip()
    if not stripped:
        raise ModelOutputError(
            f"{source_name} output is empty."
        )

    candidates=[
        stripped,
        _strip_markdown_fence(stripped),
    ]

    for candidate in candidates:
        try:
            data=json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if not isinstance(data,dict):
            raise ModelOutputError(
                f"{source_name} must be a JSON object."
            )

        return data
    
    decoder=json.JSONDecodeError()

    for index,character in enumerate(stripped):
        if character !="{":
            continue

        try:
            data,_=decoder.raw_decode(
                stripped[index:]
            )
        except json.JSONDecodeError:
            continue
        if isinstance(data,dict):
            return data

    preview=stripped[:500]

    raise ModelOutputError(
        f"{source_name} could not be parsed as JSON. "
        f"Output preview: {preview}"
    )


    