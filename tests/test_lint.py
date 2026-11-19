from __future__ import annotations

import pytest
import readyasu_lint as lint
import readyasu_text as tx


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
    assert data["tool"] == "readyasu-lint" and data["review_findings"] == 1
    assert data["findings"][0]["rule"] == "ai_vocabulary"


@pytest.mark.parametrize("text", [
    "This isn't just a tool, it's a platform.\n",
    "We didn't need a new tool. We needed a shared way to use the old one.\n",
    "The tool doesn't just store data, it transforms it.\n",
])
def test_negative_contrast_contractions(text: str) -> None:
    assert "negative_contrast" in rules(text)


@pytest.mark.parametrize("text", [
    "Run **`make test`** before pushing.\n",
    "Open **[the docs](https://example.com)** first.\n",
    "The elevator and the elevation are fine. Use an underscore here.\n",
    "Use the test harness. Check network bandwidth.\n",
    "Fill the fuel tank. Turn the ignition switch.\n",
    "Print in landscape orientation. Raise 2 to the power of 8.\n",
    "Done ✓. Rated ★★★. ☐ Todo.\n",
    "> We delve into this, as the author wrote.\n",
])
def test_more_no_false_positive(text: str) -> None:
    assert rules(text) == []


def test_callout_is_checked() -> None:
    assert "ai_vocabulary" in rules("> **Note:** We delve into it.\n")


def test_large_input_is_fast() -> None:
    import time
    text = "In today's fast-paced world, we delve into robust, seamless tools — truly.\n\n" * 1500
    start = time.monotonic()
    lint.lint(text)
    assert time.monotonic() - start < 20


@pytest.mark.parametrize("text", ["** Note** this.\n", "**Note:**This fails.\n"])
def test_one_bold_finding_per_pair(text: str) -> None:
    assert rules(text).count("bold_unrendered") == 1


# ---------------------------------------------------------------- set 4 lint review


def findings(text: str, doc_type: str | None = None, words: tx.Words | None = None) -> list[lint.Finding]:
    return lint.lint(text, doc_type, None, words).findings


@pytest.mark.parametrize("text", [
    "Open **http://localhost:3000** in your browser.\n",
    "**www.example.com**\n",
    '> [!TIP]\n> ```bash\n> git checkout -- src/utilize.py\n> python -c "print(2**3)"\n> ```\n',
    "- Restore the file:\n\n      git checkout -- src/utilize.py\n",
    "run `git checkout --\nsrc/leverage_utils.py` and rebuild.\n",
    "| Step | Owner |\n|---|---|\n| Batch | — |\n",
    "> In today's fast-paced world, this tool lets\nteams delve into data — and it truly shines.\n",
    "- This item wraps\nlazily onto a second line and\na third line ends with a colon:\n\nNext paragraph.\n",
    "It seems simple, but we could not reproduce it.\n",
    "09:12 — Config change rolled out\n",
    "- 2025-12-03 14:05 UTC — Rollback started\n",
    "- Fix the alert — Owner: Marco Ruiz — Due: Dec 5\n",
    "# Incident report — Checkout API outage\n\nBody text.\n",
    "See the layout:\n\n![diagram](arch.png)\n",
    "The formula:\n\n$$E=mc^2$$\n",
    "Text here <!-- TODO leverage\nthis is delve comment -->\nAfter.\n",
    "Facilitator: Sam. We store vectors in Weaviate.\n",
    "Compute 2**3 = 8 here.\n",
    "+++\ntitle = \"We delve\"\n+++\nBody.\n",
])
def test_set4_no_false_positive(text: str) -> None:
    assert findings(text) == []


def test_mail_offers_and_closings_are_exempt() -> None:
    text = ("Hi Sam,\n\nHere's a draft of the agenda for Monday. I'm happy to help with the slides. Would you like "
            "me to book the room? Let me know if you'd like a later slot.\n\nThanks,\nDana\n")
    result = lint.lint(text, "mail")
    assert result.findings == []
    assert [f.rule for f in result.exempted] == ["chat_residue"] * 4
    assert "chat_residue" in rules(text)  # still residue outside mail


