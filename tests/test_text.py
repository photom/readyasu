from __future__ import annotations

import readyasu_text as tx


def spans(text: str) -> list[str]:
    return [text[s:e] for s, e in tx.split_sentences(text)]


def test_split_basic() -> None:
    assert spans("One. Two! Three?") == ["One.", "Two!", "Three?"]


def test_split_keeps_abbreviations_and_decimals() -> None:
    text = "See e.g. the docs. Version 3.5 is out. Dr. Smith agreed."
    assert spans(text) == ["See e.g. the docs.", "Version 3.5 is out.", "Dr. Smith agreed."]


def test_split_lowercase_after_period_is_not_boundary() -> None:
    assert spans("Use the cfg. file here. Then stop.") == ["Use the cfg. file here.", "Then stop."]


def test_mask_code_and_urls() -> None:
    masked = tx.mask("Run `rm -rf x` at https://example.com/a now.")
    assert "rm" not in masked and "example" not in masked
    assert len(masked) == len("Run `rm -rf x` at https://example.com/a now.")


def test_classify_fences_headings_lists_quotes() -> None:
    doc = tx.parse("# Title\n\nText here.\n\n```\ncode. More code.\n```\n\n- item one\n> quoted\n")
    kinds = [ln.kind for ln in doc.lines]
    assert kinds == ["heading", "blank", "para", "blank", "fence", "code", "fence", "blank", "list", "quote"]
    texts = [s.text for s in doc.sentences]
    assert "code. More code." not in " ".join(texts)
    assert [s.kind for s in doc.sentences if s.text == "quoted"] == ["quote"]


def test_front_matter_is_skipped() -> None:
    doc = tx.parse("---\ntitle: x\n---\nBody.\n")
    assert [s.text for s in doc.sentences] == ["Body."]


def test_phrase_regex_wildcard_and_apostrophe() -> None:
    import re
    pattern = re.compile(tx.phrase_regex("delv*"), re.I)
    assert pattern.search("We delved in") and not pattern.search("undelve")
    pattern = re.compile(tx.phrase_regex("let's dive in"), re.I)
    assert pattern.search("Let’s dive in.")


def test_words_loading(tmp_path) -> None:  # noqa: ANN001
    (tmp_path / "allow.txt").write_text("robust\n", encoding="utf-8")
    (tmp_path / "flag.txt").write_text("frobnicate\tprocess\n", encoding="utf-8")
    (tmp_path / "flag-patterns.txt").write_text("ticket\tJIRA-\\d+\n", encoding="utf-8")
    words = tx.load_words(str(tmp_path), False)
    assert words.allowed("Robust")
    assert len(words.flags) == 2 and words.digest


def test_words_errors(tmp_path) -> None:  # noqa: ANN001
    import pytest
    (tmp_path / "flag.txt").write_text("a\tb\tc\n", encoding="utf-8")
    with pytest.raises(tx.InputError):
        tx.load_words(str(tmp_path), False)
    (tmp_path / "flag.txt").write_text("a\t" + "x" * 81 + "\n", encoding="utf-8")
    with pytest.raises(tx.InputError):
        tx.load_words(str(tmp_path), False)
    (tmp_path / "flag.txt").write_text("", encoding="utf-8")
    (tmp_path / "flag-patterns.txt").write_text("bad\t(\n", encoding="utf-8")
    with pytest.raises(tx.InputError):
        tx.load_words(str(tmp_path), False)
    with pytest.raises(tx.InputError):
        tx.load_words(str(tmp_path), True)


def test_read_text_rejects_non_utf8(tmp_path) -> None:  # noqa: ANN001
    import pytest
    path = tmp_path / "x.md"
    path.write_bytes(b"\xff\xfe bad")
    with pytest.raises(tx.InputError):
        tx.read_text(str(path))


