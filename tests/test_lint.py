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
            if f.rule == "chat_residue"] == ["Here's a draft"]
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


# ---------------------------------------------------------------- set 9 lint review


def residue(text: str, doc_type: str | None = None) -> list[str]:
    return [f.match for f in findings(text, doc_type) if f.rule == "chat_residue"]


@pytest.mark.parametrize("rule_line", ["---", "***", "___", "- - -"])
def test_preamble_before_a_rule_and_a_mail(rule_line: str) -> None:
    text = f"Here's a sincere apology note you can send to your team:\n\n{rule_line}\n\nSubject: An apology\n\nHi all,\n"
    assert residue(text) == ["Here's a sincere apology note you can send"]
    text = f"Here's a polished version of your email:\n\n{rule_line}\n\nHi Sam,\n\nThanks.\n"
    assert residue(text, "mail") == ["Here's a polished version"]  # a mail follows: reported in mail too
    # Before a rule and a list, a revision lead-in in mail is still exempt.
    assert residue(f"Here is the revised version of the agenda:\n\n{rule_line}\n\n- Budget\n", "mail") == []


@pytest.mark.parametrize(("lead", "match"), [
    ("Here's your revised email:", "Here's your revised email"),
    ("Here's the revised email:", "Here's the revised email"),
    ("Here's an updated version of your email:", "Here's an updated version"),
    ("Here's a simplified version:", "Here's a simplified version"),
    ("Here's a condensed version:", "Here's a condensed version"),
    ("Here's a reworked version:", "Here's a reworked version"),
    ("Here's a friendlier version:", "Here's a friendlier version"),
    ("Here's the corrected text:", "Here's the corrected text"),
    ("Here's a draft email:", "Here's a draft email"),
    ("Here's a draft reply:", "Here's a draft reply"),
    ("Here's a possible response:", "Here's a possible response"),
    ("Here's a draft email to your landlord:", "Here's a draft email"),
    ("Here's a draft:", "Here's a draft"),
    ("Here's a draft you can send:", "Here's a draft you can send"),
    ("Here's the updated invitation:", "Here's the updated invitation"),
])
def test_revision_lead_ins_and_mail_offers_before_a_greeting(lead: str, match: str) -> None:
    text = f"{lead}\n\nDear Mr. Patel,\n\nThank you for your patience.\n"
    for doc_type in (None, "mail", "pr"):
        assert residue(text, doc_type) == [match], (lead, doc_type)


@pytest.mark.parametrize(("text", "doc_type"), [
    # Documentation lead-ins and the writer's own sentences.
    ("Here are the options you can use with `x`:\n\n- `-v`: verbose\n", None),
    ("Here are the updated numbers:\n\n| Q | Revenue |\n|---|---|\n| Q3 | 4.2 |\n", "pr"),
    ("Here's the updated schedule:\n\n- Monday: kickoff\n", None),
    ("Here's a draft reply:\n\nThe plan is to ship on Friday.\n", "pr"),  # no mail follows
    ("Here's a draft email to the team:\n\n```\nfoo\n```\n", "manual"),  # a mail noun alone needs a greeting
    ("Here's a sample email:\n\nDear customer,\n\nThanks.\n", "manual"),  # an example in a support guide
    ("Here is the email template you can copy for outage notices:\n\n```text\nHi all,\n```\n", "manual"),
    ("Here is the email template you can copy for outage notices:\n\nHi all,\n\nWe are down.\n", "manual"),
    ("Here is the message you can use to test the webhook:\n\n```json\n{}\n```\n", None),
    ("Here's the updated email address:\n\nsupport at example dot com\n", "pr"),
    ("Hi Ana,\n\nHere's a draft email:\n\nDear Mr. Patel,\n", "mail"),  # after the writer's greeting
])
def test_lead_ins_that_are_not_preambles_set9(text: str, doc_type: str | None) -> None:
    assert residue(text, doc_type) == []


def test_here_is_a_draft_follows_the_preamble_rules() -> None:
    # "Here's a draft:" moved from closing-courtesies.txt to the pattern: reported in mail when a mail follows.
    text = "Here's a draft:\n\nDear Mr. Patel,\n\nThanks.\n"
    assert residue(text, "mail") == ["Here's a draft"]
    result = lint.lint("Here's a draft:\n\nThe plan is to ship.\n", "mail")
    assert "chat_residue" not in [f.rule for f in result.findings]
    assert [f.match for f in result.exempted if f.rule == "chat_residue"] == ["Here's a draft"]
    assert all("here's a draft" not in e.phrase.lower() for e in tx.load_list("closing-courtesies"))


def test_interjection_preamble_with_more_sentences_before_the_colon() -> None:
    text = ("Sure — here's a draft you can send to your landlord. It's polite but firm, and it documents the issue "
            "clearly:\n\n---\n\nSubject: Heating\n\nDear Mr. Okafor,\n")
    assert residue(text) == ["Sure — here's a draft you can send"]
    text = ("Certainly! Here's a polished version of your email that keeps your main points but sounds a bit more "
            "professional and concise:\n\n---\n\nHi Dana,\n")
    assert residue(text, "mail") == ["Certainly! Here's a polished version"]


