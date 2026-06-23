from pathlib import Path


def test_openpandora_workflow_gates_fix_pr_on_step_outputs():
    workflow = Path(".github/workflows/openpandora.yml").read_text()

    assert 'echo "needs_fix=true" >> "$GITHUB_OUTPUT"' in workflow
    assert 'echo "needs_fix=false" >> "$GITHUB_OUTPUT"' in workflow
    assert "steps.qa.outputs.needs_fix == 'true'" in workflow
    assert "steps.project_commands.outputs.needs_fix == 'true'" in workflow
    assert "vars.OPENPANDORA_PROVIDER != ''" in workflow
    assert "openpandora fix-pr --since main --create" in workflow
