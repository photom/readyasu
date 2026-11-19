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


def test_protected_change_counted_when_code_changes() -> None:
    result = diff.compare("Run `make test`.\n", "Run `make check`.\n")
    assert any(r.kind == "code" and r.counted for r in result.risks)
    added = diff.compare("Run the tests.\n", "Run the tests with `make test`.\n")
    assert any(r.kind == "protected" and not r.counted for r in added.risks) and added.counted == 0


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


# ---- set 5 review

@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("Why does this matter? Outages may cost us customers.\n", "This matters because outages cost us customers.\n",
     "certainty"),
    ("Is the cache the cause? It might be.\n", "The cache is the cause.\n", "certainty"),
    ("Back up the database first.\n\nRun the migration on Fridays.\n\nDo not notify customers.\n",
     "Do not notify customers.\n\nBack up the database first.\n\nDo not run the migration on Fridays.\n", "negation"),
    ("It appears that a config change caused the outage.\n", "A config change caused the outage.\n", "certainty"),
    ("The cache seems stale.\n", "The cache is stale.\n", "certainty"),
    ("It's possible that the job failed.\n", "The job failed.\n", "certainty"),
    ("The bug is believed to be fixed.\n", "The bug is fixed.\n", "certainty"),
    ("Teams that may grow could hit the limit.\n", "Teams that may grow will hit the limit.\n", "certainty"),
    ("The vendor claims the patch fixes the leak.\n", "The patch fixes the leak.\n", "hearsay"),
    ("Only admins can delete projects while the freeze is active.\n", "Only admins can delete projects.\n", "condition"),
    ("Merge the PR once the tests pass.\n", "Merge the PR.\n", "condition"),
    ("The May release adds SSO.\n", "The June release adds SSO.\n", "number"),
    ("The fix ships Fri, Dec 5.\n", "The fix ships Mon, Dec 5.\n", "number"),
    ("We need at least two reviewers.\n", "We need two reviewers.\n", "approximation"),
    ("The window starts at 10:00 UTC.\n", "The window starts at 10:00 PST.\n", "number"),
    ("Pick either A or B.\n", "Pick A and B.\n", "scope"),
    ("After a crash, the agent does not restart automatically.\n",
     "After a crash, the agent restarts automatically without any delay.\n", "negation"),
    ("The replicas are upgraded first, not the primary.\n", "The primary is upgraded first, not the replicas.\n",
     "negation"),
    ("You can export the data as CSV.\n", "Can you export the data as CSV?\n", "question"),
])
def test_set5_meaning_changes_are_counted(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("Users may see errors during the upgrade, and they may need to sign in again.\n",
     "Users may see errors during the upgrade and may need to sign in again.\n"),  # used to crash
    ("Please send the report by Friday.\n", "Could you send the report by Friday?\n"),
    ("When the build finishes, deploy it.\n", "After the build finishes, deploy it.\n"),
    ("In order to deploy, you need to have admin rights.\n", "To deploy, you need admin rights.\n"),
    ("It may take a few minutes.\n", "It might take a few minutes.\n"),
    ("The cache can possibly fill up.\n", "The cache can fill up.\n"),
    ("The results were nothing short of remarkable.\n", "The results were remarkable.\n"),
    ("The cache now refreshes hourly. Feel free to reach out with any questions!\n",
     "The cache refreshes every hour.\n"),
    ("The interval changed from 1.0 to 0.5 seconds.\n", "The interval changed from 1 to 0.5 seconds.\n"),
    ("We do not support Windows.\n", "We do not offer Windows builds.\n"),
    ("We plan to ship this sprint. In order\nto finish, Priya will review the parser and Sam will\nupdate the docs.\n",
     "We plan to ship this sprint. To finish, Priya\nwill review the parser and Sam will update the docs.\n"),
])
def test_set5_harmless_rewrites(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_deleted_first_paragraph_does_not_shift_pairs() -> None:
    o = ("Great question! Here's a summary you can share.\n\nOur CI pipeline in Berlin has become a bottleneck.\n\n"
         "Build times in Frankfurt rose to 47 minutes.\n\nThe CI team owns the runners.\n")
    r = ("Our CI pipeline in Berlin has become a real bottleneck.\n\nBuild times in Frankfurt rose to 47 minutes "
         "last quarter.\n\nThe CI team owns all runners.\n")
    result = diff.compare(o, r)
    assert [k.kind for k in result.risks if k.counted] == []
    assert [(c["orig_line"], c["rev_line"]) for c in result.changes] == [(1, 0), (3, 1), (5, 3), (7, 5)]


def test_contractions_in_deleted_residue_are_not_counted() -> None:
    o = "Here's the update you asked for. The job runs nightly.\n\nLet me know if you'd like more detail.\n"
    assert diff.compare(o, "The job runs every night.\n").stiffness == []


def test_closing_section_removal_is_a_soft_review() -> None:
    o = "# Guide\n\n## Setup\n\nInstall it.\n\n## Final Thoughts\n\nInstalling it is easy.\n"
    result = diff.compare(o, "# Guide\n\n## Setup\n\nInstall it.\n")
    messages = [v.message for v in result.reviews if v.kind == "heading"]
    assert messages and messages[0].startswith("Closing section removed")
    assert result.energy == []


def test_not_just_is_not_a_reversed_contrast() -> None:
    result = diff.compare("It is not just faster, but more reliable.\n", "It is faster and more reliable.\n")
    assert "contrast_reversed" not in [r.kind for r in result.risks]


def test_material_lines_from_the_original_are_marked() -> None:
    result = diff.compare("The bill was $3200.\n", "The bill was $3200 per month.\n", materials="Cost: monthly.\n")
    assert any(str(m["material_line"]).startswith("(original)") for m in result.material["matched_numbers"])


# ---- set 6 review

def test_deleted_negation_merged_reversed_into_a_neighbor() -> None:
    o = ("Median reaction time fell from 312 ms to 287 ms in the nap group, while the control group showed no change. "
         "These findings suggest that naps may help. However, the nap did not improve self-reported sleepiness on "
         "the Karolinska Sleepiness Scale.\n")
    r = ("Median reaction time fell from 312 ms to 287 ms in the nap group, and self-reported sleepiness on the "
         "Karolinska Sleepiness Scale also improved, while the control group showed no change. These findings "
         "suggest that naps may help.\n")
    assert "negation" in kinds(o, r)


def test_action_items_stay_paired_when_labels_lose_bold() -> None:
    o = ("1. **Certificate checks**: Add a check. Owner: Marco Ruiz. Due: Friday, November 20.\n"
         "2. **Alerting**: Restore the threshold. Owner: Aisha Khan. Due: Tuesday, November 17.\n")
    r = ("1. Certificate checks: Add a check. Owner: Aisha Khan. Due: Friday, November 20.\n"
         "2. Alerting: Restore the threshold. Owner: Marco Ruiz. Due: Thursday, November 17.\n")
    risks = [x for x in diff.compare(o, r).risks if x.counted]
    dates = [x for x in risks if x.message.startswith("Month or weekday")]
    assert len(dates) == 1 and "Tuesday" in dates[0].message and "Thursday" in dates[0].message
    assert any(x.kind == "name_order" for x in risks)


@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("Some trusts allow naps.\n", "Most trusts allow naps.\n", "scope"),
    ("Median reaction time fell to 287 ms.\n", "Mean reaction time fell to 287 ms.\n", "number"),
    ("Some argue for it (NHS Employers, 2019).\n", "Some argue for it.\n", "citation"),
])
def test_set6_meaning_changes_are_counted(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("All tests pass.\n", "Every test passes.\n"),
    ("Use a maximum of 3 workers.\n", "Use at most 3 workers.\n"),
    ("Our monitoring system chose to stay quiet.\n", "No alert fired.\n"),
])
def test_set6_harmless_rewrites(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_material_unit_and_weekday_mismatch() -> None:
    result = diff.compose("The freeze starts Tuesday, November 14 and takes 22 seconds.\n",
                          "The code freeze starts Monday, December 14. It takes 22 minutes.\n")
    messages = " ".join(r.message for r in result.risks)
    assert "22 s" in messages and "Tuesday" in messages


def test_material_matches_list_only_changed_lines() -> None:
    o = "We have 14 repos.\n\nThe freeze starts soon.\n"
    r = "We have 14 repos.\n\nThe freeze starts on December 14.\n"
    result = diff.compare(o, r, materials="The code freeze starts Monday, December 14.\n")
    lines = {m["line"] for m in result.material["matched_numbers"]}
    assert lines == {3}


def test_closing_rule_only_for_trailing_headings_and_not_pr() -> None:
    o = "## Summary\n\nAdds retries.\n\n## Changes\n\nRetry logic.\n"
    msgs = [v.message for v in diff.compare(o, "## Changes\n\nRetry logic.\n", "pr").reviews if v.kind == "heading"]
    assert msgs and msgs[0].startswith("Number of headings changed")


def test_energy_ignores_deleted_residue() -> None:
    o = "Certainly! Here's a reply you can send.\n\nThanks for flagging it! I'll send the numbers.\n"
    r = "Thanks for flagging it! I'll send the numbers.\n"
    assert diff.compare(o, r, "mail").energy == []


@pytest.mark.parametrize(("orig", "rev"), [
    ("It appears that the cache might be stale.\n", "The cache might be stale.\n"),
    ("It seems like the server may be down.\n", "The server may be down.\n"),
    ("It should be noted that backups run nightly.\n", "Backups run nightly.\n"),
    ("When it comes to caching, Redis is the default choice.\n", "Redis is the default choice for caching.\n"),
    ("While this approach works, it has drawbacks.\n", "This approach works, but it has drawbacks.\n"),
    ("That said, the plan holds.\n", "Still, the plan holds.\n"),
    ("Users may see a brief delay during the upgrade.\n", "Users might see a brief delay during the upgrade.\n"),
    ("You may include a cover letter.\n", "You are allowed to include a cover letter.\n"),
    ("We didn't need a new tool. We needed a shared way to use the old one.\n",
     "What we needed was not a new tool but a shared way to use the old one.\n"),
    ("You don't have to restart the service.\n", "Restarting the service is optional.\n"),
    ("Users are not required to sign in.\n", "Signing in is optional.\n"),
    ("We do not use Kafka. We use RabbitMQ.\n", "We use RabbitMQ, not Kafka.\n"),
    ("Do not restart the primary. Restart the replicas instead.\n", "Restart the replicas, not the primary.\n"),
    ("Several services broke.\n", "A handful of services broke.\n"),
])
def test_set6_diff_review_harmless(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("Could the cache be stale? We restarted it at 3:00.\n", "The cache was stale, so we restarted it at 3:00.\n",
     "question"),
    ("We have around a dozen customers on v1.\n", "We have 12 customers on v1.\n", "approximation"),
    ("Over a dozen users signed up.\n", "A dozen users signed up.\n", "approximation"),
    ("Dana asked Lee to review it.\n", "Dana reviewed it.\n", "name"),
    ("It looks like the disk is full.\n", "The disk is full.\n", "certainty"),
    ("It is unclear whether the bug affects v2.\n", "The bug affects v2.\n", "certainty"),
    ("As far as we know, no data was lost.\n", "No data was lost.\n", "certainty"),
    ("| Day | Owner |\n|---|---|\n| Mon | Ana |\n| Tue | Ben |\n", "| Day | Owner |\n|---|---|\n| Tue | Ana |\n| Mon | Ben |\n",
     "number"),
])
def test_set6_diff_review_counted(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


def test_could_not_is_not_a_hedge() -> None:
    assert "certainty" not in kinds("We could not reproduce the bug.\n", "We were unable to reproduce the bug.\n")


def test_compose_compound_numbers_and_months() -> None:
    ok = diff.compose("The timeout is twenty-five minutes, and up to two hundred users can join. The buffer holds 0.5 "
                      "seconds.\n", "Timeout: 25 minutes. Max users: 200. Retention: 0.50 seconds of buffer.\n")
    assert ok.risks == []
    bad = diff.compose("The migration is planned for June.\n", "The migration is planned for May.\n")
    assert bad.risks and bad.material["material_hedges_not_in_final"] == []


def test_fully_rewritten_long_text_is_fast() -> None:
    import time
    o = "\n".join(f"Sentence {i} talks about the cache layer and the retry budget in some detail." for i in range(150))
    r = "\n".join(f"Line {i} now covers retries, timeouts and the queue with other words entirely." for i in range(150))
    start = time.monotonic()
    diff.compare(o + "\n", r + "\n")
    assert time.monotonic() - start < 10


# ---- set 7 review

@pytest.mark.parametrize(("orig", "rev"), [
    ("- [ ] Priya: Draft the rollback plan by Wednesday\n- [ ] Tom: Share the staging notes by Friday\n",
     "- [ ] Tom: Draft the rollback plan by Wednesday\n- [ ] Priya: Share the staging notes by Friday\n"),
    ("- **Priya**: Draft the rollback plan.\n- **Tom**: Share the notes.\n",
     "- **Tom**: Draft the rollback plan.\n- **Priya**: Share the notes.\n"),
    ("| Owner | Task |\n|---|---|\n| Priya | Draft the plan |\n| Tom | Share the notes |\n",
     "| Owner | Task |\n|---|---|\n| Tom | Draft the plan |\n| Priya | Share the notes |\n"),
])
def test_owner_swaps_in_item_and_table_forms(orig: str, rev: str) -> None:
    assert "name_order" in kinds(orig, rev)


def test_possibility_can_becoming_plain_is_counted() -> None:
    assert "certainty" in kinds("A crash during restore can corrupt the database.\n",
                                "A crash during restore corrupts the database.\n")
    assert "certainty" not in kinds("You can export the data as CSV.\n", "Export the data as CSV.\n")


def test_not_just_removal_is_listed_not_counted() -> None:
    o = "This PR does not just fix a bug; it also adds retries.\n\nThe tool is not only faster but also cheaper.\n"
    r = "This PR fixes a bug and adds retries.\n\nThe tool is faster and cheaper.\n"
    result = diff.compare(o, r)
    assert [x for x in result.risks if x.counted] == []
    assert any(x.kind == "negation" for x in result.risks)


def test_one_change_counts_once() -> None:
    assert kinds("Most services restarted.\n", "All services restarted.\n").count("scope") == 1
    assert kinds("Admins may delete projects.\n", "Admins can delete projects.\n") == ["certainty"]


def test_list_numbers_in_material_are_not_values() -> None:
    result = diff.compare("We need controllers.\n", "We need two controllers.\n",
                          materials="2. The new access points handle up to 60 devices each.\n")
    assert [m["value"] for m in result.material["numbers_not_in_material"]] == ["2"]


def test_contractions_in_removed_contrast_are_not_counted() -> None:
    o = "This PR doesn't just fix a bug — it's a rethink. It's worth noting that retries are capped.\n"
    r = "This PR fixes a bug and rethinks retries. Retries are capped.\n"
    assert diff.compare(o, r).stiffness == []


def test_folded_label_word_is_not_a_gone_name() -> None:
    assert kinds("1. **Slower responses**: Peak latency exceeded 3 seconds.\n",
                 "1. Responses slowed down, and peak latency exceeded 3 seconds.\n") == []


def test_name_replaced_in_a_sentence() -> None:
    o = "Dana is the owner. The budget was approved by Dana. Lee reviewed it.\n"
    r = "Dana is the owner. The budget was approved by Lee. Lee reviewed it.\n"
    assert "name" in kinds(o, r)


@pytest.mark.parametrize(("orig", "rev"), [
    ("1. **Slower responses**: Peak latency exceeded 3 seconds.\n2. **Security**: Passwords are hashed with bcrypt.\n",
     "1. Responses slowed down, and peak latency exceeded 3 seconds.\n2. For security, passwords are hashed with bcrypt.\n"),
    ("## The North Star\n\nText.\n", "## Onboarding goal\n\nText.\n"),
    ("## Results\n\nThe pilot reduced support tickets by 25% over six weeks, a truly remarkable result.\n\n## Conclusion\n\n"
     "Overall, the pilot cut tickets by 25%.\n", "## Results\n\nThe pilot reduced support tickets by 25% over six weeks.\n"),
    ("Do not run the migration during business hours. It locks the users table. To sum up, never run it during "
     "business hours.\n", "Do not run the migration during business hours, because it locks the users table.\n"),
    ("A manager's approval isn't required for changes under $500.\n",
     "A manager's approval is not required for changes under $500.\n"),
    ("You won't need to restart.\n", "You will not need to restart.\n"),
    ("It is possible that the job might hang.\n", "The job might hang.\n"),
    ("Perhaps we could ship on Friday.\n", "We could ship on Friday.\n"),
    ("The migration took a while, but it finished without errors.\n",
     "The migration took a long time, but it finished without errors.\n"),
    ("It has happened before.\n", "It has happened in the past.\n"),
    ("You may see a warning about an unsigned driver during the install.\n",
     "A warning about an unsigned driver may appear during the install.\n"),
])
def test_set7_diff_review_harmless(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("Track p95 and p99 latency on the dashboard.\n", "Track p50 latency on the dashboard.\n", "number"),
    ("The p95 latency improved after the fix.\n", "The p50 latency improved after the fix.\n", "number"),
    ("Send the invoice to Maria. Maria handles billing questions.\n",
     "Send the invoice to Tom. Maria handles billing questions.\n", "name"),
])
def test_set7_diff_review_counted(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


def test_deleted_condition_sentence_gets_a_review() -> None:
    reviews = review_kinds("Restart the worker. Do this only if the queue is empty.\n", "Restart the worker.\n")
    assert "deleted" in reviews


def test_markers_inside_underscore_emphasis_are_seen() -> None:
    assert "negation" in kinds("The job does _not_ retry.\n", "The job retries.\n")
    assert "certainty" in kinds("The fix __may__ help.\n", "The fix helps.\n")


# ---- set 8 review

@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("Annual subscriptions are eligible for a refund.\n", "All subscriptions are eligible for a refund.\n", "scope"),
    ("Enterprise customers get SSO.\n", "All customers get SSO.\n", "scope"),
    ("Under normal traffic, the API responds in 200 ms.\n", "The API responds in 200 ms.\n", "condition"),
    ("During peak hours, deploys are blocked.\n", "Deploys are blocked.\n", "condition"),
    ("Per the vendor, the outage was caused by a DNS change.\n", "The outage was caused by a DNS change.\n", "hearsay"),
    ("We may suspend accounts at our sole discretion.\n", "We may suspend accounts.\n", "condition"),
    ("Fees are non-refundable except where required by applicable law.\n", "Fees are non-refundable.\n", "condition"),
    ("Data refreshes daily.\n", "Data refreshes hourly.\n", "number"),
    ("The plan is billed monthly.\n", "The plan is billed annually.\n", "number"),
])
def test_set8_meaning_changes_are_counted(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("In production, we run 3 replicas.\n", "We run 3 replicas in production.\n"),
    ("Backups run nightly.\n", "Backups run every night.\n"),
    ("You will need to restart the service after the upgrade.\n", "Restart the service after the upgrade.\n"),
    ("For more details, see the guide.\n", "See the guide for more details.\n"),
])
def test_set8_harmless_rewrites(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_section_is_not_a_name() -> None:
    assert "name" not in kinds("Refunds follow Section 9.\n", "Refunds follow the policy.\n")


def test_owner_swap_message_shows_full_names() -> None:
    o = "- [ ] Lena Ortiz: Draft the plan\n- [ ] Marco Feld: Share the notes\n"
    r = "- [ ] Marco Feld: Draft the plan\n- [ ] Lena Ortiz: Share the notes\n"
    messages = [x.message for x in diff.compare(o, r).risks if x.kind == "name_order"]
    assert any('"Lena Ortiz" moved from line 1 to line 2' in m for m in messages)


def test_fact_gaps_ignore_digits_inside_names() -> None:
    result = diff.compare("x\n", "Query latency improved significantly after the Q3 release.\n", want_fact_gaps=True)
    assert [g.kind for g in result.fact_gaps] == ["degree"]


def test_full_diff_shows_one_line_per_one_line_change() -> None:
    full = diff.compare("We use a robust pipeline.\n", "We use a pipeline.\n").full_diff
    assert "  ~ " in full and "  - " not in full


def test_three_to_one_merge_is_compared_as_one() -> None:
    o = "The migration ran overnight. It may have skipped a few rows. We have not checked the totals.\n"
    r = "The migration ran overnight and skipped a few rows; we have checked the totals.\n"
    assert {"negation", "certainty"} <= set(kinds(o, r))


def test_one_to_three_split_keeps_numbers() -> None:
    o = ("We propose moving CI to self-hosted runners, which would cut the monthly bill from $4,000 to $1,500 and "
         "shorten queue times from 10 minutes to 2 minutes.\n")
    r = ("We propose moving CI to self-hosted runners. This would cut the monthly bill from $4,000 to $1,500. It would "
         "also shorten queue times from 10 minutes to 2 minutes.\n")
    assert "number" not in kinds(o, r)


def test_title_case_labels_are_not_names() -> None:
    o = "- **Faster Startup**: The CLI starts in 200 ms instead of 900 ms.\n- **Key Takeaway**: Cache needs an owner.\n"
    r = "- The CLI starts faster, in 200 ms instead of 900 ms.\n- The cache needs an owner.\n"
    assert "name" not in kinds(o, r)


@pytest.mark.parametrize(("orig", "rev"), [
    ("Large uploads can time out on slow links.\n", "Large uploads may time out on slow links.\n"),
    ("Users might see a delay during the upgrade.\n", "Users may see a delay during the upgrade.\n"),
    ("The launch date is TBD.\n", "The launch date is not decided yet.\n"),
])
def test_set8_diff_review_harmless(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


@pytest.mark.parametrize(("orig", "rev"), [
    ("Contractors mustn't share badges.\n", "Contractors shouldn't share badges.\n"),
    ("You shouldn't run the migration on the primary.\n", "Never run the migration on the primary.\n"),
    ("Visitors mustn't enter the server room.\n", "Visitors don't enter the server room.\n"),
])
def test_contracted_prohibitions(orig: str, rev: str) -> None:
    assert "obligation" in kinds(orig, rev)


def test_two_scope_changes_both_count() -> None:
    assert kinds("Only admins can delete some projects.\n", "Admins can delete all projects.\n").count("scope") == 2


def test_time_zone_after_pm() -> None:
    assert "number" in kinds("The call is at 3 p.m. PST.\n", "The call is at 3 p.m. EST.\n")


# ---- set 9 review

@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("Pass rates rose by approximately 41% [2].\n", "Pass rates rose by 41%.\n", "approximation"),
    ("We saw approximately 41% fewer flakes across 3 suites.\n", "We saw 41% fewer flakes across 4 suites.\n",
     "approximation"),
    ("Set `retention_days = 30` in the config.\n", "Set `retention_days = 7` in the config.\n", "code"),
    ("Per Priya, the fix shipped.\n", "The fix shipped.\n", "hearsay"),
    ("The job runs once per minute.\n", "The job runs once per second.\n", "number"),
    ("Tokens expire after an hour.\n", "Tokens expire after a minute.\n", "number"),
    ("Health checks run every few seconds.\n", "Health checks run every few minutes.\n", "number"),
    ("Windows support is currently experimental.\n", "Windows support is experimental.\n", "condition"),
    ("Backups run on Tuesdays and Saturdays.\n", "Backups run on Tuesdays and Sundays.\n", "number"),
])
def test_set9_meaning_changes_are_counted(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("The service handles 200 requests per second.\n", "The service handles 200 requests every second.\n"),
    ("Quotas are set per user.\n", "Quotas apply to each user.\n"),
    ("We need your approval by Friday, June 12, so that transfers can be finalized before the July planning cycle. "
     "Please approve the budget and the two internal transfers.\n",
     "Could you approve the budget and the two internal transfers by Friday, June 12? We need your approval by then "
     "so that transfers can be finalized before the July planning cycle.\n"),
    ("Wait a second before retrying.\n", "Pause briefly before retrying.\n"),
    ("In today's fast-paced world, our tool helps teams ship.\n", "Our tool helps teams ship.\n"),
    ("At the end of the day, the fix works.\n", "The fix works.\n"),
])
def test_set9_harmless_rewrites(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_citation_counts_once() -> None:
    assert kinds("Flakiness rose (Smith, 2020).\n", "Flakiness rose.\n") == ["citation"]


@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("We must rotate the signing keys every 90 days.\n", "Signing keys are rotated every 90 days.\n", "obligation"),
    ("You must enable two-factor authentication before you deploy.\n",
     "Two-factor authentication is enabled before you deploy.\n", "obligation"),
    ("In production, debug logging is disabled.\n", "Debug logging is disabled.\n", "condition"),
    ("On weekends, support responds within 4 hours.\n", "Support responds within 4 hours.\n", "condition"),
    ("Attendees: Dana Kim, Lee Park.\n\nDana: send the notes by Friday.\n\nLee: update the docs by Monday.\n",
     "Attendees: Dana Kim, Lee Park.\n\nLee: send the notes by Friday.\n\nDana: update the docs by Monday.\n", "name"),
])
def test_set9_diff_review_counted(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("The plan costs $10 per month.\n", "The plan costs $10 a month.\n"),
    ("The company provides one laptop per employee.\n", "The company provides one laptop for each employee.\n"),
    ("On a daily basis, the job exports 5,000 rows.\n", "The job exports 5,000 rows daily.\n"),
    ("If you have questions, please don't hesitate to contact me.\n", "If you have questions, please contact me.\n"),
    ("We launched the feature a month ago.\n", "We launched the feature last month.\n"),
    ("The free plan includes 3 projects. The Pro plan includes 20 projects. The Team plan has no limit.\n",
     "The free plan includes 3 projects, the Pro plan 20, and the Team plan has no limit.\n"),
    ("Customers reportedly saw errors after the deploy.\n", "Customers say they saw errors after the deploy.\n"),
])
def test_set9_diff_review_harmless(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_owner_swap_counts_once_per_name() -> None:
    assert kinds("- Owner: Dana\n- Reviewer: Lee\n", "- Owner: Lee\n- Reviewer: Dana\n").count("name_order") == 2