@pytest.mark.parametrize(("text", "match"), [
    ("This isn't a tool. It's not a framework. It's a mindset.\n", "It's not a framework. It's"),
    ("It's not about speed. It's not about cost. It's about trust.\n", "It's not about cost. It's"),
    ("We didn't build a tool. We didn't build a framework. We built a culture.\n",
     "We didn't build a framework. We built"),
])
def test_chained_two_sentence_contrasts(text: str, match: str) -> None:
    assert [f.match for f in findings(text) if f.rule == "negative_contrast"] == [match]


def test_two_chained_contrasts_are_both_reported() -> None:
    text = "It isn't a tool. It's a mindset. It isn't a phase. It's a movement.\n"
    assert [f.match for f in findings(text) if f.rule == "negative_contrast"] == [
        "It isn't a tool. It's", "It isn't a phase. It's"]


@pytest.mark.parametrize("text", [
    "Remote work isn't a perk. It's a paradigm shift.\n",
    "Ledgerly Flow isn't just another accounting tool. It's a complete rethinking of how you work.\n",
    "Good design isn't decoration. It's communication.\n",
    "What we need isn't more meetings. It's fewer, better ones.\n",
    "Most teams don't need Kubernetes. They need a single server.\n",
])
def test_two_sentence_contrast_with_a_noun_phrase_subject(text: str) -> None:
    assert "negative_contrast" in rules(text)


@pytest.mark.parametrize("text", [
    "Let's not overthink it. It's a config change.\n",
    "That's not all. It's also cheap.\n",
    "In March we didn't ship. We shipped in April.\n",
    "Your original subscription isn't affected. It's active until October 29, 2025.\n",
    "The old token isn't valid. It's expired since Monday.\n",
    "The flag isn't enabled. It's disabled by default.\n",
])
def test_two_sentence_contrast_status_and_other_subjects(text: str) -> None:
    assert "negative_contrast" not in rules(text)


def test_todays_opener_needs_modifiers_and_the_noun_to_end_the_phrase() -> None:
    assert "stock_phrase" not in rules("In today's call we reviewed the business plan for Q3.\n")
    assert "stock_phrase" not in rules("In today's standup Priya reviewed market data.\n")
    for text in ("In today's rapidly evolving healthcare landscape, teams ship.\n",
                 "In today's fast-paced digital landscape, the way we work has changed.\n",
                 "In today's cloud-native world, apps are distributed.\n",
                 "Small firms struggle in today's competitive market.\n",
                 "*In today's digital world*, we ship.\n",
                 "| Opener | \"In today's rapidly evolving healthcare landscape\" |\n"):
        assert "stock_phrase" in rules(text), text


@pytest.mark.parametrize("text", [
    "In this policy:\n\n(a) \"Hybrid working\" means working from home;\n\n(b) \"Office\" means the site.\n",
    "The tenant must:\n\na) pay rent on time;\n\nb) keep the flat clean.\n",
    "Exceptions:\n\n(i) medical leave;\n\n(ii) jury duty.\n",
    "The steps are:\n\n(1) apply;\n\n(2) wait.\n",
])
def test_decorative_colon_before_lettered_paragraphs(text: str) -> None:
    assert "decorative_colon" not in rules(text)


def test_decorative_colon_before_an_ordinary_paragraph_is_still_reported() -> None:
    assert "decorative_colon" in rules("Consider this:\n\nA plain paragraph (a) with letters.\n")


def test_pathological_names_and_end_marks_are_linear() -> None:
    import time
    for text in ("A." * 20000 + "\n", "A-" * 20000 + "\n", "C+" * 20000 + "\n", "Foo-" * 10000 + "\n",
                 "." * 40000 + "a\n", "!" * 40000 + "a\n"):
        start = time.monotonic()
        lint.lint(text)
        assert time.monotonic() - start < 2, text[:6]
    assert "negative_contrast" in rules("React isn't a framework; it's a library.\n")
    assert "negative_contrast" in rules("(React isn't a framework; it's a library.)\n")


@pytest.mark.parametrize("text", [
    "`-l`, `--level` LEVEL — show only records at LEVEL or above.\n",
    "`-m`, `--match` KEY=PATTERN — keep records whose field KEY matches.\n",
    "`--fields` LIST — comma-separated fields to print.\n",
    "- `--color` [WHEN] — colorize the output.\n",
    "- `--out` <path> — write to a file.\n",
    "- `--files` FILE... — the inputs.\n",
])
def test_em_dash_after_an_option_with_a_placeholder(text: str) -> None:
    assert "em_dash" not in rules(text)


