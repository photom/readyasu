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
    text = "Let me know if you have any questions. I hope this helps. As an AI language model, I can't attach files.\n"
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
    assert [f.rule for f in result.exempted] == ["chat_residue"] * 3  # "Here's a draft" needs a colon after it
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
    assert got == ["Certainly! Here's the revised version"]


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


# ---------------------------------------------------------------- set 5 lint review


def located(text: str, doc_type: str | None = None) -> list[tuple[str, int, int, str]]:
    return [(f.rule, f.line, f.col, f.match) for f in findings(text, doc_type)]


def test_second_paragraph_of_a_list_item_is_checked() -> None:
    text = ("1. Open the settings page.\n\n    Pick the region closest to your users.\n\n"
            "    This step leverages a robust cache — it is seamless.\n\n2. Save.\n")
    got = [(rule, line) for rule, line, _col, _m in located(text)]
    assert got == [("ai_vocabulary", 5), ("ai_vocabulary", 5), ("em_dash", 5), ("ai_vocabulary", 5)]


def test_fence_after_list_paragraph_is_not_prose() -> None:
    text = ("1. Install the tool:\n    ~~~\n    npm i\n    ~~~\n    Then start it:\n    ~~~\n"
            "    npm start -- --robust # leverage\n    ~~~\n2. Done.\n")
    assert findings(text) == []


@pytest.mark.parametrize("text", [
    "As an AI researcher, I have reviewed the paper.\n",
    "We use GPT-2 as a language model for rescoring.\n",
    "The firm positions itself as an AI company.\n",
    "Hope this helps clarify the timeline.\n",
])
def test_chat_residue_not_in_ordinary_prose(text: str) -> None:
    assert "chat_residue" not in rules(text, "mail")
    if text.startswith("Hope"):
        assert "chat_residue" in rules(text)  # still residue in a document
    else:
        assert "chat_residue" not in rules(text)


@pytest.mark.parametrize("text", [
    "As an AI, I don't have personal opinions.\n",
    "As a large language model, I cannot browse the web.\n",
    "As an AI language model I cannot browse.\n",
])
def test_ai_disclaimers_still_caught(text: str) -> None:
    assert "chat_residue" in rules(text, "mail")


def test_hope_this_helps_is_a_courtesy() -> None:
    result = lint.lint("Thanks for the notes. I hope this helps!\n", "mail")
    assert "chat_residue" not in [f.rule for f in result.findings]
    assert [f.match for f in result.exempted if f.rule == "chat_residue"] == ["I hope this helps"]
    assert "chat_residue" in rules("I hope this helps!\n")


def test_dash_position_is_the_dash(tmp_path, capsys) -> None:  # noqa: ANN001
    import json
    path = tmp_path / "a.md"
    path.write_text("We changed the cache\n— and the latency dropped.\n\nWe changed it — and it worked.\n"
                    "\nWe tried -- and failed.\n", encoding="utf-8")
    lint.main([str(path), "--json", "--no-words"])
    data = json.loads(capsys.readouterr().out)
    assert [(f["line"], f["col"], f["match"]) for f in data["findings"] if f["rule"] == "em_dash"] == [
        (2, 1, "—"), (4, 15, "—"), (6, 10, "--")]


@pytest.mark.parametrize("text", [
    "The best code is no code at all.\n— Jeff Atwood\n",
    '"Simplicity is prerequisite for reliability."\n— Edsger W. Dijkstra, 1975\n',
])
def test_attribution_under_a_quotation(text: str) -> None:
    assert "em_dash" not in rules(text)


@pytest.mark.parametrize("text", [
    "We tried everything.\n— Then It Worked Again.\n",
    "We changed the cache\n— Jeff noticed it.\n",
])
def test_dash_line_that_is_not_an_attribution(text: str) -> None:
    assert "em_dash" in rules(text)


@pytest.mark.parametrize("text", [
    "It is faster, that is for sure!\n",
    "The answer, of course! was no.\n",
    "This is a great question to ask your vendor.\n",
    "This is a\ngreat question to ask your vendor.\n",
    "| Q | A |\n|---|---|\n| Faster? | Yes, for sure! |\n",
])
def test_interjections_mid_sentence(text: str) -> None:
    assert "chat_residue" not in rules(text)


@pytest.mark.parametrize("text", [
    "Great question! Here is the answer.\n",
    "We shipped it. Of course! It worked.\n",
    "**Certainly!** Here is the plan.\n",
    "Sam asked about pricing\nGreat question! We will follow up.\n",
    "Hey there! Welcome to the guide.\n",
    "| Reply | Action |\n|---|---|\n| Sure! I will send it. | Delete |\n",
])
def test_interjections_at_a_sentence_start(text: str) -> None:
    assert "chat_residue" in rules(text)
    assert "chat_residue" not in rules(text, "script")


def test_interjection_list_comment_matches_behavior() -> None:
    header = [ln for ln in (tx.LISTS_DIR / "chat-interjections.txt").read_text(encoding="utf-8").splitlines()
              if ln.startswith("#")]
    assert "double quotation marks" in " ".join(header)
    assert "chat_residue" not in rules('"Sure!" she said.\n')
    assert "chat_residue" in rules("'Sure!' she said.\n")  # single quotes are not treated as dialogue


