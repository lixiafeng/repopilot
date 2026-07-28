from repo_pilot.cost import CostTracker
from repo_pilot.provider import ModelResponse


def test_record_and_summarize_model_cost() -> None:
    """CostTracker 应该汇总多次模型调用。"""

    tracker = CostTracker()

    # 模拟第一次模型调用结果。
    plan_response = ModelResponse(
        content='{"plan": "test"}',
        input_tokens=100,
        output_tokens=20,
        estimated_cost=0.01,
    )

    # 模拟第二次模型调用结果。
    patch_response = ModelResponse(
        content='{"operations": []}',
        input_tokens=200,
        output_tokens=40,
        estimated_cost=0.02,
    )

    # 记录计划生成调用。
    tracker.record(
        call_name="repair_plan",
        response=plan_response,
    )

    # 记录补丁生成调用。
    tracker.record(
        call_name="json_patch",
        response=patch_response,
    )

    # 汇总所有调用。
    summary = tracker.summary()

    assert summary["calls"] == 2
    assert summary["input_tokens"] == 300
    assert summary["output_tokens"] == 60
    assert summary["estimated_cost"] == 0.03

    # records 中应该保留两次调用的明细。
    assert len(summary["records"]) == 2

    assert (
        summary["records"][0]["call_name"]
        == "repair_plan"
    )

    assert (
        summary["records"][1]["call_name"]
        == "json_patch"
    )


def test_empty_cost_tracker() -> None:
    """没有模型调用时，各项统计应该是零。"""

    tracker = CostTracker()

    summary = tracker.summary()

    assert summary["calls"] == 0
    assert summary["input_tokens"] == 0
    assert summary["output_tokens"] == 0
    assert summary["estimated_cost"] == 0
    assert summary["records"] == []