from pathlib import Path

import pytest

from repo_pilot.patcher import Patcher
from repo_pilot.provider import FakeProvider


def create_patcher() -> Patcher:
    """创建测试使用的 Patcher。"""

    # apply() 本身不调用模型，
    # 但 Patcher 构造函数需要 Provider。
    provider = FakeProvider(
        model="fake-model",
    )

    return Patcher(
        provider=provider,
    )


def test_apply_replace_text(
    tmp_path: Path,
) -> None:
    """replace_text 应该精确修改目标文件并生成 diff。"""

    # tmp_path 是 pytest 自动创建的临时目录。
    # 每个测试都会得到独立目录。
    target_file = tmp_path / "calculator.py"

    original_content = (
        "def divide(a,b):\n"
        "    return a / b\n"
    )

    # 在临时目录中创建测试文件。
    target_file.write_text(
        original_content,
        encoding="utf-8",
    )

    patch = {
        "operations": [
            {
                "type": "replace_text",
                "path": "calculator.py",
                "old": original_content,
                "new": (
                    "def divide(a,b):\n"
                    "    if b == 0:\n"
                    "        raise ValueError("
                    "'Division by zero'"
                    ")\n"
                    "    return a / b\n"
                ),
            }
        ],
        "notes": "Handle division by zero.",
    }

    patcher = create_patcher()

    # 应用补丁。
    diff = patcher.apply(
        repo=tmp_path,
        patch=patch,
    )

    # 读取应用补丁后的内容。
    modified_content = target_file.read_text(
        encoding="utf-8",
    )

    assert "if b == 0:" in modified_content
    assert "raise ValueError" in modified_content

    # diff 中应该包含新增行。
    assert "+    if b == 0:" in diff

    # diff 中应该包含文件名。
    assert "calculator.py" in diff


def test_apply_rejects_missing_old_text(
    tmp_path: Path,
) -> None:
    """文件中不存在 old 文本时，补丁必须失败。"""

    target_file = tmp_path / "calculator.py"

    target_file.write_text(
        (
            "def divide(a,b):\n"
            "    return a / b\n"
        ),
        encoding="utf-8",
    )

    patch = {
        "operations": [
            {
                "type": "replace_text",
                "path": "calculator.py",

                # 这段内容在目标文件中不存在。
                "old": "return wrong_value\n",

                "new": "return correct_value\n",
            }
        ],
        "notes": "Invalid exact replacement.",
    }

    patcher = create_patcher()

    with pytest.raises(
        ValueError,
        match="Old text",
    ):
        patcher.apply(
            repo=tmp_path,
            patch=patch,
        )


def test_apply_rejects_ambiguous_old_text(
    tmp_path: Path,
) -> None:
    """old 出现多次时不能确定修改位置，应拒绝操作。"""

    target_file = tmp_path / "values.py"

    target_file.write_text(
        (
            "value = 1\n"
            "value = 1\n"
        ),
        encoding="utf-8",
    )

    patch = {
        "operations": [
            {
                "type": "replace_text",
                "path": "values.py",
                "old": "value = 1\n",
                "new": "value = 2\n",
            }
        ],
        "notes": "Ambiguous replacement.",
    }

    patcher = create_patcher()

    with pytest.raises(
        ValueError,
        match="appears",
    ):
        patcher.apply(
            repo=tmp_path,
            patch=patch,
        )

def test_restore_snapshot(
    tmp_path: Path,
) -> None:
    """验证失败后应该能够恢复补丁前的文件内容。"""

    target_file = tmp_path / "calculator.py"

    original_content = (
        "def divide(a,b):\n"
        "    return a / b\n"
    )

    target_file.write_text(
        original_content,
        encoding="utf-8",
    )

    patch = {
        "operations": [
            {
                "type": "replace_text",
                "path": "calculator.py",
                "old": original_content,
                "new": (
                    "def divide(a,b):\n"
                    "    return 100\n"
                ),
            }
        ],
        "notes": "Temporary test patch.",
    }

    patcher = create_patcher()

    # 应用补丁之前先创建快照。
    snapshot = patcher.create_snapshot(
        repo=tmp_path,
        patch=patch,
    )

    # 应用补丁。
    patcher.apply(
        repo=tmp_path,
        patch=patch,
    )

    # 确认文件确实发生了变化。
    assert (
        target_file.read_text(
            encoding="utf-8",
        )
        != original_content
    )

    # 模拟验证失败，恢复快照。
    patcher.restore_snapshot(
        repo=tmp_path,
        snapshot=snapshot,
    )

    # 文件应该恢复到补丁应用前的内容。
    assert (
        target_file.read_text(
            encoding="utf-8",
        )
        == original_content
    )