def test_emoji_detection() -> None:
    assert tx.emoji_in("Launch 🚀 now ✅") == ["🚀", "✅"]
    assert tx.emoji_in("A → B, © 2026") == []


def test_fence_inside_list_item() -> None:
    text = "1. Install the tool:\n\n    ```bash\n    pip install foo==2.0 — now\n    ```\n\n2. Run it.\n"
    doc = tx.parse(text)
    assert [ln.kind for ln in doc.lines][2:5] == ["fence", "code", "fence"]
    assert all("pip" not in s.text for s in doc.sentences)


def test_callout_and_quote_blocks() -> None:
    doc = tx.parse("> **Warning:** Do not delete it.\n\n> She said hello.\n")
    assert [b.kind for b in doc.blocks] == ["callout", "quote"]


def test_hash_ignores_trailing_newlines() -> None:
    assert tx.sha256_text("A.\n\n\n") == tx.sha256_text("A.") == tx.sha256_text("A.\r\n")


def test_joined_offsets_with_trailing_code() -> None:
    doc = tx.parse("Run `make test`\nthen deploy.\n")
    assert doc.sentences[0].text == "Run `make test` then deploy."


def test_indented_fence_inside_top_level_fence() -> None:
    text = ("Intro.\n\n```markdown\n1. Step\n\n    ```bash\n    echo hi\n    ```\n```\n\n"
            "After the example we leverage a tool.\n")
    doc = tx.parse(text)
    assert doc.lines[-1].kind == "para"
    assert any("leverage" in s.text for s in doc.sentences)


def test_word_list_line_limit(tmp_path) -> None:  # noqa: ANN001
    (tmp_path / "allow.txt").write_text("w\n" * tx.MAX_WORD_LINES, encoding="utf-8")
    assert len(tx.load_words(str(tmp_path), False).allow) == tx.MAX_WORD_LINES


# ---------------------------------------------------------------- set 4 lint review


def kinds(text: str) -> list[str]:
    return [ln.kind for ln in tx.parse(text).lines]


def test_url_does_not_swallow_closing_bold() -> None:
    for text in ("Open **http://localhost:3000** now.", "**www.example.com**"):
        masked = tx.mask(text)
        assert masked.count("**") == 2, masked
    assert "example" not in tx.mask("See https://example.com/a_b_.")


def test_fence_inside_block_quote_is_code() -> None:
    text = '> [!TIP]\n> ```bash\n> git checkout -- src/utilize.py\n> python -c "print(2**3)"\n> ```\n> After it.\n'
    doc = tx.parse(text)
    assert kinds(text) == ["quote", "fence", "code", "code", "fence", "quote"]
    assert all(ln.quoted for ln in doc.lines[1:5])
    assert [b.kind for b in doc.blocks] == ["callout", "callout"]
    assert not any("utilize" in s.text for s in doc.sentences)


def test_fence_in_quote_ends_with_the_quote() -> None:
    assert kinds("> ```\n> code\n\nOutside para.\n") == ["fence", "code", "blank", "para"]


def test_indented_code_inside_list_item() -> None:
    text = "- Restore the file:\n\n      git checkout -- src/utilize.py\n\n  More about the item.\n"
    assert kinds(text) == ["list", "blank", "code", "blank", "para"]
    assert kinds("1. Step\n\n       code\n") == ["list", "blank", "code"]
    assert kinds("- item\n\n    continued paragraph\n") == ["list", "blank", "para"]


def test_callout_continues_across_blank_quote_lines() -> None:
    doc = tx.parse("> [!NOTE]\n> Plain first paragraph.\n>\n> In today's world we leverage synergy.\n")
    assert [b.kind for b in doc.blocks] == ["callout", "callout"]
    doc = tx.parse("> She said hello.\n>\n> She left.\n\n> [!NOTE]\n> Text.\n")
    assert [b.kind for b in doc.blocks] == ["quote", "quote", "callout"]


