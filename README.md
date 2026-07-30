# RepoPilot

RepoPilot 是一个面向 Python 仓库的单 Agent 自动修复系统。它接收 Bug 描述和测试命令，扫描仓库、分析 pytest 失败、生成结构化补丁、审查并应用补丁，最后重新运行测试验证结果。

## 核心能力

- 仓库扫描与 Python AST 符号索引
- pytest 失败信息分析
- 面向相关文件的上下文构造
- OpenAI-compatible 模型 Provider
- FakeProvider 离线测试
- 结构化 JSON Patch 生成与修复
- 补丁安全审查、应用、Diff 和回滚
- 多轮修复与测试验证
- Trace、Token、成本和最终结果输出
- Benchmark/Eval 评测
- CLI 和同步 FastAPI 接口

## 工作流

```text
Issue + Repository
        ↓
Repository Scanner
        ↓
Initial pytest
        ↓
Failure Analyzer
        ↓
Context Builder
        ↓
Planner
        ↓
Patch Generator
        ↓
Patch Reviewer
        ↓
Patch Apply
        ↓
pytest Verification
        ↓
Success / Retry / Rollback
```

RepoPilot 当前使用单 Agent 编排。确定性模块负责扫描、命令执行、补丁应用和验证；模型负责规划和提出补丁。

## 项目结构

```text
repopilot/
├── src/repo_pilot/
│   ├── api.py
│   ├── benchmark.py
│   ├── benchmark_cases.py
│   ├── cli.py
│   ├── config.py
│   ├── context.py
│   ├── eval_cli.py
│   ├── failure.py
│   ├── patcher.py
│   ├── planner.py
│   ├── provider.py
│   ├── result.py
│   ├── reviewer.py
│   ├── scanner.py
│   ├── symbols.py
│   ├── verifier.py
│   └── workflow.py
├── examples/
├── tests/
├── runs/
├── eval_runs/
└── pyproject.toml
```

实际文件名以当前仓库为准。

## 环境要求

- Python 3.11+
- pytest
- FastAPI
- Uvicorn
- HTTPX
- Typer

## 安装

PowerShell：

```powershell
git clone <your-repository-url>
cd repopilot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

测试依赖未写入 `pyproject.toml` 时：

```powershell
python -m pip install pytest httpx fastapi "uvicorn[standard]"
```

## 运行 CLI

```powershell
python -m repo_pilot.cli `
    --repo examples/buggy_calculator `
    --issue "divide by zero should raise ValueError" `
    --provider fake `
    --model fake-model `
    --max-iterations 2
```

参数以 `python -m repo_pilot.cli --help` 的实际输出为准。

## 配置真实模型

不要把 API Key 写入源码。

```powershell
$env:DEEPSEEK_API_KEY = Read-Host "API Key"
```

运行时填写当前 Provider 实际支持的模型名称：

```powershell
python -m repo_pilot.eval_cli `
    --provider deepseek `
    --model "<your-model-name>" `
    --case divide_by_zero `
    --max-iterations 2
```

## 运行同步 API

设置安全目录：

```powershell
$env:REPOPILOT_ALLOWED_ROOT = "D:\repopilot-handwrite"
$env:REPOPILOT_TRACE_DIR = "D:\repopilot-handwrite\runs"
```

启动：

```powershell
python -m uvicorn repo_pilot.api:app `
    --host 127.0.0.1 `
    --port 8000
```

运行 Agent 时不要使用 `--reload`，因为 Agent 修改 Python 文件可能触发服务重启。

接口：

```text
GET  /health
POST /repair
```

Swagger：

```text
http://127.0.0.1:8000/docs
```

请求示例：

```json
{
  "repo": "D:/repopilot-handwrite/examples/buggy_calculator",
  "issue": "divide by zero should raise ValueError",
  "test_command": "python -m pytest -q",
  "provider": "fake",
  "model": "fake-model",
  "max_iterations": 2,
  "apply_patch": true,
  "command_timeout_sec": 120
}
```

响应中的轮数字段为 `iteration`，不是 `iterations`。

## 运行测试

```powershell
python -m compileall src -q
python -m pytest tests -q
```

不要把故意包含 Bug 的 `examples/` 目录作为普通项目测试整体执行。

## 运行 Benchmark

运行一个案例：

```powershell
python -m repo_pilot.eval_cli `
    --provider fake `
    --model fake-model `
    --case divide_by_zero `
    --max-iterations 2
```

运行全部案例：

```powershell
python -m repo_pilot.eval_cli `
    --provider deepseek `
    --model "<your-model-name>" `
    --max-iterations 2
```

Eval 会复制案例到临时目录，不直接修改原始示例仓库。

评测指标包括：

- 总案例数量
- 成功案例数量
- 失败案例数量
- Pass Rate
- Average Iteration
- Total Duration
- 单案例失败原因

## 运行产物

`runs/` 中通常保存：

```text
trace.json
cost.json
summary.json
final.diff
```

`eval_runs/` 中保存 Benchmark 汇总结果。

## 安全边界

- API 只能访问 `REPOPILOT_ALLOWED_ROOT` 下面的仓库。
- 不要向公网直接暴露当前同步 API。
- 测试命令会在目标仓库内执行，只接受可信输入。
- 补丁路径必须限制在仓库内部。
- 不要提交 API Key、运行记录或临时文件。
- 当前 API 使用同步执行，不包含持久化 Job 系统。

## 当前限制

- 主要面向 Python 与 pytest 仓库。
- 模型补丁质量受上下文和模型能力影响。
- 大型仓库需要更强的检索、上下文压缩和命令隔离。
- API 没有认证、限流和独立任务队列。
- Benchmark 规模仍需继续扩充。

## Benchmark 结果

在完成正式评测后更新此处：

```text
Provider: <provider>
Model: <model>
Cases: <number>
Pass rate: <percentage>
Average iteration: <number>
Date: <date>
```

不要只记录成功案例，也要保留失败原因。

## License

按项目实际许可证填写，例如 MIT。