def test_em_dash_after_a_word_that_is_not_a_placeholder_is_reported() -> None:
    assert rules("`retry()` now waits — it was too eager.\n") == ["em_dash"]
    assert rules("LEVEL — the level to show.\n") == ["em_dash"]  # no option before it


def test_em_dash_on_a_man_page_name_line() -> None:
    text = "# logsift(1)\n\n## NAME\n\nlogsift — filter and summarize structured log files\n\n## DESCRIPTION\n\n" \
        "It reads logs — and writes them.\n"
    assert [(f.line, f.rule) for f in findings(text)] == [(9, "em_dash")]
    assert "em_dash" not in rules("## NAME\n\ngrep, egrep — print lines that match patterns\n")
    assert rules("## Name\n\nThe tool reads logs — and writes them.\n") == ["em_dash"]
    assert rules("## Usage\n\nlogsift — filter log files\n") == ["em_dash"]


@pytest.mark.parametrize("text", [
    "- Grace: confirm Spark operator compatibility with data team — Fri 8 Mar\n",
    "- Ivo: estimate egress savings from region move — next meeting\n",
    "- Ben: snapshot then delete unattached EBS volumes — this week\n",
    "- Sun-hee + Grace: compare on-call pay with other groups — before HR meeting\n",
    "- Fix the flaky alert — Marco\n",
    "- Fix the flaky alert — @marco, @ana\n",
    "- Rotate the keys — by 2024-03-08\n",
    "Platform team weekly — Tue 5 Mar 2024, 10:00–10:45\nAttendees: Grace, Ivo\n",
    "On-call handoff — wk 46 (Nov 11–18)\nFrom: dmitri\n",
    "## Sprint review — Fri 8 Mar\n",
])
def test_em_dash_before_a_date_due_time_or_owner_tag(text: str) -> None:
    assert "em_dash" not in rules(text)


@pytest.mark.parametrize("text", [
    "We finally shipped the new parser — last week.\n",  # a sentence, not a title line
    "The parser failed. We fixed it — this week\n",  # a sentence ends before the dash
    "The team agreed to revisit the plan — next week\nwe will decide who owns it.\n",  # a wrapped sentence
    "Intro line.\nThe team agreed to revisit the plan — next week\n",  # not the first line of the paragraph
    "- We rebuilt the parser — it was too slow\n",
    "- We rebuilt the parser — and it is fast now\n",
])
def test_em_dash_before_ordinary_words_is_still_reported(text: str) -> None:
    assert "em_dash" in rules(text)


def test_more_than_just_message_and_list_messages_are_clean() -> None:
    import re
    got = [f for f in findings("It is more than just a tool.\n") if f.rule == "stock_phrase"]
    assert [f.message for f in got] == [
        'Stock phrase "more than just": say what more it is, only from the original or material; otherwise keep and ask '
        "(deleting it reverses the claim). Keep any fact that appears only here."]
    for rule, name, _types in lint.LIST_RULES:
        for entry in tx.load_list(name):
            message = lint._list_message(rule, entry.phrase, entry.note or lint.RULES[rule][1])
            assert not re.search(r"\.\.|[;:,]\.|\s\.", message), message
            assert message.count("(") == message.count(")"), message


# ---------------------------------------------------------------- set 10 lint review


@pytest.mark.parametrize("text", [
    # A person's existing letter or mail, shared with a lead-in (finding 1).
    "Here is the letter my grandfather wrote in 1944:\n\nDear Mary,\n\nThe war is long.\n",
    "Here's the reply I got from Stripe support:\n\nHi Dana,\n\nThanks for reaching out.\n",
    "Here's a quick note from our CEO:\n\nDear team,\n\nWe did it.\n",
    "Here is a letter we received from a reader in Ohio:\n\nDear editor,\n\nI disagree.\n",
    "Here's the email that went out to customers on Monday:\n\nSubject: Planned maintenance\n\nHi there,\n",
    "Here's the email Sam sent:\n\nHi all,\n\nThe build is green.\n",
    "Here's a letter written by my grandfather:\n\nDear Mary,\n",
    "Here's the updated note from HR:\n\nDear all,\n\nThe office is closed.\n",
    "Here's the email:\n\nDear Mr. Patel,\n\nThanks.\n",  # no sign of a draft
    "Sure, here are the notes from Tuesday's call:\n\n- one\n- two\n",  # an interjection, then someone's notes
])
def test_shared_mail_is_not_an_assistant_preamble(text: str) -> None:
    for doc_type in (None, "mail", "essay"):
        assert residue(text, doc_type) == [], (text, doc_type)