def test_interjections_in_dialogue() -> None:
    text = "TOM: Of course! I will bring the cake.\n"
    assert "chat_residue" not in rules(text, "script")
    assert "chat_residue" not in rules(text, "essay")
    assert "chat_residue" in rules(text)
    assert "chat_residue" not in rules('"Of course!" she said, and left.\n')


@pytest.mark.parametrize("text", [
    "I hope this helps!\n",
    "As an AI language model, I cannot browse.\n",
    "Certainly! Here's the revised version of the plan.\n",
])
def test_real_chat_residue_still_caught(text: str) -> None:
    assert "chat_residue" in rules(text)
    assert "chat_residue" in rules(text, "essay")


def test_essay_keeps_revision_residue() -> None:
    got = [f.match for f in findings("Certainly! Here's the revised version of the plan.\n", "essay")]
    assert got == ["Here's the revised version"]


def test_callout_after_blank_quote_line_is_checked() -> None:
    text = "> [!NOTE]\n> Plain first paragraph.\n>\n> In today's fast-paced world, we leverage synergy.\n"
    assert "stock_phrase" in rules(text)


def test_emoji_and_italic_callouts_are_checked() -> None:
    got = rules("> 💡 **Tip:** Leverage the cache to unlock seamless performance.\n")
    assert "emoji" in got and "ai_vocabulary" in got and "metaphor_verb" in got
    assert rules("> *Note:* We delve here.\n") == ["ai_vocabulary"]


def test_regex_span_does_not_hide_list_findings() -> None:
    got = [(f.rule, f.match) for f in findings("It seems that the seamless, robust pipeline may potentially fail.\n")]
    assert ("ai_vocabulary", "seamless") in got and ("ai_vocabulary", "robust") in got
    assert ("hedge_stack", "may potentially") in got
    assert rules("This plays a crucial role in the design.\n") == ["stock_phrase"]


@pytest.mark.parametrize(("text", "match"), [
    ("It is a testament to the team.\n", "testament to"),
    ("We revolutionize it.\n", "revolutionize"),
    ("Here is a deep dive into it.\n", "deep dive into"),
])
def test_one_finding_per_span(text: str, match: str) -> None:
    assert [f.match for f in findings(text)] == [match]


def test_dash_in_a_cell_with_text_is_still_checked() -> None:
    assert "em_dash" in rules("| Step | Note |\n|---|---|\n| Batch | slow — retry |\n")


