import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from repo_pilot.config import RepoPilotConfig
from repo_pilot.result import WorkflowResult
from repo_pilot.workflow import BugfixWorkflow


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str


class RepairRequest(BaseModel):
    """客户端提交的仓库修复请求。"""

    # 要修复的本地仓库路径。
    #
    # JSON 中建议使用：
    # D:/repopilot-handwrite/examples/buggy_calculator
    repo: str = Field(
        min_length=1,
    )

    # 对 bug 的自然语言描述。
    issue: str = Field(
        min_length=1,
    )

    # 修复完成后执行的验证命令。
    test_command: str = Field(
        default="python -m pytest -q",
        min_length=1,
    )

    # 模型供应商。
    provider: str = Field(
        default="fake",
        min_length=1,
    )

    # 模型名称。
    model: str = Field(
        default="fake-model",
        min_length=1,
    )

    # Agent 最大修复轮次。
    max_iterations: int = Field(
        default=2,
        ge=1,
        le=10,
    )

    # 是否真正应用补丁。
    apply_patch: bool = True

    # 单条 shell 命令的最大执行时间。
    command_timeout_sec: int = Field(
        default=120,
        ge=1,
        le=3600,
    )


class RepairResponse(BaseModel):
    """一次修复任务的最终响应。"""

    success: bool
    message: str

    # 注意字段名是 iteration，没有 s。
    iteration: int

    diff: str
    test_output: str


app = FastAPI(
    title="RepoPilot API",
    description=(
        "HTTP API for the RepoPilot "
        "repository repair agent."
    ),
    version="0.1.0",
)


@app.get(
    "/health",
    response_model=HealthResponse,
)
def health() -> HealthResponse:
    """检查 HTTP 服务是否正常。"""

    return HealthResponse(
        status="ok",
    )


def resolve_repo_path(
    repo_text: str,
) -> Path:
    """
    校验并解析客户端提供的仓库路径。

    REPOPILOT_ALLOWED_ROOT 用于限制 API
    只能访问指定目录中的仓库。
    """

    # 默认只允许访问当前启动目录下面的仓库。
    allowed_root = Path(
        os.getenv(
            "REPOPILOT_ALLOWED_ROOT",
            ".",
        )
    ).expanduser().resolve()

    # 将请求中的路径转换成绝对路径。
    repo = Path(
        repo_text
    ).expanduser().resolve()

    # 仓库路径必须存在。
    if not repo.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Repository does not exist: "
                f"{repo}"
            ),
        )

    # 仓库路径必须是目录。
    if not repo.is_dir():
        raise HTTPException(
            status_code=400,
            detail=(
                "Repository path is not "
                f"a directory: {repo}"
            ),
        )

    try:
        # 验证 repo 是否位于允许访问的根目录中。
        repo.relative_to(
            allowed_root
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=403,
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
    """根据 API 请求创建一个新的 Workflow。"""

    # Trace 输出位置也通过环境变量控制。
    trace_dir = Path(
        os.getenv(
            "REPOPILOT_TRACE_DIR",
            "runs",
        )
    ).expanduser().resolve()

    # 确保 Trace 根目录存在。
    trace_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

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

    # 每次 API 请求创建一个新 Workflow。
    #
    # 不能把同一个 Workflow 对象全局复用，
    # 避免不同请求共享内部对象状态。
    return BugfixWorkflow(
        config=config,
    )


def to_repair_response(
    result: WorkflowResult,
) -> RepairResponse:
    """把 WorkflowResult 转换成 API 响应。"""

    return RepairResponse(
        success=result.success,
        message=result.message,
        iteration=result.iteration,
        diff=result.diff,
        test_output=result.test_output,
    )


@app.post(
    "/repair",
    response_model=RepairResponse,
)
def repair(
    request: RepairRequest,
) -> RepairResponse:
    """运行一次完整的仓库修复流程。"""

    # 在启动 Workflow 前校验仓库路径。
    repo = resolve_repo_path(
        request.repo
    )

    try:
        # 根据本次请求创建 Workflow。
        workflow = create_workflow(
            request
        )

        # 同步运行完整 Agent 流程。
        result = workflow.run(
            repo=repo,
            issue=request.issue,
            test_command=request.test_command,
        )

    except HTTPException:
        # FastAPI 的 HTTP 错误直接向上抛出。
        raise

    except Exception as exc:
        # 这里处理 Workflow 构造阶段的意外错误。
        #
        # Workflow.run() 内部已经有统一异常处理，
        # 正常运行错误通常会转换成 WorkflowResult。
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to start repair workflow: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc

    return to_repair_response(
        result
    )