@pytest.mark.parametrize(("lead", "match"), [
    ("Here's a draft email to your landlord:", "Here's a draft email"),
    ("Here's a possible response:", "Here's a possible response"),
    ("Here's the suggested reply:", "Here's the suggested reply"),
    ("Here's your reply:", "Here's your reply"),
    ("Here's a draft I've put together:", "Here's a draft"),
    ("Here's an email I wrote for you:", "Here's an email"),  # spoken to the requester
    ("Certainly! Here's the email:", "Certainly! Here's the email"),
    ("Sure! Here's the letter you asked for:", "Sure! Here's the letter"),
    ("Here's a reply you can send to Jordan:", "Here's a reply you can send"),
])
def test_assistant_mail_drafts_are_still_preambles(lead: str, match: str) -> None:
    assert residue(f"{lead}\n\nDear Mr. Patel,\n\nThank you for your patience.\n", "mail") == [match]


@pytest.mark.parametrize(("text", "match"), [
    ("Remote work isn't a perk; it's a paradigm shift.\n", "Remote work isn't a perk; it's"),
    ("Remote work isn't a perk—it's a paradigm shift.\n", "Remote work isn't a perk—it's"),
    ("Good onboarding isn't a checklist, it's a relationship.\n", "Good onboarding isn't a checklist, it's"),
    ("He isn't a coward; he's a hero.\n", "He isn't a coward; he's"),
    ("He said it wasn't his fault; it was the vendor's.\n", "it wasn't his fault; it was"),
    ("React isn't a framework; it's a library.\n", "React isn't a framework; it's"),
])
def test_one_sentence_contrast_with_a_short_subject(text: str, match: str) -> None:
    assert [f.match for f in findings(text) if f.rule == "negative_contrast"] == [match]


@pytest.mark.parametrize("text", [
    "We think Remote work isn't a perk; it's a shift.\n",  # two capitalized words in mid-sentence are not a subject
    "If it isn't broken, it's fine to ship.\n",
    # The semicolon join of a denied verb is the fix SKILL.md recommends for a two-sentence contrast.
    "We didn't need a new tool; we needed a shared way to use the old one.\n",
])
def test_one_sentence_forms_that_are_not_reported(text: str) -> None:
    assert "negative_contrast" not in rules(text)


@pytest.mark.parametrize("text", [
    "This isn't the first time. It's happened twice this quarter.\n",
    "This isn't a regression. It's been broken since 2.3.\n",
    "This isn't the first time; it's happened twice.\n",
    "It isn't clear what caused the spike. It's likely related to the 14:02 deploy.\n",
    "It is not possible to delete a project. It is possible to archive it.\n",
    "This isn't a bug. It's possible that the cache is stale.\n",
    "It isn't clear why it failed; it's likely the cache.\n",
    "Please don't use the old endpoint. It uses a deprecated auth flow.\n",
    "Just don't run it twice. It runs a full reindex.\n",
    "He wasn't the one who called; she was.\n",
])
def test_negative_contrast_false_positives_set10(text: str) -> None:
    assert "negative_contrast" not in rules(text)


@pytest.mark.parametrize("text", [
    "**This isn't a tool. It's a mindset.**\n",
    "- **This isn't a tool. It's a mindset.**\n",
    "_This isn't a tool. It's a mindset._\n",
    "We tried.  This isn't a tool. It's a mindset.\n",
    "> **Note:** It isn't a bug. It's a feature.\n",
    "**This isn't a tool.** **It's a mindset.**\n",
    "Summary: this matters. Remote work isn't a perk. It's a paradigm shift.\n",
])
def test_two_sentence_contrast_after_emphasis_spaces_or_a_label(text: str) -> None:
    assert "negative_contrast" in rules(text)


def test_two_sentence_contrast_subject_does_not_cross_a_period() -> None:
    got = [f.match for f in findings("We tried.  This isn't a tool. It's a mindset.\n") if f.rule == "negative_contrast"]
    assert got == ["This isn't a tool. It's"]


@pytest.mark.parametrize("text", [
    "[UPDATE — the fix is now live for all customers.]\n",
    "(FYI — the deploy moved to 5pm because QA found a blocker.)\n",
    "_IMPORTANT_ — back up your database before you upgrade.\n",
    "**[UPDATE — the fix is now live.]**\n",
    "(EDIT — I was wrong about the cache; it was DNS.)\n",
])
def test_dash_after_a_word_with_no_code_is_reported(text: str) -> None:
    assert "em_dash" in rules(text)


@pytest.mark.parametrize("text", [
    "**[COLD OPEN — ambient sound: wind, birds, distant traffic]**\n",
    "**[THEME MUSIC — 10 sec, then under]**\n",
    "[MUSIC OUT — 5 sec]\n",
])
def test_dash_after_an_all_caps_stage_direction_label(text: str) -> None:
    assert "em_dash" not in rules(text, "script")


def test_option_dash_check_is_linear_on_a_long_placeholder_run() -> None:
    import time
    text = "`a` " + "A " * 8000 + "— x " * 8000 + "\n"
    start = time.monotonic()
    got = rules(text)
    assert time.monotonic() - start < 2
    assert got.count("em_dash") == 7999  # only the first dash follows the placeholders
    assert rules("`-l`, `--level` LEVEL — show only records — at that level.\n") == ["em_dash"]


