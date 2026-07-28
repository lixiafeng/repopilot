from repo_pilot.reviewer import PatchReviewer


def test_approve_safe_replace_text_patch() -> None:
    """正常的仓库内文本替换应该通过审查。"""

    reviewer = PatchReviewer()

    patch = {
        "operations": [
            {
                "type": "replace_text",
                "path": "calculator.py",
                "old": (
                    "def divide(a,b):\n"
                    "    return a / b\n"
                ),
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
        "notes": "Handle zero explicitly.",
    }

    result = reviewer.review(
        patch=patch,
    )

    # 合法补丁应该通过。
    assert result["approved"] is True

    # 合法补丁不应该产生审查问题。
    assert result["issues"] == []


def test_reject_parent_directory_path() -> None:
    """使用 ../ 访问仓库外部文件的补丁必须被拒绝。"""

    reviewer = PatchReviewer()

    patch = {
        "operations": [
            {
                "type": "replace_text",

                # 尝试修改仓库父目录中的文件。
                "path": "../secret.py",

                "old": "old",
                "new": "new",
            }
        ],
        "notes": "Unsafe path.",
    }

    result = reviewer.review(
        patch=patch,
    )

    assert result["approved"] is False

    # 至少应该记录一个拒绝原因。
    assert len(result["issues"]) >= 1


def test_reject_absolute_path() -> None:
    """绝对路径不能作为补丁目标。"""

    reviewer = PatchReviewer()

    patch = {
        "operations": [
            {
                "type": "replace_text",

                # Windows 风格的绝对路径。
                "path": "C:/Windows/system.ini",

                "old": "old",
                "new": "new",
            }
        ],
        "notes": "Unsafe absolute path.",
    }

    result = reviewer.review(
        patch=patch,
    )

    assert result["approved"] is False
    assert len(result["issues"]) >= 1


def test_reject_no_op_replacement() -> None:
    """old 与 new 完全相同的操作没有意义，应被拒绝。"""

    reviewer = PatchReviewer()

    patch = {
        "operations": [
            {
                "type": "replace_text",
                "path": "calculator.py",

                # old 和 new 完全相同。
                "old": "return a / b",
                "new": "return a / b",
            }
        ],
        "notes": "No change.",
    }

    result = reviewer.review(
        patch=patch,
    )

    assert result["approved"] is False