def test_project_flag_with_curly_apostrophe(tmp_path) -> None:  # noqa: ANN001
    import warnings
    (tmp_path / "flag.txt").write_text("Let’s circle up\tmeet\nfoo bar*\n", encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        words = tx.load_words(str(tmp_path), False)
    got = findings("Let's circle up today. The foo barrels.\n", words=words)
    messages = [f.message for f in got if f.rule == "project_term"]
    assert len(messages) == 2
    assert messages[0].startswith("Project word \"Let's circle up\" → meet.")
    assert messages[1].startswith('Project word "foo barrels".')


def test_flag_pattern_label_shows_match_and_name(tmp_path) -> None:  # noqa: ANN001
    (tmp_path / "flag-patterns.txt").write_text("ticket\tJIRA-\\d+\n", encoding="utf-8")
    words = tx.load_words(str(tmp_path), False)
    got = findings("See JIRA-123 now.\n", words=words)
    assert got[0].message.startswith('Project word "JIRA-123" (ticket).')


@pytest.mark.parametrize("text", ["## **Benefits:**\n", "### *Notes:*\n"])
def test_heading_colon_inside_emphasis(text: str) -> None:
    assert rules(text) == ["heading_colon"]


def test_hedge_stack_still_catches_seems_may() -> None:
    assert "hedge_stack" in rules("It seems that the job may fail.\n")
    assert "hedge_stack" in rules("It appears the job may possibly fail.\n")


def test_em_dash_after_title_and_mid_line_time_still_checked() -> None:
    text = "# Report — Outage\n\n## Timeline — details\n\nAt 09:12 — we rolled back.\n"
    got = [(f.rule, f.line) for f in findings(text)]
    assert got == [("em_dash", 3), ("em_dash", 5)]


@pytest.mark.parametrize("text", [
    "It's not just an app. It's your second brain.\n",
    "This incident wasn't just a technical hiccup; it was a pivotal moment.\n",
])
def test_negative_contrast_more_forms(text: str) -> None:
    assert "negative_contrast" in rules(text)


def test_inline_html_prose_is_checked() -> None:
    text = "<strong>Warning:</strong> In today's fast-paced world, we leverage synergy <em>x</em>\n"
    assert "stock_phrase" in rules(text)


def test_columns_are_raw_line_columns(tmp_path, capsys) -> None:  # noqa: ANN001
    import json
    path = tmp_path / "a.md"
    path.write_text("- We will delve into it.\n> **Note:** It is truly great.\n", encoding="utf-8")
    lint.main([str(path), "--json", "--no-words"])
    data = json.loads(capsys.readouterr().out)
    cols = {(f["match"], f["line"]): f["col"] for f in data["findings"]}
    assert cols[("delve", 1)] == 11
    assert cols[("truly", 2)] == 19
    text = "Fine.\n\n   We ran the tests. We fixed the bug. We shipped the release.\n"
    assert [(f.rule, f.line, f.col) for f in findings(text)] == [("sentence_start_repeat", 3, 4)]


def test_allow_list_normalizes_apostrophes_and_line_breaks() -> None:
    words = tx.Words(allow=["it's worth noting that", "in order to"])
    assert rules("It’s worth noting that we did it in order\nto save time.\n", words=words) == []
    got = findings("We did it in order\nto save time.\n")
    assert [f.match for f in got] == ["in order to"]
    assert '"in order to"' in got[0].message


def test_messages_show_original_text() -> None:
    got = findings("It is **bold `code` **here.\n")
    assert got[0].rule == "bold_unrendered" and "`code`" in got[0].message and "xxxx" not in got[0].message


def test_lone_bold_marker_is_info() -> None:
    got = findings("Pass **kwargs to the function.\n")
    assert [(f.rule, f.severity) for f in got] == [("bold_unrendered", "info")]
    assert "backticks" in got[0].message
    assert [(f.rule, f.severity) for f in findings("**Note:**This fails.\n")] == [("bold_unrendered", "error")]


def test_heading_keeps_trailing_hash_of_word() -> None:
    doc_findings = findings("## Using C#:\n")
    assert [f.rule for f in doc_findings] == ["heading_colon"]
    assert doc_findings[0].col == 12


@pytest.mark.parametrize("text", [
    "|" + " " * 40000 + "x\n",
    "a@b " + "a." * 20000 + "\n",
    "http://x " + "a." * 20000 + "\n",
    "A. " * 13000 + "\n",
    "**a " * 10000 + "\n",
    "a — b " * 7000 + "\n",
    "# a" + " " * 40000 + "b\n",
])
def test_adversarial_lines_are_fast(text: str) -> None:
    import time
    start = time.monotonic()
    lint.lint(text)
    assert time.monotonic() - start < 2


def test_long_hard_wrapped_text_is_fast() -> None:
    import textwrap
    import time
    para = ("In today's fast-paced world, we delve into robust, seamless tools — truly. It is a testament to the "
            "team that we leverage synergy. The answer was no. Run `make test` at https://x.io now. ")
    text = textwrap.fill(para * 1300, 72) + "\n"  # about 300 KB with no blank lines
    start = time.monotonic()
    result = lint.lint(text)
    assert time.monotonic() - start < 5
    assert len(result.findings) > 1000
