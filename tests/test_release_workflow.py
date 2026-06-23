from pathlib import Path


def test_release_workflow_publishes_zipapp_on_version_tags():
    workflow = Path(".github/workflows/release.yml").read_text()

    assert "tags:" in workflow
    assert '"v*"' in workflow
    assert "python scripts/build_release.py" in workflow
    assert "dist/openpandora.pyz --version" in workflow
    assert "gh release create" in workflow
    assert "contents: write" in workflow