@pytest.mark.parametrize("text", [
    "1. 10:00–10:15 — Status updates\n",
    "2. 10:15 - 10:45 — Roadmap review\n",
    "3. 10:45 to 11:00 — Questions\n",
    "5. Dec 3–5 — Offsite\n",
    "- 14:00–15:00 — Review meeting\n",
    "- 10:00 – 10:15 — Standup\n",
    "Version 2.1 — Effective January 1, 2027\n",
    "Last updated: March 2026 — Draft\n",
    "- v2.1 — Rewrote the parser\n",
])
def test_em_dash_after_time_range_or_version(text: str) -> None:
    assert "em_dash" not in rules(text)


def test_em_dash_after_mid_line_range_still_checked() -> None:
    assert "em_dash" in rules("We met at 10:00–10:15 — it was short.\n")


@pytest.mark.parametrize("text", [
    "This is not a bug, but a feature.\n",
    "It is not a tool but a mindset.\n",
    "Observability is not a tool, but a mindset.\n",
    "This isn't a bug, but rather a feature.\n",
    "This is not about blame, but about learning.\n",
])
def test_negative_contrast_not_x_but_y(text: str) -> None:
    assert rules(text) == ["negative_contrast"]


@pytest.mark.parametrize("text", [
    "It is not a big change, but it fixes the crash.\n",
    "The fix was not tested, but it shipped.\n",
    "It is not the default but can be enabled.\n",
    "I didn't get the invite. We need to resend it before Friday.\n",
    "We don't have the budget this quarter. We need approval from finance first.\n",
    "It isn't ready. We are still testing it.\n",
])
def test_negative_contrast_concessions_and_unrelated_sentences(text: str) -> None:
    assert "negative_contrast" not in rules(text)


@pytest.mark.parametrize("text", [
    "The fix isn't a hack. It's a proper solution.\n",
    "They don't sell software. They sell trust.\n",
])
def test_negative_contrast_two_sentences_same_subject(text: str) -> None:
    assert "negative_contrast" in rules(text)


@pytest.mark.parametrize("text", [
    "It appears that the attacker could read any file on the server.\n",
    "It seems nobody could reproduce the bug on macOS.\n",
    "It seems no one could have known.\n",
    "It appears the release slipped to May.\n",
])
def test_hedge_stack_ability_could(text: str) -> None:
    assert "hedge_stack" not in rules(text)


def test_hedge_stack_possibility_could() -> None:
    assert "hedge_stack" in rules("It seems the job could have failed.\n")
    assert "hedge_stack" in rules("It appears the cache could be stale.\n")


def test_exempt_finding_does_not_hide_a_kept_one(tmp_path) -> None:  # noqa: ANN001
    (tmp_path / "flag.txt").write_text("let me know if\n", encoding="utf-8")
    words = tx.load_words(str(tmp_path), False)
    result = lint.lint("Let me know if you have any questions.\n", "mail", None, words)
    assert [(f.rule, f.match) for f in result.findings] == [("project_term", "Let me know if")]
    assert [f.rule for f in result.exempted] == ["chat_residue"]


def test_unclosed_front_matter_is_checked() -> None:
    got = rules("---\n\nWe leverage robust tooling — seamlessly.\n")
    assert "em_dash" in got and got.count("ai_vocabulary") == 3


def test_unpaired_backticks_are_fast() -> None:
    import time
    text = " ".join("`" * m for m in range(1, 280)) + " x\n"
    start = time.monotonic()
    lint.lint(text)
    assert time.monotonic() - start < 1


@pytest.mark.parametrize("text", [
    "The new dashboard feels faster after the fix.\n",
    "The agent will happily walk you through the setup.\n",
])
def test_personification_perception_and_people(text: str) -> None:
    assert "personification" not in rules(text)


@pytest.mark.parametrize("text", [
    "The tool will happily refuse to start.\n",
    "The system carefully remembers every deadline.\n",
    "The function seemed to resent being woken up.\n",
    "The monitor tirelessly watches over your services.\n",
    "The service never forgets a deadline.\n",
])
def test_personification_more_forms(text: str) -> None:
    assert "personification" in rules(text)


def test_tame_and_happy_closers() -> None:
    assert [f.match for f in findings("We tamed the cold-start beast.\n")] == ["tamed the"]
    assert "chat_residue" in rules("Happy monitoring!\n")
    assert "chat_residue" not in rules("Happy monitoring!\n", "mail")
    assert "chat_residue" not in rules("We sell the Happy Hacking Keyboard.\n")


def test_callout_with_emoji_inside_bold_is_checked() -> None:
    got = rules("> **⚠️ Warning:** This leverages a robust lock — seamlessly.\n")
    assert "ai_vocabulary" in got and "em_dash" in got
    assert "ai_vocabulary" in rules("> ℹ️ **Note:** We leverage it.\n")


def test_numbered_clauses_are_not_a_repeated_start() -> None:
    text = ("3.1 The Supplier shall deliver the goods.\n3.2 The Supplier shall invoice monthly.\n"
            "3.3 The Supplier shall report defects.\n")
    assert "sentence_start_repeat" not in rules(text, "formal")


# ---------------------------------------------------------------- set 6 lint review


@pytest.mark.parametrize("text", [
    "To install, run: `pip install fastq-tools`\n\nSee the [guide][g].\n\n[g]: https://example.com/guide\n\n"
    "## Option: `--force`\n\nText.\n",
    "The docs are at: https://example.com/docs\n\nNext.\n",
    "Contact: ops@example.com\n\nNext.\n",
    "# Title\n\n## API: <https://example.com>\n\nText.\n",
    "[g]: /docs/guide:\n\nNext.\n",
])
def test_colon_before_code_url_or_link_definition(text: str) -> None:
    assert findings(text) == []