@pytest.mark.parametrize("text", [
    "## Slide 1 — Title\n",
    "## Section 3 — Payment terms\n",
    "## Session 2 — Hands-on lab\n",
    "## Episode 12 — The milk train\n",
    "**SEGMENT 1 — The history (~6 min)**\n",
    "## Act II — The return\n",
    "## Unit 5 — Fractions\n",
    "## Exercise 4.2 — Loops\n",
    "## Milestone 2 — Beta\n",
    "## Round 2 — Interviews\n",
    "## Quest 7 — The cave\n",  # any capitalized word and a number, on a title line
    "## Units 3–5 — Review\n",
    "## 2026-11-13 (Thu) — Miniprep and digest\n",
    "## Nov 13 (Thu) — Miniprep\n",
])
def test_em_dash_after_a_numbered_label_set10(text: str) -> None:
    assert "em_dash" not in rules(text)


@pytest.mark.parametrize("text", [
    "Python 3.9 – the oldest we support – is end of life in October.\n",  # a sentence after a generic label
    "Over 50 — and counting\n",
    "In 2024 — the year we shipped\n",
])
def test_em_dash_after_a_number_that_is_not_a_label(text: str) -> None:
    assert "em_dash" in rules(text)


def test_script_speaker_labels_are_not_bold_label_lists() -> None:
    dialogue = "**G:** So we're standing in a field.\n\n**O:** A very muddy field.\n\n**G:** Welcome.\n"
    assert "bold_label_list" not in rules(dialogue)  # turns of a dialogue, in every doc type
    interview = "**Q:** Why?\n\n**A:** Because.\n\n**Q:** How?\n\n**A:** Like this.\n"
    assert "bold_label_list" not in rules(interview, "article")
    pair = "**MAYA:** Wait. You knew?\n\n**TOM (V.O.):** I always knew.\n"
    assert rules(pair).count("bold_label_list") == 2
    result = lint.lint(pair, "script")
    assert "bold_label_list" not in [f.rule for f in result.findings]
    assert [f.rule for f in result.exempted] == ["bold_label_list"] * 2
    # Summary labels are still reported in a script.
    assert rules("**Hook detail:** a joke.\n\n**Main point:** the story.\n", "script").count("bold_label_list") == 2


def test_bold_label_list_message_names_paragraphs_and_items() -> None:
    para = [f.message for f in findings("**What Happened**: the disk filled.\n\n**Why**: logs grew.\n")]
    assert para and all(m.startswith("Paragraph starts with a bold label") for m in para)
    items = [f.message for f in findings("- **Speed**: fast.\n- **Cost**: low.\n")]
    assert items and all(m.startswith("Item starts with a bold label") for m in items)


def test_heavy_bold_skips_a_label_on_each_line() -> None:
    header = "**Status:** Final\n**Author:** Sam\n**Severity:** SEV-2\n**Duration:** 47 minutes\n"
    assert "heavy_bold" not in rules(header)
    assert "heavy_bold" in rules("**Status:** Final, **a** and **b** and **c**\n")
    assert "heavy_bold" in rules("A **b** c **d** e **f** g.\n")


@pytest.mark.parametrize("text", [
    "To the Graduate Admissions Committee:\n\nI am writing to recommend Ana.\n",
    "To the editor:\n\nI disagree.\n",
    "To the hiring manager:\n\nI am applying.\n",
])
def test_to_the_salutation_is_not_a_decorative_colon(text: str) -> None:
    assert "decorative_colon" not in rules(text, "formal")


def test_to_the_point_is_still_a_decorative_colon() -> None:
    assert "decorative_colon" in rules("To the point:\n\nWe ship on Friday.\n")


def test_offer_about_the_draft_after_the_mail_is_reported_in_mail() -> None:
    text = ("Here's a polished version of your email:\n\n---\n\nHi Dana,\n\nThe report is attached.\n\nBest,\nSam\n\n"
            "---\n\nLet me know if you'd like me to adjust the tone or make it more concise!\n")
    assert residue(text, "mail") == ["Here's a polished version", "Let me know if you'd like"]
    # After the sign-off, without a thematic break.
    text = "Hi Dana,\n\nThe report is attached.\n\nBest,\nSam\n\nWould you like me to make the tone more casual?\n"
    assert residue(text, "mail") == ["Would you like me to"]
    # Offers that no word list has.
    text = ("Hi all,\n\nWe are sorry.\n\nWarmest regards,\nThe Team\n\n---\n\nFeel free to adjust the dates or tone. "
            "Would you like a shorter version for SMS as well?\n")
    assert residue(text, "mail") == ["Feel free to", "Would you like"]


