from openpandora.file_context import collect_file_context


def test_collect_file_context_reads_changed_text_files(tmp_path):
    source_path = tmp_path / "src" / "demo.py"
    source_path.parent.mkdir()
    source_path.write_text("print('hello')\n")

    contexts = collect_file_context(("src/demo.py",), tmp_path)

    assert len(contexts) == 1
    assert contexts[0].file_path == "src/demo.py"
    assert contexts[0].content == "print('hello')"


def test_collect_file_context_redacts_sensitive_lines(tmp_path):
    source_path = tmp_path / "config.py"
    source_path.write_text("OPENAI_API_KEY = 'secret'\nprint('safe')\n")

    contexts = collect_file_context(("config.py",), tmp_path)

    assert contexts[0].content == "[redacted sensitive-looking line]\nprint('safe')"


def test_collect_file_context_skips_missing_files(tmp_path):
    assert collect_file_context(("missing.py",), tmp_path) == ()
