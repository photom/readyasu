from __future__ import annotations

import pytest
import readyasu_diff as diff


def kinds(orig: str, rev: str, doc_type: str | None = None, counted_only: bool = True) -> list[str]:
    result = diff.compare(orig, rev, doc_type)
    return [r.kind for r in result.risks if r.counted or not counted_only]


def review_kinds(orig: str, rev: str) -> list[str]:
    return [v.kind for v in diff.compare(orig, rev).reviews]


def test_identical_text_has_no_findings() -> None:
    text = "# T\n\nThe job may fail. Only admins can delete it.\n"
    result = diff.compare(text, text)
    assert not result.risks and not result.changes


def test_benign_edit_has_no_counted_risk() -> None:
    assert kinds("In order to save time, we cache results.\n", "To save time, we cache results.\n") == []


@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("Wait 3 seconds.\n", "Wait 5 seconds.\n", "number"),
    ("Wait three seconds.\n", "Wait 5 seconds.\n", "number"),
    ("It does not retry.\n", "It retries.\n", "negation"),
    ("The fix may help.\n", "The fix helps.\n", "certainty"),
    ("The fix will likely help.\n", "The fix will help.\n", "certainty"),
    ("You may skip it.\n", "Skip it.\n", "permission"),
    ("You should test it.\n", "You must test it.\n", "obligation"),
    ("The date is TBD.\n", "The date is May.\n", "status"),
    ("Reportedly, it failed.\n", "It failed.\n", "hearsay"),
    ("Is it ready?\n", "It is ready.\n", "question"),
    ("Please send it.\n", "Send it.\n", "request"),
    ("It takes about 30 minutes.\n", "It takes 30 minutes.\n", "approximation"),
    ("Pick either A or B.\n", "Pick both A and B.\n", "scope"),
    ("Only admins can delete.\n", "Admins can delete.\n", "scope"),
    ("Errors were associated with the flush.\n", "The flush caused errors.\n", "correlation"),
    ("We looked into it.\n", "We looked into it, and we will fix it.\n", "commitment"),
    ("Results improved [1].\n", "Results improved [2].\n", "citation"),
    ("Dana asked Lee to review.\n", "Lee asked Dana to review.\n", "name_order"),
])
def test_meaning_risks(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


def test_booster_counted_only_for_fact_types() -> None:
    orig, rev = "The job runs nightly.\n", "The job always runs nightly.\n"
    assert "booster" in kinds(orig, rev, "pr")
    assert "booster" not in kinds(orig, rev)
    assert "booster" in review_kinds(orig, rev)


def test_contrast_reversal_not_counted() -> None:
    got = kinds("We chose clarity, not cleverness.\n", "We chose clarity and cleverness.\n", counted_only=False)
    assert "contrast_reversed" in got


def test_protected_change_reported_not_counted() -> None:
    result = diff.compare("Run `make test`.\n", "Run `make check`.\n")
    assert any(r.kind == "protected" and not r.counted for r in result.risks)
    assert result.counted == 0


def test_added_sentence_with_commitment() -> None:
    assert "commitment" in kinds("We found the bug.\n", "We found the bug. We will fix it tomorrow.\n")


def test_reviews() -> None:
    got = review_kinds("Users reported errors.\n", "The team saw errors, so we were relieved.\n")
    assert "actor_added" in got and "feeling_added" in got


def test_words_gone_and_heading() -> None:
    got = review_kinds("# Setup steps\n\nInstall the database.\n", "# Setup\n\nInstall it.\n")
    assert "words_gone" in got and "heading" in got


def test_stiffness_and_energy() -> None:
    result = diff.compare("We're done! It's great! 🎉\n", "We are done. It is great.\n")
    assert result.stiffness and result.energy
    assert diff.stiffness_line(result).startswith("candidates")


def test_reference_only_for_formal_types() -> None:
    result = diff.compare("We're done and it's great.\n", "We are done and it is great.\n", "formal")
    assert diff.stiffness_line(result).startswith("reference")


def test_fact_gaps() -> None:
    result = diff.compare("x\n", "We significantly improved performance.\nWe shortened it by 3 seconds.\n",
                          want_fact_gaps=True)
    assert [g.kind for g in result.fact_gaps] == ["effect"]
    result = diff.compare("x\n", "We significantly improved it.\n", "essay", want_fact_gaps=True)
    assert result.fact_gaps == []


def test_compose_material_check() -> None:
    result = diff.compose("Backups are kept for 30 days and deleted at 4:00.\n",
                          "Backups are kept for 30 days. Deletion runs at 3:00.\n")
    assert [r.kind for r in result.risks] == ["material_number"]
    assert "4:00" in result.risks[0].message


def test_cli(tmp_path, capsys) -> None:  # noqa: ANN001
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("Wait 3 seconds.\n", encoding="utf-8")
    b.write_text("Wait 5 seconds.\n", encoding="utf-8")
    assert diff.main([str(a), str(b), "--no-words"]) == 0
    assert diff.main([str(a), str(b), "--no-words", "--fail-on", "meaning-risk"]) == 1
    assert diff.main([str(a), str(a), "--no-words", "--fail-on", "meaning-risk"]) == 0
    assert diff.main([str(a), "--no-words"]) == 2
    assert diff.main(["--compose", str(b), "--no-words"]) == 2
    out = capsys.readouterr().out
    assert "Stiffness check:" in out and "Energy check:" in out


def test_number_change_counted_once() -> None:
    result = diff.compare("Wait 3 seconds.\n", "Wait 5 seconds.\n")
    assert result.counted == 1


@pytest.mark.parametrize(("orig", "rev"), [
    ("Once the build finishes, deploy.\n", "After the build finishes, deploy.\n"),
    ("First, open settings. Then click Save.\n", "Open settings and click Save.\n"),
    ("Wait a second.\n", "Pause briefly.\n"),
    ("Write to the target directory.\n", "Write to the output directory.\n"),
    ("No one replied.\n", "Nobody replied.\n"),
])
def test_benign_word_changes_not_counted(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("Most users prefer X.\n", "Users prefer X.\n", "scope"),
    ("This applies for some customers.\n", "This applies for customers.\n", "scope"),
    ("Ship in Q3.\n", "Ship in Q4.\n", "number"),
    ("Use v2 of the API.\n", "Use v3 of the API.\n", "number"),
    ("Budget is 5k.\n", "Budget is 5M.\n", "number"),
    ("We raised $1.5M.\n", "We raised $1.5B.\n", "number"),
    ("Alice approved Bob's request.\n", "Bob approved Alice's request.\n", "name_order"),
    ("> **Warning:** Do not delete the bucket before 5 pm.\n", "> **Warning:** Delete the bucket after 6 pm.\n",
     "negation"),
])
def test_more_meaning_risks(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


def test_actor_false_positives() -> None:
    got = review_kinds("The user can sign in.\n", "Users can sign in, i.e. log in.\n")
    assert "actor_added" not in got
    assert "actor_added" in review_kinds("The report is ready.\n", "I think the report is ready.\n")


def test_changed_places_shows_line_counts() -> None:
    out = diff.format_text(diff.compare("A one.\nB two.\n", "A one. B two.\n"))
    assert "(2 lines → 1 line)" in out.split("== Meaning risks")[0]


@pytest.mark.parametrize(("orig", "rev"), [
    ("It usually works.\n", "It typically works.\n"),
    ("We often deploy.\n", "We frequently deploy.\n"),
    ("Many users like it.\n", "Numerous users like it.\n"),
    ("Most teams agree.\n", "The majority of teams agree.\n"),
    ("Under certain conditions it fails.\n", "Under specific conditions it fails.\n"),
    ("Several services broke.\n", "A handful of services broke.\n"),
    ("Coverage rose 10%.\n", "Coverage rose 10 percent.\n"),
    ("Use v2.\n", "Use version 2.\n"),
])
def test_synonym_edits_not_counted(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_adverb_quantifier_drop_is_review() -> None:
    assert kinds("It usually works.\n", "It works.\n") == []
    assert "quantifier_gone" in review_kinds("It usually works.\n", "It works.\n")


def test_currency_with_country_prefix() -> None:
    assert "number" in kinds("It costs US$5.\n", "It costs US$6.\n")


@pytest.mark.parametrize(("orig", "rev"), [
    ("The most important step is testing.\n", "The key step is testing.\n"),
    ("This is the most common error.\n", "This is the usual error.\n"),
    ("Most importantly, back up first.\n", "Above all, back up first.\n"),
    ("Retry at most 3 times.\n", "Retry no more than 3 times.\n"),
    ("I'm certain the fix works.\n", "I'm sure the fix works.\n"),
])
def test_non_quantity_most_certain(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_certain_as_quantifier_still_counted() -> None:
    assert "scope" in kinds("It fails under certain loads.\n", "It fails under load.\n")


def test_approximation_groups() -> None:
    assert kinds("It takes about 30 minutes.\n", "It takes approximately 30 minutes.\n") == []
    assert "approximation" in kinds("Retry at most 3 times.\n", "Retry at least 3 times.\n")
    assert "negation" not in kinds("Use no more than 3.\n", "Use at most 3.\n")


@pytest.mark.parametrize(("orig", "rev"), [
    ("No one else can access the vault.\n", "Everyone else can access the vault.\n"),
    ("Submit no later than 5 pm.\n", "Submit later than 5 pm.\n"),
    ("It's no more than a draft.\n", "It's more than a draft.\n"),
])
def test_negation_phrases_still_counted(orig: str, rev: str) -> None:
    assert "negation" in kinds(orig, rev)


def test_no_one_else_synonym_not_counted() -> None:
    assert kinds("No one else can access the vault.\n", "Nobody else can access the vault.\n") == []


def test_most_with_mass_noun_is_review() -> None:
    assert "quantifier_gone" in review_kinds("Most traffic goes to the EU region.\n", "Traffic goes to the EU region.\n")


@pytest.mark.parametrize(("orig", "rev"), [
    ("Retry not more than 3 times.\n", "Retry at most 3 times.\n"),
    ("Use a maximum of 3 workers.\n", "Use at most 3 workers.\n"),
    ("Keep no fewer than $5.\n", "Keep at least $5.\n"),
    ("Most of all, test the backup.\n", "Above all, test the backup.\n"),
    ("Most important, back up first.\n", "Above all, back up first.\n"),
])
def test_fifth_pass_benign(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_pronoun_one_not_a_number() -> None:
    assert kinds("We kept the old tool.\n", "We kept the old one.\n") == []
    assert "number" in kinds("Use two servers.\n", "Use one server.\n")
    assert "number" in kinds("Only two servers run.\n", "Only one server runs.\n")


def test_compose_risk_has_no_original_line() -> None:
    out = diff.format_text(diff.compose("Wait 3 seconds.\n", "Wait 5 seconds.\n"))
    assert "original line 0" not in out


@pytest.mark.parametrize(("orig", "rev"), [
    ("One of the servers failed.\n", "Some of the servers failed.\n"),
    ("Exactly one is allowed.\n", "Several are allowed.\n"),
    ("At most one can run.\n", "Any number can run.\n"),
    ("We chose one.\n", "We chose several.\n"),
    ("Approve one, then wait.\n", "Approve them, then wait.\n"),
    ("Use the one remaining node.\n", "Use the remaining nodes.\n"),
])
def test_one_as_count_is_compared(orig: str, rev: str) -> None:
    assert "number" in kinds(orig, rev)


def test_one_as_pronoun_is_not() -> None:
    assert kinds("No one replied.\n", "Nobody replied.\n") == []
    assert kinds("They help one another.\n", "They help each other.\n") == []
    assert kinds("Pick the one that works.\n", "Pick the option that works.\n") == []


# ---- set 4 review: conditions, units, dates, hedges, hearsay, moves, names

@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("Pro costs $80 per year when billed annually.\n", "Pro costs $80 per year.\n", "condition"),
    ("Sharing is not available on the web app at launch.\n", "Sharing is not available on the web app.\n", "condition"),
    ("Admins can delete projects if they own them.\n", "Admins can delete projects.\n", "condition"),
    ("Retries are capped at 30 seconds.\n", "Retries are capped at 30 ms.\n", "number"),
    ("Disks hold 2 TB each.\n", "Disks hold 2 GB each.\n", "number"),
    ("Refunds take 30 days.\n", "Refunds take 30 business days.\n", "number"),
    ("We will ship in May.\n", "We will ship in June.\n", "number"),
    ("Submit it by Monday.\n", "Submit it by Friday.\n", "number"),
    ("The release is planned for May 5.\n", "The release is on May 5.\n", "certainty"),
    ("The fix may ship in Q3, and a backport is planned.\n", "The fix may ship in Q3, and a backport follows.\n",
     "certainty"),
    ("This change would cut build time in half.\n", "This change cuts build time in half.\n", "certainty"),
    ("We expect the migration to finish on Friday.\n", "The migration finishes on Friday.\n", "certainty"),
    ("The vendor says the patch fixes the leak.\n", "The patch fixes the leak.\n", "hearsay"),
    ("Sam said the staging build is green.\n", "The staging build is green.\n", "hearsay"),
])
def test_set4_meaning_changes_are_counted(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("Check if the file exists.\n", "Check whether the file exists.\n"),
    ("Wait 5 seconds.\n", "Wait 5 s.\n"),
    ("It could potentially fail.\n", "It could fail.\n"),
    ("I would like your approval.\n", "I'd like your approval.\n"),
    ("You need at least 3 nodes.\n", "You need 3 or more nodes.\n"),
    ("Upload up to 10 files.\n", "Upload 10 files or fewer.\n"),
    ("The migration is in progress.\n", "The migration is ongoing.\n"),
    ("Review the draft before Friday.\n", "Review the document before Friday.\n"),
    ("The team's deadline moved.\n", "The deadline for the team moved.\n"),
    ("We moved the job to a queue. The result? Fewer timeouts.\n",
     "We moved the job to a queue, which reduced timeouts.\n"),
    ("Review this by Friday.\n", "Could you review this by Friday?\n"),
    ("It's not just a bug fix, it's a rethink.\n", "It's a rethink.\n"),  # negation only, no "just" scope risk
])
def test_set4_harmless_rewrites(orig: str, rev: str) -> None:
    assert [k for k in kinds(orig, rev) if k != "negation" or "not just" not in orig] == []


def test_moved_sentence_with_flipped_negation_is_compared() -> None:
    o = "Stop the service before the upgrade. Do not delete the old logs. Then run the installer.\n"
    r = "Delete the old logs. Stop the service before the upgrade. Then run the installer.\n"
    assert "negation" in kinds(o, r)
    o = "Customers may cancel within 30 days. Refunds are processed in 5 business days.\n"
    r = "Refunds are processed in 5 business days. Customers must cancel within 30 days.\n"
    assert {"permission", "obligation"} <= set(kinds(o, r))


def test_split_sentence_keeps_its_number() -> None:
    o = ("The nightly job copies 200 tables to the warehouse and usually finishes in 40 minutes. If it fails, the "
         "on-call engineer may rerun it manually.\n")
    r = ("The nightly job copies 200 tables to the warehouse. It usually finishes in 40 minutes. If it fails, the "
         "on-call engineer may rerun it by hand.\n")
    assert "number" not in kinds(o, r)


def test_deleted_summary_repeating_a_number_is_not_a_number_change() -> None:
    o = ("We moved the cache to Redis, and p95 latency fell by 40%.\n\nError rates also dropped.\n\n"
         "In summary, the move cut latency by 40% and reduced errors.\n")
    r = "We moved the cache to Redis, and p95 latency fell by 40%.\n\nError rates also dropped.\n"
    assert "number" not in kinds(o, r)


def test_owners_swapped_between_list_items() -> None:
    o = "- Add an alert for config drift. Owner: Marco Ruiz.\n- Review the deploy checklist. Owner: Priya Nair.\n"
    r = "- Add an alert for config drift. Owner: Priya Nair.\n- Review the deploy checklist. Owner: Marco Ruiz.\n"
    assert "name_order" in kinds(o, r)


def test_actor_in_subject_position_and_unit_codes() -> None:
    assert "actor_added" in review_kinds("The budget was approved last week.\n", "Priya approved the budget last week.\n")
    assert "actor_added" not in review_kinds("Disks hold 2 TB.\n", "Disks hold 2 GB.\n")
    assert "actor_added" not in review_kinds("Backoff: retry with a delay.\n", "Backoff: Retries wait longer.\n")


def test_changed_place_excerpt_shows_the_difference() -> None:
    prefix = "Notewise 3.0 rolls out to every workspace this week and now includes up to 3 shared notebooks per user "
    result = diff.compare(prefix + "when billed annually.\n", prefix + "with any plan.\n")
    text = "\n".join(diff.format_sections(result))
    assert "billed annually" in text.split("== Meaning risks")[0]


def test_empty_fact_gaps_section_is_shown() -> None:
    result = diff.compare("We ship on Monday.\n", "We ship Monday.\n", want_fact_gaps=True)
    assert "None found" in "\n".join(diff.format_sections(result))
