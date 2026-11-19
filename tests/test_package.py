"""Consistency between the skill's documents and the scripts."""

from __future__ import annotations

import re

import yomiyasu_en_lint as lint
import yomiyasu_en_text as tx
from conftest import ROOT, SKILL


def skill_text() -> str:
    return (SKILL / "SKILL.md").read_text(encoding="utf-8")


def test_frontmatter() -> None:
    text = skill_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m
    front = m.group(1)
    assert re.search(r"^name: yomiyasu-en$", front, re.M)
    assert re.search(r"^description: .{50,1024}$", front, re.M)
    version = re.search(r'version: "([^"]+)"', front)
    assert version and version.group(1) == tx.__version__


def test_referenced_files_exist() -> None:
    texts = [skill_text()] + [p.read_text(encoding="utf-8") for p in (SKILL / "references").rglob("*.md")]
    for text in texts:
        for ref in re.findall(r"`(references/[\w./-]+\.(?:md|txt))`", text):
            if "<" in ref:
                continue
            assert (SKILL / ref).is_file(), ref


def test_doc_type_files_match_lint_exemptions() -> None:
    for doc_type in tx.DOC_TYPES:
        text = (SKILL / "references" / "doc-types" / f"{doc_type}.md").read_text(encoding="utf-8")
        m = re.search(r"^Lint rules exempted: (.+)$", text, re.M)
        assert m, doc_type
        listed = [] if m.group(1).strip() == "none" else [
            r.split(" ")[0] for r in (x.strip() for x in m.group(1).split(", "))]
        expected = list(lint.EXEMPT[doc_type]) + (["chat_residue"] if doc_type == "mail" else [])
        assert sorted(listed) == sorted(expected), doc_type


def test_audience_table_matches_lint_exemptions() -> None:
    text = (SKILL / "references" / "audience.md").read_text(encoding="utf-8")
    section = text.split("## 13.")[1].split("## 14.")[0]
    for doc_type in tx.DOC_TYPES:
        m = re.search(r"^\| " + doc_type + r" \| (.+) \|$", section, re.M)
        assert m, doc_type
        listed = [] if m.group(1).strip() == "none" else [
            r.split(" ")[0] for r in (x.strip() for x in m.group(1).split(", "))]
        expected = list(lint.EXEMPT[doc_type]) + (["chat_residue"] if doc_type == "mail" else [])
        assert sorted(listed) == sorted(expected), doc_type


def test_lists_readme_matches_lint() -> None:
    text = (SKILL / "references" / "lists" / "README.md").read_text(encoding="utf-8")
    for rule, name, _courtesy in lint.LIST_RULES:
        assert re.search(r"\| " + re.escape(name) + r"\.txt \| " + rule, text), name
        assert (tx.LISTS_DIR / f"{name}.txt").is_file()
    for name in ("fact-gaps", "stiff-words", "feelings", "roles"):
        assert (tx.LISTS_DIR / f"{name}.txt").is_file()


def test_review_points_cover_every_rule() -> None:
    text = (SKILL / "references" / "review-points.md").read_text(encoding="utf-8")
    for rule in lint.RULES:
        assert f"`{rule}`" in text, rule


def test_versions_agree() -> None:
    import json
    import yomiyasu_en_check as check
    import yomiyasu_en_diff as diff
    assert lint.__version__ == diff.__version__ == check.__version__ == tx.__version__
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert plugin["version"] == tx.__version__
    assert market["plugins"][0]["version"] == tx.__version__


def test_skill_license_copied() -> None:
    assert (SKILL / "LICENSE").read_text(encoding="utf-8") == (ROOT / "LICENSE").read_text(encoding="utf-8")


def test_list_files_compile() -> None:
    for path in tx.LISTS_DIR.glob("*.txt"):
        if path.name == "fact-gaps.txt":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                re.compile(tx.phrase_regex(line.split("\t")[0]))


def test_review_points_cover_every_risk_kind() -> None:
    import yomiyasu_en_diff as diff
    text = (SKILL / "references" / "review-points.md").read_text(encoding="utf-8")
    kinds = re.findall(r"^  ([a-z_]+)\s{2,}", diff.HELP_EPILOG, re.M)
    assert "condition" in kinds
    for kind in kinds:
        assert re.search(r"^\| " + kind + r" \|", text, re.M), kind