@pytest.mark.parametrize("text", [
    # The writer's own offers: inside the mail, or not about the draft.
    "Hi Dana,\n\nThe report is attached. Let me know if you'd like me to adjust the tone of the summary.\n\n"
    "Best,\nSam\n",
    "Hi Dana,\n\nThe report is attached.\n\nBest,\nSam\n\nP.S. Let me know if you'd like a printed version.\n",
    "Hi Dana,\n\nThe agenda is below.\n\nThanks,\nSam\n\nP.S. Let me know if you'd like the draft agenda early.\n",
    "Thanks!\n\nLet me know if you'd like a different version of the schedule.\n",  # "Thanks!" alone is no sign-off
])
def test_writers_offers_in_mail_are_still_exempt(text: str) -> None:
    assert residue(text, "mail") == []


def test_editing_verb_with_another_object_after_a_rule_is_not_an_offer() -> None:
    assert residue("# Setup\n\nInstall it.\n\n---\n\nFeel free to tweak the config to your liking.\n") == []
    # After a drafted mail (a greeting before the rule), an editing verb on "it" is an offer about the draft.
    assert residue("Hi Dana,\n\nThe report is attached.\n\n---\n\nFeel free to personalize it with your own "
                   "projects!\n") == ["Feel free to"]


# ---------------------------------------------------------------- set 11


@pytest.mark.parametrize(("text", "doc_type"), [
    # A README, a style guide and a template end with a note to their readers after a thematic break.
    ("# csvtrim\n\nTrims whitespace in CSV files.\n\n## Install\n\nRun `pip install csvtrim`.\n\n---\n\n"
     "If you would like a shorter version of this guide, see QUICKSTART.md. If you'd like a different version of the "
     "binary for ARM, see Releases.\n", "manual"),
    ("# Error message style\n\nSay what happened and what to do next.\n\n---\n\nFeel free to suggest clearer wording "
     "for any message in this list by opening a pull request.\n", None),
    ("# .editorconfig template\n\nCopy `.editorconfig` into the root of your repository.\n\n---\n\nThis file is only "
     "a starting point. Feel free to tweak it for your team.\n", None),
    ("# Voice and tone guide\n\nOur product voice is plain.\n\n---\n\nFeel free to post in #writing if you're unsure "
     "about tone or wording.\n", "manual"),
    ("## Notes from the workshop\n\nWe covered pacing and tone.\n\n---\n\nWould you like to join the next session on "
     "phrasing? Sign up below.\n", None),
])
def test_readers_notes_after_a_rule_are_not_assistant_offers(text: str, doc_type: str | None) -> None:
    assert residue(text, doc_type) == []


@pytest.mark.parametrize("header", [
    "From: Ana Ruiz\nSent: Monday, November 3, 2025 9:14 AM\nTo: Sam Lee\nSubject: Board deck",
    "-----Original Message-----\nFrom: Ana Ruiz",
    "On Mon, Nov 3, 2025 at 9:14 AM Ana Ruiz <ana@example.com>\nwrote:",
])
def test_earlier_messages_in_a_pasted_thread_are_not_after_the_sign_off(header: str) -> None:
    text = (f"Hi Ana,\n\nThe board deck is attached.\n\nBest,\nSam\n\n{header}\n\nAttached is my first pass. Let me know "
            "if you'd like me to adjust the tone for the board version.\n\nThanks,\nAna\n")
    assert residue(text, "mail") == []


def test_a_new_greeting_starts_a_new_message() -> None:
    text = ("Hi Ana,\n\nThe deck is attached.\n\nBest,\nSam\n\nHi Sam,\n\nLet me know if you'd like me to adjust the "
            "tone for the board version.\n\nThanks,\nAna\n")
    assert residue(text, "mail") == []
    # The offer after the last sign-off is still the assistant's.
    assert residue(text + "\nWould you like me to make it more formal?\n", "mail") == ["Would you like me to"]


@pytest.mark.parametrize(("text", "match"), [
    # No greeting or sign-off before the rule: words about a draft, or the assistant offering to change it.
    ("# Launch post\n\nWe shipped v2.\n\n---\n\nFeel free to adjust the tone of this draft.\n", ["Feel free to"]),
    ("# Launch post\n\nWe shipped v2.\n\n---\n\nWant me to make it shorter?\n", ["Want me to"]),
    ("# Launch post\n\nWe shipped v2.\n\n---\n\nI can also rewrite the email in a friendlier tone.\n",
     ["I can also"]),
    # Once the paragraph is assistant chat, its other offers are too.
    ("# Post\n\nBody.\n\n---\n\nFeel free to personalize it with your own projects! Let me know if you'd like a "
     "shorter version.\n", ["Feel free to", "Let me know if you'd like"]),
])
def test_assistant_offers_after_a_rule_without_a_mail(text: str, match: list[str]) -> None:
    assert residue(text) == match


