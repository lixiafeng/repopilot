from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from fastapi import (
    FastAPI,
    HTTPException,
    status,
)
from pydantic import BaseModel, Field

from repo_pilot.config import RepoPilotConfig
from repo_pilot.result import WorkflowResult
from repo_pilot.workflow import BugfixWorkflow


# ============================================================
# 请求和响应模型
# ============================================================


class HealthResponse(BaseModel):
    """健康检查接口的响应。"""

    status: str


class RepairRequest(BaseModel):
    """客户端提交的一次仓库修复请求。"""

    # 需要修复的本地仓库路径。
    #
    # Windows 的 JSON 请求中建议使用正斜杠：
    # D:/repopilot-handwrite/examples/buggy_calculator
    repo: str = Field(
        min_length=1,
    )

    # 对 Bug 的自然语言描述。
    issue: str = Field(
        min_length=1,
    )

    # 修复前和修复后执行的测试命令。
    test_command: str = Field(
        default="python -m pytest -q",
        min_length=1,
    )

    # 模型供应商，例如：
    # fake、deepseek、openai。
    provider: str = Field(
        default="fake",
        min_length=1,
    )

    # 模型名称。
    model: str = Field(
        default="fake-model",
        min_length=1,
    )

    # Agent 最多执行多少轮修复。
    max_iterations: int = Field(
        default=2,
        ge=1,
        le=10,
    )

    # 是否真正把补丁写入仓库。
    apply_patch: bool = True

    # 一条命令的最大执行时间。
    command_timeout_sec: int = Field(
        default=120,
        ge=1,
        le=3600,
    )


class RepairResponse(BaseModel):
    """一次仓库修复的最终响应。"""

    # 是否修复成功。
    success: bool

    # Workflow 返回的结果说明。
    message: str

    # 最终执行到第几轮。
    #
    # 注意字段名是 iteration，没有 s。
    iteration: int

    # Agent 生成并应用的代码差异。
    diff: str

    # 最后一次测试命令的输出。
    test_output: str


# ============================================================
# FastAPI 应用
# ============================================================


app = FastAPI(
    title="RepoPilot API",
    description=(
        "HTTP API for the RepoPilot "
        "repository repair agent."
    ),
    version="0.1.0",
)


# 当前使用单 Agent 模式。
#
# 同一时间只允许一个 /repair 请求真正运行 Workflow。
# 第二个请求会等待第一个请求执行结束。
#
# 这不是 Job 系统，只是防止两个请求同时修改仓库。
repair_lock = Lock()


# ============================================================
# 辅助函数
# ============================================================


def resolve_repo_path(
    repo_text: str,
) -> Path:
    """
    解析并校验客户端传入的仓库路径。

    API 只能访问 REPOPILOT_ALLOWED_ROOT
    指定目录下面的仓库。
    """

    # 从环境变量读取允许访问的根目录。
    #
    # 没有设置时，默认使用 API 启动时的当前目录。
    allowed_root = Path(
        os.getenv(
            "REPOPILOT_ALLOWED_ROOT",
            ".",
        )
    ).expanduser().resolve()

    # 把客户端传入的字符串转换成绝对路径。
    repo = Path(
        repo_text
    ).expanduser().resolve()

    # 仓库路径必须存在。
    if not repo.exists():
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "Repository does not exist: "
                f"{repo}"
            ),
        )

    # 仓库路径必须是目录，不能是普通文件。
    if not repo.is_dir():
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "Repository path is not "
                f"a directory: {repo}"
            ),
        )

    try:
        # 检查 repo 是否位于 allowed_root 下面。
        #
        # 例如：
        #
        # allowed_root:
        # D:/repopilot-handwrite
        #
        # repo:
        # D:/repopilot-handwrite/examples/buggy_calculator
        #
        # 这是合法路径。
        repo.relative_to(
            allowed_root
        )

    except ValueError as exc:
        # repo 不在允许目录中时返回 HTTP 403。
        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail=(
                "Repository is outside "
                "REPOPILOT_ALLOWED_ROOT. "
                f"Allowed root: {allowed_root}"
            ),
        ) from exc

    return repo


def create_workflow(
    request: RepairRequest,
) -> BugfixWorkflow:
    """根据 API 请求创建一个新的单 Agent Workflow。"""

    # 从环境变量读取运行记录目录。
    trace_dir = Path(
        os.getenv(
            "REPOPILOT_TRACE_DIR",
            "runs",
        )
    ).expanduser().resolve()

    # 保证 Trace 目录存在。
    trace_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 将 API 请求转换为 RepoPilotConfig。
    config = RepoPilotConfig(
        provider=request.provider,
        model=request.model,
        max_iterations=request.max_iterations,
        apply_patch=request.apply_patch,
        command_timeout_sec=(
            request.command_timeout_sec
        ),
        trace_dir=trace_dir,
    )

    # 每个请求创建一个新的 Workflow。
    return BugfixWorkflow(
        config=config,
    )


def to_repair_response(
    result: WorkflowResult,
) -> RepairResponse:
    """把内部 WorkflowResult 转换成 HTTP 响应。"""

    return RepairResponse(
        success=result.success,
        message=result.message,
        iteration=result.iteration,

        # 某些失败结果可能没有 diff，
        # API 统一返回空字符串。
        diff=result.diff or "",

        # 某些构造阶段错误可能没有测试输出，
        # API 统一返回空字符串。
        test_output=(
            result.test_output or ""
        ),
    )


# ============================================================
# API 路由
# ============================================================


@app.get(
    "/health",
    response_model=HealthResponse,
)
def health() -> HealthResponse:
    """
    检查 RepoPilot API 是否能够正常响应。

    这个接口不调用模型，也不运行 Workflow。
    """

    return HealthResponse(
        status="ok",
    )


@app.post(
    "/repair",
    response_model=RepairResponse,
)
def repair(
    request: RepairRequest,
) -> RepairResponse:
    """
    同步运行一次仓库修复任务。

    客户端会一直等待，直到 Workflow 执行结束。
    """

    # 在创建 Workflow 前校验仓库路径。
    repo = resolve_repo_path(
        request.repo
    )

    try:
        # 单 Agent 模式：
        # 一次只运行一个修复 Workflow。
        with repair_lock:
            # 根据当前请求创建 Workflow。
            workflow = create_workflow(
                request
            )

            # 进入真正的 Agent 修复流程。
            result = workflow.run(
                repo=repo,
                issue=request.issue,
                test_command=(
                    request.test_command
                ),
            )

    except HTTPException:
        # 已经是明确的 HTTP 错误时，
        # 保留原来的状态码和错误信息。
        raise

    except Exception as exc:
        # 处理 Workflow 创建阶段等外层异常。
        #
        # workflow.run() 内部已经有统一异常处理，
        # 所以这里主要处理配置和初始化错误。
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Failed to start repair workflow: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc

    # 把 WorkflowResult 转换成 JSON 响应。
    return to_repair_response(
        result
    )