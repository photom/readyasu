from __future__ import annotations

import yomiyasu_en_text as tx


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