def test_colon_columns_are_the_colon() -> None:
    assert located("Consider `x` here:\n\nNext.\n") == [("decorative_colon", 1, 18, ":")]
    assert located("# T\n\n## Steps `a`:\n\nText.\n") == [("heading_colon", 3, 13, ":")]
    assert rules("Note <b>this</b>:\n\nNext.\n") == ["decorative_colon"]  # tags are invisible


@pytest.mark.parametrize("text", [
    "If the value is not set, it is read from the environment.\n",
    "Although the API is not stable, it is widely used.\n",
    "The outage was not a major one, but customers noticed it.\n",
    "When the file is not found, it is created.\n",
    "Because the cache is not shared, it is rebuilt on start.\n",
    "It is not a big change, but reviewers should check it.\n",
    "It was not a failure, but nobody cared.\n",
])
def test_negative_contrast_conditions_and_concessions(text: str) -> None:
    assert "negative_contrast" not in rules(text)


def test_negative_contrast_match_ends_on_a_word() -> None:
    assert [f.match for f in findings("This is not about blame, but about learning.\n")] == [
        "is not about blame, but about learning"]
    assert [f.match for f in findings("It is not just fast but also cheap.\n")] == ["not just fast but also cheap"]
    assert rules("It is not a tool but infrastructure.\n") == ["negative_contrast"]


def test_hard_wrapped_hedge_and_contrast() -> None:
    text = "It seems that the new cache layer\nmay be the cause.\n\nThe tool does not just lint your\nfiles, it fixes them.\n"
    assert [(r, ln) for r, ln, _c, _m in located(text)] == [("hedge_stack", 1), ("negative_contrast", 4)]
    assert "negative_contrast" in rules("It isn't a tool.\nIt's a philosophy.\n")


@pytest.mark.parametrize("text", [
    "Open Monday – Friday, 9 am – 5 pm. Seats cost $5 – $10.\n",
    "We support v1.2 – v1.4.\n",
    "The pilot runs January – March.\n",
    "Expect 20% – 30% fewer pages, Q1 – Q3.\n",
    "Files of 5 MB – 10 MB load fast.\n",
])
def test_spaced_dash_ranges(text: str) -> None:
    assert "em_dash" not in rules(text)


def test_spaced_dash_beside_one_number_is_reported() -> None:
    assert rules("In 2020 – the year of the pandemic – we grew.\n").count("em_dash") == 2
    assert "em_dash" in rules("It may – or may not – work.\n")


@pytest.mark.parametrize("text", [
    "I'm not sure. I'm checking with the database team.\n",
    "We're not ready to ship. We're still waiting on QA.\n",
    "They aren't available this week. They are at the offsite.\n",
])
def test_two_sentence_status_updates(text: str) -> None:
    assert "negative_contrast" not in rules(text)


def test_two_sentence_contrast_with_a_noun_after_be() -> None:
    assert "negative_contrast" in rules("It isn't a feature. It's something we hacked together.\n")
    assert "negative_contrast" in rules("We're not a startup. We're a research lab.\n")


@pytest.mark.parametrize("text", [
    "Dear Ms. Alvarez:\n\nThank you for the offer.\n",
    "To whom it may concern:\n\nI am writing about the lease.\n",
])
def test_letter_salutation_colon(text: str) -> None:
    assert "decorative_colon" not in rules(text, "formal")


def test_dash_after_a_code_term_is_not_reported_in_any_form() -> None:
    text = "- `--threads N` — workers\n- `--verbose` – more output\n- `-q` -- quiet\n- **`-x`** — exit\n"
    assert rules(text) == []
    assert located("Use `foo` — it is fast.\n") == [("em_dash", 1, 11, "—")]
    assert rules("- `a` and b — then c\n") == ["em_dash"]
    assert rules("- [`foo`](https://x.io/foo) — the foo tool\n") == []
    assert rules("- [Guide](guide.md) — it explains everything\n") == ["em_dash"]


@pytest.mark.parametrize("text", [
    "What could possibly go wrong?\n",
    "There is no way we could possibly finish.\n",
    "Nobody could possibly know.\n",
])
def test_rhetorical_could_possibly(text: str) -> None:
    assert "hedge_stack" not in rules(text)


def test_hedge_after_a_distant_negation_is_reported() -> None:
    assert "hedge_stack" in rules("It is not clear if the change may potentially break it.\n")


def test_wrapped_year_is_checked_as_text() -> None:
    assert rules("The company was founded in\n1998. It now employs 40 people — mostly engineers.\n") == ["em_dash"]


def test_indented_backticks_do_not_hide_the_rest() -> None:
    assert rules("- item\n\n      ```\n      x\n\nIt is worth noting that.\n") == ["stock_phrase"]


def test_title_is_exempt_from_expression_rules() -> None:
    assert findings("# Unlocking the Power of X: A Robust Guide\n\nBody.\n") == []
    assert rules("# 🚀 Launch\n\nBody.\n") == ["emoji"]
    assert rules("# Title\n\n## Unlocking the Power:\n\nBody.\n") == ["metaphor_verb", "heading_colon"]


