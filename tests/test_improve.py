from openpandora.findings import Finding
from openpandora.improve import build_improve_plan
from openpandora.review import ReviewResult


def test_build_improve_plan_says_no_files_changed():
    result = ReviewResult(
        provider="local",
        summary="OpenPandora found work to review before this branch is ready.",
        suggestions=("Add a focused test.",),
        findings=(Finding(title="Add a test", message="Missing test."),),
        command_results=(),
    )

    plan = build_improve_plan(result)

    assert "OpenPandora improve dry run" in plan
    assert "No files were changed." in plan
    assert "- Add a focused test." in plan
    assert "Use --apply" in plan


def test_build_improve_plan_handles_clean_review():
    result = ReviewResult(
        provider="local",
        summary="OpenPandora did not find anything to improve right now.",
        suggestions=(),
        findings=(),
        command_results=(),
    )

    plan = build_improve_plan(result)

    assert "- No improvement patch is needed right now." in plan
