from pathlib import Path


def test_openpandora_workflow_gates_fix_pr_on_step_outputs():
    workflow = Path(".github/workflows/openpandora.yml").read_text()

    assert "branches-ignore" not in workflow
    assert 'branches:\n      - "**"' in workflow
    assert 'echo "needs_fix=true" >> "$GITHUB_OUTPUT"' in workflow
    assert 'echo "needs_fix=false" >> "$GITHUB_OUTPUT"' in workflow
    assert "id: compare" in workflow
    assert "github.event.before" in workflow
    assert 'COMPARE_REF="${{ steps.compare.outputs.ref }}"' in workflow
    assert "id: loop_guard" in workflow
    assert "openpandora/fix-*)" in workflow
    assert "steps.loop_guard.outputs.can_create_fix_pr == 'true'" in workflow
    assert "steps.loop_guard.outputs.can_create_fix_pr == 'false'" in workflow
    assert "steps.qa.outputs.needs_fix == 'true'" in workflow
    assert "steps.project_commands.outputs.needs_fix == 'true'" in workflow
    assert "vars.OPENPANDORA_PROVIDER != ''" in workflow
    assert 'openpandora check --since "$COMPARE_REF"' in workflow
    assert 'openpandora fix-pr --since "$COMPARE_REF" --create' in workflow