def test_negative_contrast_in_headings() -> None:
    text = "# T\n\n## Not just a linter, but a formatter\n\n## Not a linter but a formatter\n\n## Not all tests pass\n"
    assert [(r, ln) for r, ln, _c, _m in located(text)] == [("negative_contrast", 3), ("negative_contrast", 5)]


def test_entry_exemptions_for_slides_and_script() -> None:
    for doc_type in ("slides", "script"):
        result = lint.lint("Thank you for your attention.\n", doc_type)
        assert result.findings == [] and [f.rule for f in result.exempted] == ["chat_residue"]
    assert rules("Thank you for your attention.\n", "article") == ["chat_residue"]
    result = lint.lint("# Deck\n\n## Key Takeaways\n\nWe cut costs.\n", "slides")
    assert result.findings == []
    assert "ai_vocabulary" in [f.rule for f in result.exempted]
    assert "ai_vocabulary" in rules("# Deck\n\n## Key Takeaways\n\nWe cut costs.\n", "article")
    assert '"thank you for your attention"' in lint.HELP_EPILOG
    for (name, phrase), _types in lint.ENTRY_EXEMPT.items():  # every exempted entry is still in its list
        assert phrase in [entry.phrase.lower() for entry in tx.load_list(name)], (name, phrase)


def test_one_emoji_finding_per_cluster() -> None:
    got = findings("Flag 🇯🇵, family 👨‍👩‍👧, thumbs 👍🏽.\n")
    assert [f.match for f in got] == ["🇯🇵", "👨‍👩‍👧", "👍🏽"]
    assert rules("# T\n\nBody.\n\n## ⚠️ Summary\n\nDone.\n") == ["emoji", "closing_summary"]


@pytest.mark.parametrize("text", [
    "Run `apt update`. Then run `apt install foo`. Next `systemctl start foo`.\n",
    "Open Settings. Click Save. Restart the app.\n",
])
def test_imperative_steps_are_not_fragments(text: str) -> None:
    assert "fragment_run" not in rules(text, "manual")
    assert "fragment_run" not in rules(text)


def test_fragments_still_reported() -> None:
    assert "fragment_run" in rules("Fast. Simple. Reliable.\n")
    assert "fragment_run" in rules("Build. Test. Ship.\n")


def test_interjection_quotes_are_linear() -> None:
    import time
    start = time.monotonic()
    result = lint.lint("Sure! " * 40000 + "\n")
    assert time.monotonic() - start < 4
    assert [f.rule for f in result.findings].count("chat_residue") == 40000
    assert "chat_residue" not in rules('"Sure!" she said. “Of course!” he said.\n')
    assert "chat_residue" in rules('"Fine," she said. Sure! We will go.\n')


@pytest.mark.parametrize("text", [
    "- 1.2.0 — Added dedup.\n",
    "- 2025/12/03 — kickoff.\n",
    "- 03.12.2025 — kickoff.\n",
    "- 9–10 am — standup.\n",
    "- 2.0.0-rc1 — Release candidate.\n",
])
def test_more_stamps_before_a_dash(text: str) -> None:
    assert "em_dash" not in rules(text)


def test_text_output_has_column_and_centered_excerpt(tmp_path, capsys) -> None:  # noqa: ANN001
    path = tmp_path / "a.md"
    path.write_text("x " * 100 + "the fix — a small one. " + "y " * 100 + "\n", encoding="utf-8")
    lint.main([str(path), "--no-words"])
    out = capsys.readouterr().out
    assert "L1:209 [WARN] em_dash: Dash in \"" in out
    excerpt = [ln for ln in out.splitlines() if ln.startswith("  > ")][0]
    assert "the fix — a small one." in excerpt and excerpt.startswith("  > …")
    assert 'Dash in "…x x x x x x x x the fix — a small one. y y y y y…"' in out


def test_exclamation_message_shows_context() -> None:
    got = findings("We shipped it! It works.\n")
    assert got[0].rule == "exclamation" and '"We shipped it! It works."' in got[0].message


def test_code_starts_a_sentence() -> None:
    got = rules("The fix? `retry()` now wraps every call.\n\nWe shipped it! `v2.0` is live.\n")
    assert got == ["self_answered_question", "exclamation"]
    text = "`a` is one. `b` is two. `c` is three.\n"
    assert "sentence_start_repeat" not in rules(text)


@pytest.mark.parametrize(("text", "rule"), [
    ("In today's rapidly evolving healthcare landscape, teams struggle.\n", "stock_phrase"),
    ("What, then, is the gap? Simply put, we lack data.\n", "self_answered_question"),
    ("Is it slow? In short, yes.\n", "self_answered_question"),
    ("The scheduler chose to retry the job.\n", "personification"),
    ("The tool decided to stop.\n", "personification"),
])
def test_end_to_end_misses(text: str, rule: str) -> None:
    assert rule in rules(text)


def test_assistant_preamble_in_mail() -> None:
    text = "Certainly! Here's a reply you can send to Jordan:\n\nHi Jordan,\n\nThanks for the note.\n\nBest,\nSam\n"
    result = lint.lint(text, "mail")
    assert [(f.rule, f.match) for f in result.findings if f.rule == "chat_residue"] == [
        ("chat_residue", "Certainly! Here's a reply you can send")]
    mail = "Hi Sam,\n\nHere's a draft you can use for the client deck. I added the numbers.\n\nThanks,\nDana\n"
    assert "chat_residue" not in [f.rule for f in lint.lint(mail, "mail").findings]
    mail = "Here's a draft you can use for the client deck. I added the numbers.\n\nThanks,\nDana\n"
    assert "chat_residue" not in [f.rule for f in lint.lint(mail, "mail").findings]
    alone = "Sure! Here's a polished version you can send.\n\nHi Jordan,\n\nThanks.\n"
    assert "chat_residue" in [f.rule for f in lint.lint(alone, "mail").findings]