def test_offers_after_a_rule_in_mail_and_after_a_drafted_mail() -> None:
    # In mail, and after a greeting or sign-off in any doc type, any talk about the draft after the rule.
    assert residue("Team,\n\nThe offsite moved to Thursday.\n\nPriya\n\n---\n\nFeel free to tweak it.\n", "mail") \
        == ["Feel free to"]
    assert residue("Hi team,\n\nThe offsite moved to Thursday.\n\n---\n\nFeel free to tweak it.\n") == ["Feel free to"]
    assert residue("Team,\n\nThe offsite moved to Thursday.\n\nPriya\n\n---\n\nFeel free to tweak it.\n") == []
    text = ("Hi Dana,\n\nThe report is attached.\n\nBest,\nSam\n\n---\n\nLet me know if you'd like me to adjust the tone "
            "or make it more concise!\n")
    assert residue(text, "mail") == ["Let me know if you'd like"]


def contrasts(text: str) -> list[str]:
    return [f.match for f in findings(text) if f.rule == "negative_contrast"]


@pytest.mark.parametrize(("text", "match"), [
    ("🚀 This isn't just an update. It's a revolution.\n", "This isn't just an update. It's"),
    ("We shipped v2! 🎉 This isn't just an update. It's a new era.\n", "This isn't just an update. It's"),
    ("**The big shift**\nThis isn't a tool. It's a mindset.\n", "This isn't a tool. It's"),
    ("- **Culture over tools**\n  Remote work isn't a perk, it's a paradigm shift.\n", "Remote work isn't a perk, it's"),
    ("💡 Remote work isn't a perk. It's a paradigm shift.\n", "Remote work isn't a perk. It's"),
    ("The truth is simple: it isn't a tool. It's a mindset.\n", "it isn't a tool. It's"),
    ("Here's the truth: we don't sell software. We sell outcomes.\n", "we don't sell software. We sell"),
    ("Hi team\nWe don't sell software. We sell outcomes.\n", "We don't sell software. We sell"),
    ("Shipped! 👨‍👩‍👧‍👦 This isn't a tool. It's a mindset.\n", "This isn't a tool. It's"),
])
def test_contrast_after_emoji_a_line_break_or_a_colon(text: str, match: str) -> None:
    assert contrasts(text) == [match]


@pytest.mark.parametrize("text", [
    "Here's the thing nobody tells you: it's not hard. It's barely even cooking.\n",  # an adjective is denied
    "We tested it and it isn't a tool. It's a mindset.\n",  # a lower-case pronoun not after a colon
    "Yesterday I didn't ship the fix. I shipped a workaround.\n",  # the pronoun does not start the sentence
    "→ This isn't a tool. It's a mindset.\n",  # an arrow is not an emoji
])
def test_contrast_needs_a_sentence_start(text: str) -> None:
    assert contrasts(text) == []


def test_emoji_before_an_interjection_starts_a_sentence() -> None:
    assert residue("🎉 Sure! Here's what changed.\n") == ["Sure!"]


@pytest.mark.parametrize("text", [
    "**Speaker 1:** So when did you start?\n\n**Speaker 2:** In 2019.\n\n**Speaker 1:** And the first job?\n",
    "**Participant 3:** I never use it.\n\n**Moderator:** Why not?\n\n**Participant 3:** I don't trust it.\n",
    "**Caller 1:** Is the road open?\n\n**Host:** Not yet.\n\n**Caller 1:** Thanks.\n",
    "**P2:** Fine.\n\n**P1:** Good.\n\n**P2:** Done.\n",
    "**MAYA:** Where were you?\n\n**DEV (into the phone, whispering):** I can't talk.\n\n**MAYA:** Dev.\n",
])
def test_numbered_speakers_and_long_notes_are_dialogue_turns(text: str) -> None:
    got = rules(text)
    assert "bold_label_list" not in got
    assert "sentence_start_repeat" not in got


def test_a_bold_label_is_not_the_first_word_of_a_sentence() -> None:
    assert "sentence_start_repeat" in rules("**Note:** We ran it.\n\n**Tip:** We fixed it.\n\n**Warning:** We shipped it.\n")
    # Summary labels with a number are still reported outside script, and exempted in script.
    steps = "**Step 1:** Install it.\n\n**Step 2:** Configure it.\n"
    assert rules(steps).count("bold_label_list") == 2
    assert "bold_label_list" not in rules(steps, "script")


@pytest.mark.parametrize("text", [
    "INT. KITCHEN — NIGHT\n\nMaya stands at the counter.\n",
    "EXT. PARKING LOT – DAY\n",
    "**INT. MAYA'S APARTMENT — CONTINUOUS**\n",
    "INT./EXT. CAR — MOVING — DAY\n",
    "I/E. VAN — NIGHT\n",
])
def test_scene_headings_are_not_spliced_clauses(text: str) -> None:
    assert "em_dash" not in rules(text, "script")


def test_a_sentence_after_a_scene_heading_dash_is_still_checked() -> None:
    assert "em_dash" in rules("INT. KITCHEN — Maya slams the door. She leaves.\n", "script")


