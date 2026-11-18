from __future__ import annotations

import pytest
import yomiyasu_en_lint as lint
import yomiyasu_en_text as tx


def rules(text: str, doc_type: str | None = None, words: tx.Words | None = None) -> list[str]:
    return [f.rule for f in lint.lint(text, doc_type, None, words).findings]


@pytest.mark.parametrize(("text", "rule"), [
    ("We delve into the details.\n", "ai_vocabulary"),
    ("In today's fast-paced world, teams ship.\n", "stock_phrase"),
    ("I hope this helps!\n", "chat_residue"),
    ("Feel free to reach out.\n", "chat_residue"),
    ("We did it in order to save time.\n", "wordy_phrase"),
    ("This will unlock new value.\n", "metaphor_verb"),
    ("It is truly great.\n", "intensifier"),
    ("Let's circle back next week.\n", "jargon"),
    ("This may potentially fail.\n", "hedge_stack"),
    ("The fix — a small one — worked.\n", "em_dash"),
    ("The fix -- a small one -- worked.\n", "em_dash"),
    ("Ship it 🚀.\n", "emoji"),
    ("## Steps:\n", "heading_colon"),
    ("- **Speed**: fast.\n- **Cost**: low.\n", "bold_label_list"),
    ("A **b** c **d** e **f** g.\n", "heavy_bold"),
    ("**Note:**This fails.\n", "bold_unrendered"),
    ("It is **bold **here.\n", "bold_unrendered"),
    ("It's not a bug, it's a feature request.\n", "negative_contrast"),
    ("It isn't a tool. It's a philosophy.\n", "negative_contrast"),
    ("The code tells a story.\n", "personification"),
    ("We shipped. The result? Fewer errors.\n", "self_answered_question"),
    ("Fast. Simple. Reliable.\n", "fragment_run"),
    ("Here are three key reasons to switch.\n", "count_announcement"),
    ("Done!\n", "exclamation"),
    ("We ran it. We fixed it. We shipped it.\n", "sentence_start_repeat"),
    ("Consider this:\n\nAnother paragraph.\n", "decorative_colon"),
])
def test_rule_fires(text: str, rule: str) -> None:
    assert rule in rules(text)


def test_closing_summary_heading() -> None:
    text = "# Title\n\nBody.\n\nMore.\n\n## Conclusion\n\nIt works.\n"
    assert "closing_summary" in rules(text)


def test_excess_list() -> None:
    text = "Intro.\n\n" + "".join(f"- item {i}\n" for i in range(9))
    assert "excess_list" in rules(text)


@pytest.mark.parametrize("text", [
    "The range is 2019–2021.\n",
    "Run `delve --truly` now.\n",
    "See https://example.com/unlock-the-power.\n",
    "> We delve into the realm of quotes.\n",
    "```\nIn today's fast-paced world\n```\n",
    "This is **bold** text.\n",
    "The sensor detects a fault.\n",
    "- **Deadline**: May 9\n",
    "The following steps apply:\n\n- one\n- two\n",
])
def test_no_false_positive(text: str) -> None:
    assert rules(text) == []


def test_doc_type_exemptions() -> None:
    text = "Fast. Simple. Reliable!\n"
    assert "fragment_run" in rules(text)
    result = lint.lint(text, "promo")
    assert "fragment_run" not in [f.rule for f in result.findings]
    assert "fragment_run" in [f.rule for f in result.exempted]


def test_mail_exempts_courtesies_only() -> None:
    text = "Let me know if you have any questions. I hope this helps.\n"
    got = rules(text, "mail")
    assert got.count("chat_residue") == 1


def test_project_words(tmp_path) -> None:  # noqa: ANN001
    (tmp_path / "flag.txt").write_text("frobnicate\tprocess\n", encoding="utf-8")
    (tmp_path / "allow.txt").write_text("robust\n", encoding="utf-8")
    words = tx.load_words(str(tmp_path), False)
    result = lint.lint("We frobnicate robust data.\n", None, None, words)
    got = [(f.rule, f.message) for f in result.findings]
    assert any(r == "project_term" and "→ process" in m for r, m in got)
    assert not any(r == "ai_vocabulary" for r, _ in got)


def test_cli_exit_codes(tmp_path, capsys) -> None:  # noqa: ANN001
    path = tmp_path / "a.md"
    path.write_text("Ship it 🚀.\n", encoding="utf-8")
    assert lint.main([str(path), "--no-words"]) == 0
    assert lint.main([str(path), "--no-words", "--fail-on", "warn"]) == 1
    assert lint.main([str(path), "--no-words", "--fail-on", "error"]) == 0
    assert lint.main([str(path), "--no-words", "--strict"]) == 1
    assert lint.main([str(tmp_path / "missing.md"), "--no-words"]) == 2
    with pytest.raises(SystemExit) as exc:
        lint.main([str(path), "--doc-type", "bogus"])
    assert exc.value.code == 2
    capsys.readouterr()


def test_json_output(tmp_path, capsys) -> None:  # noqa: ANN001
    import json
    path = tmp_path / "a.md"
    path.write_text("We delve.\n", encoding="utf-8")
    lint.main([str(path), "--json", "--no-words"])
    data = json.loads(capsys.readouterr().out)
    assert data["tool"] == "yomiyasu-en-lint" and data["review_findings"] == 1
    assert data["findings"][0]["rule"] == "ai_vocabulary"