# ---------------------------------------------------------------- set 7 lint review


@pytest.mark.parametrize("text", [
    "09:12 — Config change rolled out\n09:15 — Alerts fired\n09:52 — Rollback started\n",
    "Agenda\n10:00–10:15 — Status updates\n10:15–10:45 — Roadmap\n",
    "Milestones\nDec 5, 2025 — Kickoff\nDec 3–5, 2025 — Offsite\n2025-12-03 09:12 UTC — Paged\n",
])
def test_timeline_lines_after_the_first_line(text: str) -> None:
    assert "em_dash" not in rules(text, "incident")


@pytest.mark.parametrize("stamp", [
    ("1.11" * 20)[:52], ("1.11" * 20)[:61], ("1.11 " * 13)[:60], ("1.11," * 13)[:60], ("sat " * 15)[:60],
    ("10.10.10 " * 7)[:60], ("t+1 " * 15)[:60],
])
def test_stamp_check_is_fast(stamp: str) -> None:
    import time
    start = time.monotonic()
    for text in (stamp + "x — y\n", "a\n" + stamp + "x — y\n"):
        assert "em_dash" in rules(text)
    assert time.monotonic() - start < 1


def test_stamps_still_match_after_the_separator_change() -> None:
    for stamp in ("09:12", "10:00–10:15", "Dec 3–5", "Version 2.1", "Last updated: March 2026", "2025-12-03 09:12 UTC",
                  "1.10", "1.2", "9.30 am", "Mon 10:00"):
        assert lint._STAMP.match(stamp + " "), stamp


def test_wrapped_number_in_a_list_item_is_text() -> None:
    assert located("- The company was founded in\n  1998. It now employs 50 people — mostly engineers.\n") == [
        ("em_dash", 2, 34, "—")]


@pytest.mark.parametrize("text", [
    "This is not a blocker, but the team should review it before Friday.\n",
    "The outage was not a major one, but our largest customer noticed it.\n",
    "This is not a breaking change, but the default timeout went from 30s to 10s.\n",
    "This is not a perfect fix, but the tests pass.\n",
    "It is not a big deal, but the release notes need an update.\n",
    "This is not a regression, but the fix still needs a test.\n",
    "It is not a hard rule, but the team needs to agree on it.\n",
])
def test_negative_contrast_concession_with_a_clause_after_but(text: str) -> None:
    assert "negative_contrast" not in rules(text)


@pytest.mark.parametrize("text", [
    "This is not a product, but a platform for building products.\n",
    "This is not a bug, but the expected behavior.\n",
    "It's not a cost, but a long-term strategic investment.\n",
    "It is not a bug but a feature we built on purpose.\n",
    "## Not a linter, but a formatter for teams\n",
])
def test_negative_contrast_noun_phrase_after_but_is_reported(text: str) -> None:
    assert "negative_contrast" in rules("# T\n\n" + text)


@pytest.mark.parametrize(("text", "match"), [
    ("We __leverage__ caching and _seamless_ deploys.\n", ["leverage", "seamless"]),
    ("_In today's fast-paced world_, teams ship daily.\n", ["In today's fast-paced world"]),
    ("This _may potentially_ break.\n", ["may potentially"]),
    ("The _code tells a story_.\n", ["The _code tells a story"]),
    ("Set enable_seamless_mode and leverage_ratio.\n", []),
])
def test_underscore_emphasis_does_not_hide_matches(text: str, match: list[str]) -> None:
    assert [f.match for f in findings(text)] == match


def test_underscore_emphasis_and_project_words(tmp_path) -> None:  # noqa: ANN001
    (tmp_path / "flag.txt").write_text("frobnicate\n", encoding="utf-8")
    (tmp_path / "flag-patterns.txt").write_text("vendor\t\\bAcme\\b\n", encoding="utf-8")
    words = tx.load_words(str(tmp_path), False)
    got = lint.lint("We _frobnicate_ data from __Acme__ but not my_frobnicate_fn.\n", None, None, words).findings
    assert [(f.rule, f.match) for f in got] == [("project_term", "frobnicate"), ("project_term", "Acme")]


def test_keycap_emoji_alone_is_reported() -> None:
    assert [f.match for f in findings("Press 1️⃣ to start.\n")] == ["1️⃣"]
    assert [f.match for f in findings("Use #️⃣ tags.\n")] == ["#️⃣"]


def test_option_aliases_before_a_dash() -> None:
    text = "- `-h`, `--help` — show help\n- `-v` / `--verbose` — print progress\n- `-q` or `--quiet` — be quiet\n"
    assert rules(text) == []
    assert rules("- `-h`, `--help`, and the rest — this is wrong\n") == ["em_dash"]
    assert rules("- `a` or b — then c\n") == ["em_dash"]