def test_callout_with_emoji_or_italic_label() -> None:
    for text in ("> 💡 **Tip:** Use the cache.\n", "> *Note:* We delve here.\n", "> ⚠️ _Warning:_ Stop.\n"):
        assert [b.kind for b in tx.parse(text).blocks] == ["callout"], text
    assert [b.kind for b in tx.parse("> Note that she left.\n").blocks] == ["quote"]


def test_inline_code_across_line_break_is_masked() -> None:
    doc = tx.parse("run `git checkout --\nsrc/leverage_utils.py` and rebuild.\n")
    assert "--" not in doc.lines[0].masked and "leverage" not in doc.lines[1].masked
    assert doc.lines[1].masked.endswith("and rebuild.")
    assert "leverage" not in doc.sentences[0].masked


def test_phrase_regex_curly_apostrophe_entry() -> None:
    import re
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        pattern = re.compile(tx.phrase_regex("Let’s circle up"), re.I)
    assert pattern.search("let's circle up") and pattern.search("Let’s circle up")


def test_lazy_continuation_lines() -> None:
    text = "> In today's world, this tool lets\nteams delve into data.\n\nAfter.\n"
    assert kinds(text) == ["quote", "quote", "blank", "para"]
    assert [b.kind for b in tx.parse(text).blocks] == ["quote", "para"]
    text = "- This item wraps\nlazily onto a second line and\na third line:\n\nNext.\n"
    doc = tx.parse(text)
    assert [b.kind for b in doc.blocks] == ["list", "para"]
    assert len(doc.blocks[0].lines) == 3


def test_inline_html_and_mid_line_comments() -> None:
    assert kinds("<strong>Warning:</strong> Text here <em>x</em>\n") == ["para"]
    assert kinds("<div align=\"center\">\n\n<img src=\"x.png\">\n\n<br>\n") == ["html", "blank", "html", "blank", "html"]
    text = "Text here <!-- TODO leverage\nthis is delve comment -->\nAfter.\n"
    doc = tx.parse(text)
    assert kinds(text) == ["para", "html", "para"]
    assert "leverage" not in doc.lines[0].masked
    assert "TODO" not in tx.mask("A <!-- TODO --> B")


def test_allowed_ignores_apostrophe_style_and_line_breaks() -> None:
    words = tx.Words(allow=["it's worth noting that", "in order to"])
    assert words.allowed("It’s worth noting that")
    assert words.allowed("in order\nto")
    assert not words.allowed("in order")


def test_split_common_words_initials_and_non_ascii() -> None:
    assert spans("The answer was no. The team needs another week.") == [
        "The answer was no.", "The team needs another week."]
    assert spans("Set the fan to max. Then restart it.") == ["Set the fan to max.", "Then restart it."]
    assert spans("Plan B. It was cheaper.") == ["Plan B.", "It was cheaper."]
    assert spans("We met in Oslo. Émile joined later.") == ["We met in Oslo.", "Émile joined later."]
    assert spans("See No. 5 and Fig. 3 here. Then Dec. 5 came.") == ["See No. 5 and Fig. 3 here.", "Then Dec. 5 came."]
    assert spans("John F. Kennedy spoke. J. R. R. Tolkien wrote.") == ["John F. Kennedy spoke.", "J. R. R. Tolkien wrote."]
    assert spans("The U.S. Army agreed. It costs approx. 5 dollars.") == [
        "The U.S. Army agreed.", "It costs approx. 5 dollars."]


def test_toml_front_matter_and_heading_hash() -> None:
    doc = tx.parse("+++\ntitle = \"delve\"\n+++\nBody.\n")
    assert [s.text for s in doc.sentences] == ["Body."]
    doc = tx.parse("## Using C#\n## Title ##\n#  Spaced  #\n")
    assert [ln.content for ln in doc.lines] == ["Using C#", "Title", "Spaced"]
    assert [ln.level for ln in doc.lines] == [2, 2, 1]
    assert doc.lines[2].offset == 3