@pytest.mark.parametrize("text", [
    "## Monday (Mar 3) — Workshops\n",
    "- Friday (Nov 14) — Code freeze\n",
    "Thursday (6 Feb) — Committee meeting\n",
    "Tue (11/12) — retro\n",
    "## Mar 3 (Mon) — Workshops\n",
])
def test_weekday_with_a_date_in_parentheses_is_a_stamp(text: str) -> None:
    assert "em_dash" not in rules(text)


def test_words_in_parentheses_after_a_weekday_are_not_a_stamp() -> None:
    assert "em_dash" in rules("Friday (the day we ship) — big day.\n")


def test_tamp_your_is_not_tame_your() -> None:
    assert "metaphor_verb" not in rules("Tamp your coffee evenly, then lock the portafilter.\n")
    for text in ("This tool will tame your inbox.\n", "It tames your backlog.\n", "We tamed your queue.\n",
                 "Taming your logs is easy.\n"):
        assert "metaphor_verb" in rules(text)


@pytest.mark.parametrize("text", [
    "To all staff:\n\nThe office will close at noon on Friday.\n",
    "To All Residents of Building C:\n\nThe water will be off on Monday.\n",
    "To all concerned:\n\nThe audit is complete.\n",
])
def test_to_all_salutation_is_not_a_decorative_colon(text: str) -> None:
    assert "decorative_colon" not in rules(text)


def test_to_all_of_this_is_still_a_decorative_colon() -> None:
    assert "decorative_colon" in rules("To all of this:\n\nWe say no.\n")


@pytest.mark.parametrize(("text", "match"), [
    ("Below is a polished version of your email:\n\nHi Mark,\n\nThanks for the contract.\n\nBest,\nAnna\n",
     "Below is a polished version"),
    ("I've revised your email to sound more confident:\n\nHi Mark,\n\nThanks for the contract.\n",
     "I've revised your email"),
    ("Below is a draft email to your landlord:\n\n---\n\nDear Mr. Patel,\n\nThe heat is out.\n", "Below is a draft email"),
    ("Sure! I have polished your cover letter:\n\nDear hiring manager,\n\nI am applying.\n",
     "Sure! I have polished your cover letter"),
])
def test_below_is_and_ive_revised_preambles(text: str, match: str) -> None:
    assert residue(text, "mail") == [match]
    assert residue(text) == [match]


@pytest.mark.parametrize("text", [
    "Below is an updated summary of the API:\n\n- `get`\n- `put`\n",  # no mail follows
    "Below is the full text of the letter:\n\nDear Sirs,\n\nWe object.\n",  # not offered as a draft
    "Below is the email I sent to the landlord:\n\nDear Mr. Patel,\n\nThe heat is out.\n",  # a sent mail
    "Below is a sample reply:\n\nHi there,\n\nThanks for writing.\n",  # an example in a support guide
    "I've revised your email address:\n\nHi Mark,\n\nIt is mark@example.com now.\n",  # not a text
    "I've revised your draft and left comments.\n\nHi Mark,\n\nThanks.\n",  # no colon
    "Hi Mark,\n\nI've revised your draft:\n\nHi team,\n\nThe launch moved.\n",  # after a greeting
])
def test_below_is_and_ive_revised_that_are_not_preambles(text: str) -> None:
    assert residue(text) == []


@pytest.mark.parametrize(("text", "rule", "match"), [
    ("The scheduler doesn't care that rows went missing.\n", "personification", "The scheduler doesn't care"),
    ("The logs don't care who you are.\n", "personification", "The logs don't care"),
    ("Don't hesitate to reach out if you have any questions.\n", "chat_residue", "Don't hesitate to"),
    ("Remember, onboarding isn't a sprint; it's a marathon.\n", "negative_contrast",
     "Remember, onboarding isn't a sprint; it's"),
    ("This guide provides a comprehensive overview of the API.\n", "stock_phrase", "provides a comprehensive overview"),
])
def test_trial_misses_set11(text: str, rule: str, match: str) -> None:
    assert match in [f.match for f in findings(text) if f.rule == rule]


@pytest.mark.parametrize("text", [
    "The cache doesn't know about the new key.\n",  # what a program has no data for
    "The app doesn't remember your settings.\n",
    "Remember, if it isn't tested, it's broken.\n",  # a condition
    "Remember, the office isn't open on Monday; it's closed.\n",  # a status
    "Please remember, work isn't a race; it's a habit.\n",  # the reminder does not open the sentence
])
def test_trial_look_alikes_set11(text: str) -> None:
    got = rules(text)
    assert "personification" not in got and "negative_contrast" not in got


def test_comprehensive_overview_message_asks_for_the_coverage() -> None:
    [f] = [f for f in findings("The report offers a comprehensive overview of costs.\n") if f.rule == "stock_phrase"]
    assert "say what it covers, only from the original or material; otherwise keep and ask" in f.message