def test_dash_bullets_in_plain_text() -> None:
    assert rules("Decisions:\n– Budget approved\n– Hiring paused\n", "minutes") == []
    assert rules("Notes\n— Budget approved\n— Hiring paused\n") == []
    assert rules("Action items:\n-- Send the deck\n") == []
    assert located("We fixed the bug\n— and then the cache broke.\n") == [("em_dash", 2, 1, "—")]
    assert rules("Decisions:\n– Budget approved – mostly\n") == ["em_dash"]  # only the bullet is skipped


def test_heading_contrast_needs_an_article_or_just() -> None:
    text = "# T\n\n## Not supported, but planned\n\n## Not now, but soon\n\n## Not just fast, but reliable\n"
    assert [(r, ln) for r, ln, _c, _m in located(text)] == [("negative_contrast", 7)]


@pytest.mark.parametrize("text", [
    "## Step 1 — Install the CLI\n", "Part 2 — Setup\n", "Option A — Keep the cache\n", "Chapter 3 — Results\n",
    "- Lesson 4 — Testing\n", "Module 2.1 — Parsing\n", "Stage II — Rollout\n",
])
def test_em_dash_after_a_numbered_label(text: str) -> None:
    assert "em_dash" not in rules("# T\n\n" + text)


def test_em_dash_after_a_label_word_without_a_number_is_reported() -> None:
    assert "em_dash" in rules("The next step — the hard one — is testing.\n")


@pytest.mark.parametrize("text", [
    "Kubernetes is not just a scheduler, it is a platform.\n",
    "Our tool is not only a linter, it is a formatter.\n",
    "React isn't a framework; it's a library.\n",
    "Kubernetes isn't just a scheduler. It's a platform.\n",
    "This tool isn't a linter. It's a formatter.\n",
    "Docs aren't optional. They're part of the product.\n",
])
def test_negative_contrast_names_and_is_not_just(text: str) -> None:
    assert "negative_contrast" in rules(text)


@pytest.mark.parametrize("text", [
    "Alice isn't available today. She is at the offsite.\n",
    "Monday isn't a holiday. We work as usual.\n",
    "When Docker isn't running, it fails fast.\n",
    "This is not a bug. It is not a feature either.\n",
])
def test_negative_contrast_names_without_a_contrast(text: str) -> None:
    assert "negative_contrast" not in rules(text)


@pytest.mark.parametrize("text", [
    "We didn't build a new tool. We built a shared process.\n",
    "We didn't stop the rollout. We stopped the alerts.\n",
    "They didn't write a spec. They wrote a prototype.\n",
    "It doesn't have a UI. It has a CLI.\n",
])
def test_negative_contrast_irregular_and_doubled_verbs(text: str) -> None:
    assert "negative_contrast" in rules(text)


def test_exclamation_before_an_emoji() -> None:
    got = findings("We shipped v2! 🎉 Thanks to everyone who helped.\n")
    assert [(f.rule, f.col) for f in got] == [("exclamation", 14), ("emoji", 16)]
    assert "exclamation" in rules("Happy restoring! 🎉\n")
    assert "exclamation" in rules("Done!🎉\n")
    assert "exclamation" not in rules("Done 🎉\n")


def test_happy_restoring_is_a_closing() -> None:
    assert "chat_residue" in rules("Happy restoring!\n")
    assert "chat_residue" not in rules("Happy restoring!\n", "mail")


def test_preamble_after_a_greeting_is_the_writers_mail() -> None:
    for mail in ("Hi Ana,\n\nHere's a draft reply you can send to the customer:\n\n> Dear Mr. Lee, thanks.\n",
                 "Hi Ana,\nHere's a draft reply you can send to the customer:\n\n> Dear Mr. Lee, thanks.\n",
                 "Dear Mr. Lee,\n\nHere is a version you can forward to your team:\n\n- one\n"):
        assert "chat_residue" not in rules(mail, "mail"), mail
    text = "Certainly! Here's a reply you can send to Jordan:\n\nHi Jordan,\n\nThanks.\n"
    assert "chat_residue" in rules(text, "mail")
    text = "Hi there! Here's a draft you can send to the client:\n\n> Hello.\n"
    assert "chat_residue" in rules(text, "mail")
    text = "Hello world programs are short.\n\nSure! Here's a version you can use:\n\n> Hello.\n"
    assert "chat_residue" in rules(text, "mail")


@pytest.mark.parametrize("text", [
    "I'm not in the office today. I'm at the dentist.\n",
    "They're not coming to the offsite. They're on leave.\n",
    "We're not working on it this week. We're off until Monday.\n",
])
def test_two_sentence_status_places_and_progressives(text: str) -> None:
    assert "negative_contrast" not in rules(text)


def test_two_sentence_contrast_about_is_still_reported() -> None:
    assert "negative_contrast" in rules("It's not about speed. It's about trust.\n")


def test_sentences_split_after_ms_and_pm() -> None:
    assert "sentence_start_repeat" in rules("The p95 is 450 ms. It was 300 ms. It is fine. It is fast.\n")
    assert "sentence_start_repeat" in rules("We meet at 5 p.m. We eat at 6 p.m. We leave at 9.\n")


@pytest.mark.parametrize("text", [
    "The tool will lovingly verify each file.\n",
    "The retry logic now tells the story.\n",
    "The parser stubbornly refuses to guess.\n",
])
def test_personification_set7(text: str) -> None:
    assert "personification" in rules(text)