def test_setext_heading_level() -> None:
    doc = tx.parse("Title\n=====\n\nSub\n---\n")
    assert [(ln.kind, ln.level) for ln in doc.lines if ln.kind == "heading"] == [("heading", 1), ("heading", 2)]


def test_sentence_start_offsets() -> None:
    doc = tx.parse("One two. Three four.\n")
    assert [s.start for s in doc.sentences] == [0, 9]


def test_text_helpers_are_linear() -> None:
    import time
    cases = [
        "|" + " " * 40000 + "x",
        "a | b\n--" + " " * 40000 + "x",
        "a@b " + "a." * 20000,
        "http://x " + "a." * 20000,
        "www." * 10000,
        "A. " * 13000,
    ]
    for text in cases:
        start = time.monotonic()
        tx.parse(text)
        tx.split_sentences(text)
        assert time.monotonic() - start < 2, text[:20]


# ---------------------------------------------------------------- set 5 lint review


def test_later_paragraphs_of_a_list_item_are_prose() -> None:
    text = ("1. Open the settings page.\n\n    Pick the region closest to your users.\n\n"
            "    This step leverages a robust cache.\n\n2. Save.\n")
    doc = tx.parse(text)
    assert kinds(text) == ["list", "blank", "para", "blank", "para", "blank", "list"]
    assert [ln.continuation for ln in doc.lines if ln.kind == "para"] == [True, True]
    assert any("leverages" in s.text for s in doc.sentences)
    tabbed = "1. Open it.\n\n\tPick one.\n\n\tThis step leverages it.\n"
    assert kinds(tabbed) == ["list", "blank", "para", "blank", "para"]
    assert kinds("- a\n  - b\n\n  outer para\n\n      code\n") == ["list", "list", "blank", "para", "blank", "code"]
    assert kinds("- a\n\n    para\n\ntop\n\n    code\n") == ["list", "blank", "para", "blank", "para", "blank", "code"]


def test_fence_after_a_paragraph_inside_a_list_item() -> None:
    text = ("1. Install the tool:\n    ~~~\n    npm i\n    ~~~\n    Then start it:\n    ~~~\n"
            "    npm start -- --robust # leverage\n    ~~~\n2. Done.\n")
    doc = tx.parse(text)
    assert kinds(text) == ["list", "fence", "code", "fence", "para", "fence", "code", "fence", "list"]
    assert not any("leverage" in s.text for s in doc.sentences)


def test_front_matter_needs_a_closing_line_and_a_key() -> None:
    assert kinds("---\n\nWe leverage robust tooling.\n") == ["rule", "blank", "para"]
    assert kinds("---\nIntro text here.\n") == ["rule", "para"]
    assert kinds("---\ntitle: x\nNo closing line.\n")[0] == "rule"
    assert kinds("---\ntitle: x\n---\nBody.\n") == ["front", "front", "front", "para"]
    assert kinds("---\n# comment\n...\nBody.\n") == ["front", "front", "front", "para"]
    assert kinds("+++\n\nBody.\n+++\n")[0] != "front"


def test_code_spans_pair_runs_of_equal_length() -> None:
    assert tx.code_spans("a `code` b") == [(2, 8, "code")]
    assert tx.code_spans("``` foo ``") == []  # no closing run of three: literal
    assert tx.code_spans("a `` ` `` b") == [(2, 9, "code")]
    assert tx.code_spans("<!-- ` --> text `code`") == [(0, 10, "html"), (16, 22, "code")]
    assert tx.code_spans("`<!--` x") == [(0, 6, "code")]
    assert tx.code_spans("x <!-- open") == [(2, 11, "html")]
    assert tx.code_spans("x <!-- open", comments=False) == []


def test_unpaired_backtick_runs_are_linear() -> None:
    import time
    text = " ".join("`" * m for m in range(1, 280)) + " x"
    start = time.monotonic()
    for _ in range(5):
        tx.mask(text)
        tx.parse(text)
    assert time.monotonic() - start < 1
    assert tx.mask(text) == text


