# RepoPilot

RepoPilot 是一个面向 **Python / pytest 项目**的单 Agent 代码自动修复系统。

系统根据 Bug 描述和测试失败信息，自动完成：

**仓库扫描 → 失败分析 → 相关代码定位 → 修复规划 → 结构化补丁生成 → 补丁审查 → 测试验证 → Retry / Rollback**

LLM 负责分析、规划和生成补丁，本地模块负责代码扫描、路径校验、补丁应用、测试执行和失败恢复。

## 核心能力

* Python AST 符号索引
* pytest 失败信息分析
* 相关代码上下文构建
* DeepSeek / OpenAI-compatible Provider
* FakeProvider 离线测试
* 结构化 JSON Patch
* Patch Review、Diff、Apply、Rollback
* 多轮修复与测试验证
* Trace、Token、Cost 统计
* Benchmark / Eval
* CLI、FastAPI
* Docker 容器化运行

## Workflow

```text
Issue + Repository
        ↓
Repository Scan
        ↓
Initial pytest
        ↓
Failure Analysis
        ↓
Context Build
        ↓
Plan
        ↓
Patch Generation
        ↓
Patch Review
        ↓
Patch Apply
        ↓
pytest Verification
        ↓
Success / Retry / Rollback
```

## 项目结构

```text
repopilot/
├── src/repo_pilot/
├── tests/
├── examples/
├── scripts/
├── Dockerfile
├── pyproject.toml
└── README.md
```

## 安装

```powershell
git clone https://github.com/lixiafeng/repopilot.git
cd repopilot

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -e .
```

## CLI

```powershell
python -m repo_pilot.cli `
    --repo examples/buggy_calculator `
    --issue "divide by zero should raise ValueError" `
    --provider fake `
    --model fake-model `
    --max-iterations 2
```

## 测试

```powershell
python -m pytest tests -q
```

## Benchmark

```powershell
python -m repo_pilot.eval_cli `
    --provider fake `
    --model fake-model `
    --case divide_by_zero `
    --max-iterations 2
```

评测指标包括：

* Pass Rate
* Average Iteration
* Total Duration
* Failure Reason
* Diff
* Test Output

## FastAPI

启动：

```powershell
python -m uvicorn repo_pilot.api:app `
    --host 127.0.0.1 `
    --port 8000
```

Swagger：

```text
http://127.0.0.1:8000/docs
```

接口：

```text
GET  /health
POST /repair
```

## Docker

构建：

```powershell
docker build -t repopilot:1.0 .
```

运行：

```powershell
docker run --rm `
    --name repopilot-api `
    -p 127.0.0.1:8000:8000 `
    repopilot:1.0
```

## 当前限制

* 主要面向 Python / pytest 项目
* 大型仓库的检索与上下文压缩仍可继续优化
* Benchmark 规模仍需继续扩充
* 当前 FastAPI 为同步接口
* 当前不包含后台 Job 系统

## 技术栈

**Python · pytest · AST · DeepSeek · FastAPI · Typer · Pydantic · Docker · Git**