def test_metaphor_and_contrast_messages() -> None:
    got = findings("This will unlock new value.\n")
    assert got[0].rule == "metaphor_verb"
    assert "Use only what the original or material says; otherwise keep it and ask." in got[0].message
    assert "Do not replace it with a vague benefit." in got[0].message
    got = findings("It is not just fast but also cheap.\n")
    assert got[0].rule == "negative_contrast" and '("not just X" affirms X; keep X)' in got[0].message


# ---------------------------------------------------------------- set 8 lint review


@pytest.mark.parametrize(("text", "doc_type"), [
    ("## Configuration\n\nHere are the options you can use with `tinyq worker`:\n\n- `--threads N`: worker threads\n"
     "- `--db PATH`: database file\n", None),
    ("## Configuration\n\nHere are the options you can use with `tinyq worker`:\n\n- `--threads N`: threads\n",
     "manual"),
    ("# Webhooks\n\nHere is the message you can use to test the webhook:\n\n```json\n{}\n```\n", None),
    ("Some managers need numbers.\n\nIf yours does, here's a short email you can send to your manager:\n\n"
     "> Hi Dana, ...\n", "article"),
    ("Here's a reply you can send to Jordan:\n\n- one\n- two\n", "mail"),  # no drafted mail follows
    ("We are not sure. Here are the options:\n\n- a\n", None),
])
def test_ordinary_lead_ins_are_not_preambles(text: str, doc_type: str | None) -> None:
    assert "chat_residue" not in rules(text, doc_type)


@pytest.mark.parametrize(("text", "doc_type", "match"), [
    ("Certainly! Here's a revised version:\n\nThe system is fast.\n", None, "Certainly! Here's a revised version"),
    ("Certainly! Here's a revised version:\n\nHi Jordan,\n\nThanks.\n", "mail", "Certainly! Here's a revised version"),
    ("Sure! Here's a draft email you can send:\n\nHi Jordan,\n\nThanks.\n", "mail",
     "Sure! Here's a draft email you can send"),
    ("Sure — here's the text you can use:\n\n> Hello.\n", None, "Sure — here's the text you can use"),
    ("Here's a polished version of your email:\n\nHi Jordan,\n\nThanks.\n", "mail", "Here's a polished version"),
    ("Here's a more concise version:\n\nThe system is fast.\n", None, "Here's a more concise version"),
    ("Here's a reply you can send to Jordan:\nHi Jordan,\nThanks.\n", "mail", "Here's a reply you can send"),
    ("Here's a reply you can send to Jordan:\n\nSubject: Q3 numbers\n\nHi Jordan,\n", "mail",
     "Here's a reply you can send"),
    ("I'm not sure. Here's a reply you can send to Jordan:\n\nHi Jordan,\n", "mail", "Here's a reply you can send"),
])
def test_assistant_preambles_still_caught(text: str, doc_type: str | None, match: str) -> None:
    assert [f.match for f in findings(text, doc_type) if f.rule == "chat_residue"] == [match]


def test_revision_lead_in_before_a_list_is_normal_in_mail() -> None:
    text = "Here is the revised version of the agenda:\n\n- Budget\n- Hiring\n"
    result = lint.lint(text, "mail")
    assert "chat_residue" not in [f.rule for f in result.findings]
    assert [f.match for f in result.exempted if f.rule == "chat_residue"] == ["Here is the revised version"]
    assert "chat_residue" in rules(text, "pr")
    assert "chat_residue" not in rules("# T\n\nIntro.\n\n" + text, "pr")  # only in the first prose block


def test_fence_on_a_list_marker_line_does_not_flip_the_document() -> None:
    text = ("## Setup\n\n1. ```bash\n   npm install --save robust-retry\n   ```\n2. Start the server. It is crucial to "
            "set the token first — otherwise it fails.\n\nThis tool will seamlessly empower your team.\n")
    assert [(f.line, f.match) for f in findings(text)] == [
        (6, "crucial"), (6, "—"), (8, "seamlessly"), (8, "empower")]


@pytest.mark.parametrize(("text", "doc_type"), [
    ("Hi Priya,\n\nThanks for the review. Here is the revised version of the runbook with your comments addressed.\n\n"
     "Best,\nTom\n", "mail"),
    ("Thanks for the review. Here is the revised version of the runbook with your comments addressed.\n", "pr"),
    ("Thanks for the review. Here is the revised version of the runbook with your comments addressed.\n", None),
    ("Here's a draft implementation of the retry logic.\n", "pr"),
])
def test_writers_own_revision_and_draft_sentences(text: str, doc_type: str | None) -> None:
    assert "chat_residue" not in rules(text, doc_type)


def test_here_is_a_draft_with_a_colon_is_still_residue() -> None:
    assert [f.match for f in findings("Here's a draft:\n\nThe plan is to ship.\n", "pr")
            if f.rule == "chat_residue"] == ["Here's a draft:"]
    assert "chat_residue" not in rules("Hi Ana,\n\nHere's a draft:\n\n- one\n", "mail")


@pytest.mark.parametrize("text", [
    "We didn't just ship features. We shipped value.\n",
    "We didn't simply fix the bug. We fixed the process.\n",
    "They didn't merely write a spec. They wrote a prototype.\n",
])
def test_two_sentence_contrast_with_just_before_the_verb(text: str) -> None:
    assert "negative_contrast" in rules(text)


def test_two_sentence_contrast_with_just_needs_the_same_verb() -> None:
    assert "negative_contrast" not in rules("We didn't just ship. We celebrated.\n")