def test_callout_with_emoji_inside_the_label() -> None:
    for text in ("> **⚠️ Warning:** This leverages a lock.\n", "> ℹ️ **Note:** Text.\n", "> **ℹ️ Note:** Text.\n",
                 "> _💡 Tip:_ Text.\n"):
        assert [b.kind for b in tx.parse(text).blocks] == ["callout"], text


# ---------------------------------------------------------------- set 6 lint review


def test_sentences_keep_leading_and_trailing_code() -> None:
    doc = tx.parse("`parse()` is the entry point. `lex()` is called by it.\n")
    assert [s.text for s in doc.sentences] == ["`parse()` is the entry point.", "`lex()` is called by it."]
    assert doc.sentences[1].masked.startswith(" ")  # masked text still has spaces for code
    assert [s.text for s in tx.parse("- Install with `pip install foo`\n").sentences] == ["Install with `pip install foo`"]
    doc = tx.parse("The fix? `retry()` now wraps every call. See https://example.com/a is the page.\n")
    assert [s.text for s in doc.sentences] == ["The fix?", "`retry()` now wraps every call.",
                                               "See https://example.com/a is the page."]
    assert [s.text for s in tx.parse("First.<br>Second one.\n").sentences] == ["First.", "Second one."]  # tags stay separators
    assert tx.split_view("Run `x` at <b>a</b>") == "Run XXX at    a    "


def test_wrapped_year_does_not_start_a_list() -> None:
    assert kinds("The company was founded in\n1998. It now employs 40 people.\n") == ["para", "para"]
    assert len(tx.parse("The company was founded in\n1998. It now employs 40 people.\n").blocks) == 1
    assert kinds("Steps follow\n1. Open it.\n2. Close it.\n") == ["para", "list", "list"]
    assert kinds("Text\n- item\n") == ["para", "list"]
    assert kinds("Text\n*\n") == ["para", "para"]  # an empty item cannot interrupt a paragraph
    assert kinds("1. a\n   more\n2. b\n") == ["list", "para", "list"]


def test_indented_backticks_in_a_list_item_are_indented_code() -> None:
    text = "- item\n\n      ```\n      x\n\nIt is worth noting that.\n"
    assert kinds(text) == ["list", "blank", "code", "code", "blank", "para"]
    assert kinds("- item\n\n  ```\n  x\n  ```\n\nAfter.\n") == ["list", "blank", "fence", "code", "fence", "blank",
                                                               "para"]


def test_emoji_clusters() -> None:
    assert tx.emoji_in("🇯🇵 👨‍👩‍👧 👍🏽 ❤️ 1️⃣ 🏳️‍🌈") == [
        "🇯🇵", "👨‍👩‍👧", "👍🏽", "❤️", "1️⃣", "🏳️‍🌈"]
    assert tx.emoji_spans("a 🇯🇵 b") == [(2, 4)]
    assert tx.emoji_in("Done ✓ 1 2 # → ©") == []


def test_non_utf8_error_names_line_and_byte(tmp_path) -> None:  # noqa: ANN001
    import pytest
    path = tmp_path / "x.md"
    path.write_bytes(b"ok\nfine\n\xff bad")
    with pytest.raises(tx.InputError, match=r"line 3, byte 8"):
        tx.read_text(str(path))


def test_excerpt_centers_on_the_column() -> None:
    line = "a" * 200 + " — " + "b" * 200
    shown = tx.excerpt(line, 202, 1, 160)
    assert "—" in shown and shown.startswith("…") and shown.endswith("…")
    assert len(shown) <= 162
    assert tx.excerpt("short line", 3) == "short line"
    assert tx.excerpt("x" * 300, 1).startswith("x") and tx.excerpt("x" * 300, 300).endswith("x")
