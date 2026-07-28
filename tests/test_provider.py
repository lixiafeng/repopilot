import json

import httpx
import pytest

from repo_pilot.provider import (
    OpenAICompatibleProvider,
    ProviderError,
)


def create_success_response(
    request: httpx.Request,
    content: str = '{"ok": true}',
) -> httpx.Response:
    """
    构造一个符合 Chat Completions 格式的成功响应。

    request 参数来自 MockTransport，
    把它传给 Response 后，raise_for_status()
    才能获得完整的请求上下文。
    """

    return httpx.Response(
        # HTTP 200 表示请求成功。
        status_code=200,

        # 保存本次模拟请求。
        request=request,

        # 模拟模型 API 返回的 JSON。
        json={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 25,
            },
        },
    )


def test_complete_success() -> None:
    """
    HTTP 200 时应该正确返回 ModelResponse。
    """

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        """
        MockTransport 收到请求后会调用这个函数。
        """

        # Provider 应该使用 POST 请求。
        assert request.method == "POST"

        # 检查请求地址。
        assert (
            str(request.url)
            == "https://api.example.com/chat/completions"
        )

        # 检查 Authorization 请求头。
        assert (
            request.headers["Authorization"]
            == "Bearer test-key"
        )

        # request.content 是请求体的原始字节。
        # json.loads() 将它转换成 Python 字典。
        request_data = json.loads(
            request.content.decode("utf-8")
        )

        # 检查模型名称。
        assert (
            request_data["model"]
            == "test-model"
        )

        # 请求字段必须是 messages。
        assert "messages" in request_data

        # 第二条消息应该是用户传入的 prompt。
        assert (
            request_data["messages"][1]["content"]
            == "Return JSON."
        )

        return create_success_response(
            request=request,
            content='{"result": "success"}',
        )

    # 创建模拟传输层。
    transport = httpx.MockTransport(
        handler
    )

    # 将 MockTransport 注入 Provider。
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        transport=transport,
    )

    # 这里不会访问真实互联网。
    result = provider.complete(
        "Return JSON."
    )

    # 检查模型文本。
    assert (
        result.content
        == '{"result": "success"}'
    )

    # 检查 Token 解析。
    assert result.input_tokens == 100
    assert result.output_tokens == 25

    # 当前还没有配置模型价格。
    assert result.estimated_cost == 0.0

def test_retry_http_429_then_success() -> None:
    """
    前两次返回 HTTP 429，第三次成功时，
    Provider 应该自动重试并返回结果。
    """

    # 记录模拟服务器被调用了多少次。
    call_count = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal call_count

        # 每次请求都将次数加一。
        call_count += 1

        # 前两次请求模拟 API 限流。
        if call_count <= 2:
            return httpx.Response(
                status_code=429,
                request=request,
                json={
                    "error": {
                        "message": (
                            "Too many requests."
                        )
                    }
                },
            )

        # 第三次请求模拟服务恢复正常。
        return create_success_response(
            request=request,
            content='{"retried": true}',
        )

    transport = httpx.MockTransport(
        handler
    )

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",

        # 最多允许两次重试。
        #
        # 第一次请求 + 两次重试
        # 一共最多发送三次。
        max_retries=2,

        # 测试时将等待时间设为 0，
        # 避免单元测试真的等待 1 秒、2 秒。
        backoff_base_sec=0.0,

        transport=transport,
    )

    result = provider.complete(
        "Return JSON."
    )

    # 两次失败加一次成功，共调用三次。
    assert call_count == 3

    # 最终应该返回第三次的成功内容。
    assert result.content == '{"retried": true}'

def test_http_401_does_not_retry() -> None:
    """
    HTTP 401 通常表示 API Key 错误，
    重复发送相同请求没有意义，因此不应该重试。
    """

    call_count = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal call_count

        call_count += 1

        # 每次都返回认证失败。
        return httpx.Response(
            status_code=401,
            request=request,
            json={
                "error": {
                    "message": "Invalid API key."
                }
            },
        )

    transport = httpx.MockTransport(
        handler
    )

    provider = OpenAICompatibleProvider(
        api_key="wrong-key",
        base_url="https://api.example.com",
        model="test-model",

        # 即使配置了很多重试次数，
        # 401 也不属于可重试状态码。
        max_retries=3,

        backoff_base_sec=0.0,
        transport=transport,
    )

    # Provider 最终应该将 HTTPStatusError
    # 转换成项目统一的 ProviderError。
    with pytest.raises(
        ProviderError,
        match="HTTP 401",
    ):
        provider.complete(
            "Return JSON."
        )

    # 401 不应该重试，所以只调用一次。
    assert call_count == 1
def test_retry_timeout_then_success() -> None:
    """
    第一次请求超时，第二次成功时，
    Provider 应该自动重试。
    """

    call_count = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal call_count

        call_count += 1

        # 第一次请求模拟读取超时。
        if call_count == 1:
            raise httpx.ReadTimeout(
                "Simulated timeout.",
                request=request,
            )

        # 第二次请求模拟成功。
        return create_success_response(
            request=request,
            content='{"timeout_recovered": true}',
        )

    transport = httpx.MockTransport(
        handler
    )

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",

        # 允许一次重试。
        max_retries=1,

        # 测试时不真正等待。
        backoff_base_sec=0.0,

        transport=transport,
    )

    result = provider.complete(
        "Return JSON."
    )

    # 第一次超时，第二次成功。
    assert call_count == 2

    assert (
        result.content
        == '{"timeout_recovered": true}'
    )