@pytest.mark.parametrize("text", [
    "The API isn't stable yet; it's still in beta.\n",
    "She's not in the office this week; she's at the conference.\n",
    "It's not ready, it's still in review.\n",
    "They're not online, they're at the offsite.\n",
])
def test_one_sentence_status_and_place_are_not_contrasts(text: str) -> None:
    assert "negative_contrast" not in rules(text)


def test_one_sentence_contrast_still_reported() -> None:
    assert "negative_contrast" in rules("It's not a bug, it's a feature request.\n")
    assert "negative_contrast" in rules("It isn't just ready, it's battle-tested.\n")  # "just" makes it a contrast


@pytest.mark.parametrize("text", [
    "We're not just a vendor, we're your partner.\n",
    "We aren't just a vendor, we're your partner.\n",
    "You're not just a customer, you're family.\n",
    "It's not just a tool, it's a platform.\n",
])
def test_not_just_contrast_with_contractions(text: str) -> None:
    assert "negative_contrast" in rules(text)


def test_lets_not_just_is_not_a_contrast() -> None:
    assert "negative_contrast" not in rules("Let's not just ship it, we should test it first.\n")


@pytest.mark.parametrize("text", [
    "It's not a perfect fix, but the patch works.\n",
    "That's not a lot of money, but the principle matters.\n",
    "This is not a perfect fix, but the test passes.\n",
    "This is not a blocker, but the new strategy works.\n",
])
def test_concession_with_a_present_tense_verb(text: str) -> None:
    assert "negative_contrast" not in rules(text)


@pytest.mark.parametrize("text", [
    "This is not a product, but the new features.\n",
    "It's not a cost, but a few tweaks.\n",
    "This is not a product, but the missing pieces.\n",
    "This is not a bug, but a feature.\n",
])
def test_contrast_with_a_plural_noun_after_an_adjective(text: str) -> None:
    assert "negative_contrast" in rules(text)


@pytest.mark.parametrize("text", [
    "- v1.0–v1.4 — end of life\n- 2.0.0 – 2.3.1 — legacy branch\n",
    "v1.0 to v1.4 — end of life\n",
    "- 1.2 – 1.4 — old\n",
])
def test_em_dash_after_a_version_range(text: str) -> None:
    assert "em_dash" not in rules(text)


def test_em_dash_after_a_version_in_a_sentence_is_reported() -> None:
    assert rules("We moved from v1.0 to v1.4 — it was slow.\n") == ["em_dash"]
    assert rules("- 2.0.0 — legacy — mostly\n") == ["em_dash"]


@pytest.mark.parametrize("text", [
    "But what does this mean for developers? It means fewer manual steps.\n",
    "What does this mean for small teams? It means fewer manual steps.\n",
    "And what, then, is the real gap? We lack data.\n",
])
def test_self_answered_question_with_a_longer_opening(text: str) -> None:
    assert "self_answered_question" in rules(text)


def test_self_answered_question_length_limit() -> None:
    assert "self_answered_question" not in rules("What does this mean for the many small teams here? Less work.\n")


def test_am_before_i_is_not_a_sentence_start_repeat() -> None:
    assert "sentence_start_repeat" not in rules("At 9 a.m. I restarted the service. I checked the logs. I found the "
                                                "error.\n")
    assert "sentence_start_repeat" in rules("I restarted the service. I checked the logs. I found the error.\n")


def test_emoji_arrows_and_selectors() -> None:
    text = "Open Settings ➜ Privacy.\n\nℹ️ Read this first.\n\n▶️ Watch the demo.\n\n" \
        "‼️ Note.\n\nHum ♪ along.\n"
    assert [(f.line, f.match) for f in findings(text)] == [
        (3, "ℹ️"), (5, "▶️"), (7, "‼️")]
    assert "emoji" in rules("Made with ❤ in Berlin.\n")


def test_every_emoji_start_passes_the_candidate_filter() -> None:
    for cp in tx._BMP_EMOJI:
        assert lint._EMOJI_CANDIDATE.match(chr(cp)), hex(cp)


@pytest.mark.parametrize("text", [
    "## Usage\n    make deploy  # utilize the robust cache\n",
    "## Usage\n\n    make deploy  # utilize the robust cache\n",
    "---\n    make deploy  # utilize the robust cache\n",
    "<pre>\n$ tinyq status\nworkers: 4 — all robust\n</pre>\n",
])
def test_indented_code_and_pre_blocks_are_not_prose(text: str) -> None:
    assert rules(text) == []


def test_indented_line_after_a_paragraph_is_still_prose() -> None:
    assert rules("Intro text.\n    We utilize the robust cache.\n") == ["wordy_phrase", "ai_vocabulary"]


def test_double_click_is_a_literal_step() -> None:
    assert rules("1. Double-click on the installer.\n2. Follow the prompts.\n") == []


def test_many_dashes_in_one_block_are_linear() -> None:
    import time
    for text in ("a — b " * 80000 + "\n", "a — b\n" * 80000):
        start = time.monotonic()
        result = lint.lint(text)
        assert time.monotonic() - start < 4
        assert len(result.findings) == 80000
        first, last = (f.message.split('"')[1] for f in (result.findings[0], result.findings[-1]))
        assert first.startswith("a — b") and first.endswith("…")
        assert last.startswith("…") and last.endswith("a — b")
