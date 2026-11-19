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


# ---- set 10 review

@pytest.mark.parametrize("qualifier", [
    ", subject to manager approval", " with manager approval", " with prior written consent from Finance",
    " where applicable", " to the extent permitted by law", " on a case-by-case basis",
])
def test_formal_qualifiers_are_conditions(qualifier: str) -> None:
    o = f"Employees may work remotely up to three days per week{qualifier}.\n"
    r = "Employees may work remotely up to three days per week.\n"
    assert "condition" in kinds(o, r)


def test_frequency_messages_show_the_phrase() -> None:
    result = diff.compare("Backups run every weekday.\n", "Backups run every day.\n")
    assert any("every weekday" in x.message for x in result.risks if x.counted)
    assert "number" in kinds("Reviews happen every six months.\n", "Reviews happen annually.\n")


def test_this_with_a_named_noun_is_not_a_connection_review() -> None:
    o = "Our policy covers remote work.\n\nIt is important to note that this policy fosters trust.\n"
    r = "Our policy covers remote work.\n\nThis policy fosters trust.\n"
    assert "connection" not in review_kinds(o, r)


def test_exclamation_drop_is_reference_for_manuals() -> None:
    result = diff.compare("Run the installer! It takes a minute.\n", "Run the installer. It takes a minute.\n", "manual")
    assert result.energy == [] and result.energy_reference_items


def test_reference_fact_gap() -> None:
    result = diff.compare("x\n", "Reset your password before the deadline.\n", want_fact_gaps=True)
    assert [g.kind for g in result.fact_gaps] == ["reference"]


def test_word_diff_keeps_decimals_together() -> None:
    assert "1+}.{+8" not in diff.word_diff("Sync is faster on large records.", "Sync takes 1.8 seconds on large records.")


@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("The basic plan costs $10 per month. The pro plan costs $25 per month.\n",
     "The basic plan costs $25 per month. The pro plan costs $10 per month.\n", "number"),
    ("Alice is off on Monday. Bob is off on Friday.\n", "Alice is off on Friday. Bob is off on Monday.\n", "number"),
    ("> **Warning:** Back up `/var/lib/acme/data` first.\n", "> **Warning:** Back up `/var/lib/acme` first.\n", "code"),
    ("Two or more reviewers must approve.\n", "Two reviewers must approve.\n", "approximation"),
    ("Requires Node.js 18 or later.\n", "Requires Node.js 18.\n", "approximation"),
    ("We changed the pool size from 50 to 5.\n", "We changed the pool size from 5 to 50.\n", "number"),
    ("Enterprise customers get priority support.\n", "Every customer gets priority support.\n", "scope"),
    ("Rotate the keys every other day.\n", "Rotate the keys daily.\n", "number"),
    ("We were told the servers are old.\n", "The servers are old.\n", "hearsay"),
    ("Submit no later than 5 pm.\n", "Submit later than 5 pm.\n", "negation"),
])
def test_set10_diff_review_counted(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("You must not share your password.\n", "Do not share your password.\n"),
    ("You'll need to restart the app after updating.\n", "Restart the app after updating.\n"),
    ("You must first install Node 18.\n", "First install Node 18.\n"),
    ("To apply the change, you must restart the server.\n", "To apply the change, restart the server.\n"),
    ("For this reason, we chose Postgres.\n", "Therefore, we chose Postgres.\n"),
    ("At least one reviewer must approve.\n", "One or more reviewers must approve.\n"),
    ("- [ ] Dana Kim: Look into the flaky tests\n", "- [ ] Dana Kim: Investigate the flaky tests\n"),
    ("Details are at https://example.com/docs.\n", "Details are in [the docs](https://example.com/docs).\n"),
    ("Payroll runs every 2 weeks.\n", "Payroll runs biweekly.\n"),
    ("The meeting lasts an hour.\n", "The meeting lasts one hour.\n"),
    ("Rate limits apply per API key.\n", "Rate limits apply to each API key.\n"),
    ("Latency fell by 40%. This 40% drop came from the new cache.\n", "Latency fell by 40%, thanks to the new cache.\n"),
    ("Send the draft to Legal by Fri.\n", "Send the draft to Legal by Friday.\n"),
    ("It's no secret that the build is slow.\n", "The build is slow.\n"),
    ("Submit it no later than Friday.\n", "Submit it by Friday.\n"),
    ("Before you begin, install Docker.\n", "Install Docker first.\n"),
])
def test_set10_diff_review_harmless(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_repeated_value_moved_does_not_crash() -> None:
    diff.compare("The trial lasts 14 days, and refunds are possible within 14 days. Contact support to cancel.\n",
                 "The trial lasts two weeks, and refunds are possible during the trial. Contact support within 14 days "
                 "to cancel.\n")


def test_guarantees_counts_once() -> None:
    assert kinds("The checksum detects corruption.\n", "The checksum guarantees that corruption is detected.\n",
                 "manual") == ["commitment"]


def test_owner_swap_counts_once_with_full_names() -> None:
    o = "- [ ] Lena Ortiz: Draft the plan\n- [ ] Marco Feld: Share the notes\n"
    r = "- [ ] Marco Feld: Draft the plan\n- [ ] Lena Ortiz: Share the notes\n"
    assert kinds(o, r) == ["name_order", "name_order"]


# ---- set 11 review

@pytest.mark.parametrize(("orig", "rev"), [
    ("Timeouts went from 30 seconds to 10 seconds.\n", "Timeouts went from 10 seconds to 30 seconds.\n"),
    ("We shortened the retry interval from 1 second to 0.5 seconds.\n",
     "We shortened the retry interval from 0.5 seconds to 1 second.\n"),
    ("Latency dropped from about 800 milliseconds to roughly 120 milliseconds.\n",
     "Latency dropped from about 120 milliseconds to roughly 800 milliseconds.\n"),
])
def test_reversed_from_to_with_units_counts_once(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == ["number"]


@pytest.mark.parametrize(("orig", "rev"), [
    ("Churn in the SMB segment was not the main drag on margin. Infrastructure costs were.\n",
     "Infrastructure costs, not churn in the SMB segment, were the main drag on margin.\n"),
    ("In today's fast-paced SaaS landscape, Q3 was a strong quarter.\n", "Q3 was a strong quarter.\n"),
])
def test_set11_harmless(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_within_n_days_of_keeps_the_time_limit() -> None:
    assert "condition" not in kinds("Submit the request soon after your first login.\n",
                                    "Submit the request within 2 business days of your first login.\n")


def test_you_may_removed_counts_once_as_permission() -> None:
    assert kinds("You may set a custom timeout.\n", "Set a custom timeout.\n") == ["permission"]


def test_every_monday_is_weekly() -> None:
    result = diff.compare("Reports run every Monday.\n", "Reports run weekly.\n")
    assert not any("Frequency" in x.message for x in result.risks if x.counted)


def test_heading_colon_removal_is_not_a_review() -> None:
    assert "heading" not in review_kinds("## Summary:\n\nText.\n", "## Summary\n\nText.\n")


def test_reference_gap_with_a_version_name() -> None:
    result = diff.compare("x\n", "We should triage this before the 3.8.3 cut, as discussed.\n", want_fact_gaps=True)
    assert [g.kind for g in result.fact_gaps] == ["reference"]


@pytest.mark.parametrize(("orig", "rev"), [
    ("> [!WARNING]\n> Truncating the table removes every row.\n", "> [!WARNING]\n> This removes every row in the table.\n"),
    ("> [!WARNING]\n> You must not run `drop_all()` on production.\n", "> [!WARNING]\n> Do not run `drop_all()` on production.\n"),
    ("> **Warning:** You must not run the script twice.\n", "> **Warning:** Do not run the script twice.\n"),
    ("- Priya: Spearhead the migration plan\n", "- Priya: Lead the migration plan\n"),
    ("Feel free to reach out if anything is unclear.\n", "Let me know if anything is unclear.\n"),
    ("Per our conversation, I've attached the revised quote.\n", "As we discussed, I've attached the revised quote.\n"),
    ("Per the vendor's docs, the limit is 100 requests.\n", "The vendor's docs say the limit is 100 requests.\n"),
    ("Delete old backups weekly.\n", "Delete all old backups weekly.\n"),
    ("Backups run every 6 hours.\n", "Backups run every six hours.\n"),
    ("Rotate logs every 2 days.\n", "Rotate logs every other day.\n"),
    ("You will then need to run `terraform apply`.\n", "Then run `terraform apply`.\n"),
    ("Due May 5 (Fri).\n", "Due Friday, May 5.\n"),
    ("Office hours: Tue and Thu.\n", "Office hours: Tuesday and Thursday.\n"),
    ("Open Mon-Fri.\n", "Open Monday to Friday.\n"),
])
def test_set11_diff_review_harmless(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("Retries wait 30 seconds, and the timeout is configurable.\n", "Retries wait 30 seconds. The timeout is 30 seconds.\n",
     "number"),
    ("You must restart the service.\n", "If you like, restart the service.\n", "obligation"),
    ("Submit no later than Friday.\n", "Submit after Friday.\n", "negation"),
])
def test_set11_diff_review_counted(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


def test_typically_gone_is_reviewed() -> None:
    assert "quantifier_gone" in review_kinds("Builds typically take 5 minutes.\n", "Builds take 5 minutes.\n")


@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("The bottleneck was not the database. It was the network.\n", "The bottleneck was the database, not the network.\n",
     "negation"),
    ("Speed is not the goal. Predictability is.\n", "Speed, not predictability, is the goal.\n", "negation"),
    ("The delay was caused by the supplier, not by our team.\n", "The delay was caused by our team, not by the supplier.\n",
     "negation"),
    ("Write to the replica, not to the primary.\n", "Write to the primary, not to the replica.\n", "negation"),
    ("The limit is 200 requests, not 20.\n", "The limit is 20 requests, not 200.\n", "negation"),
    ("Attendees: Dana, Lee, Priya\n\n- Action: Dana to send the invoice by Friday.\n",
     "Attendees: Dana, Lee, Priya\n\n- Action: Priya to send the invoice by Friday.\n", "name"),
    ("Tinyq requires Python 3.10 or later.\n", "Tinyq requires Python 3.1 or later.\n", "number"),
    ("Approval from the CFO is required.\n", "Approval from the CEO is required.\n", "name"),
    ("Send it to QA before Friday.\n", "Send it to UAT before Friday.\n", "name"),
    ("We rarely see this error in production.\n", "We see this error in production.\n", "negation"),
    ("Experts believe the vulnerability was exploited.\n", "The vulnerability was exploited.\n", "hearsay"),
    ("Analysts estimate the market at $4B.\n", "The market is $4B.\n", "hearsay"),
    ("Run the backup before the upgrade.\n", "Run the backup after the upgrade.\n", "condition"),
    ("The warranty covers all parts except the battery.\n", "The warranty covers all parts.\n", "condition"),
    ("Restart all workers after changing the setting.\n", "Restart the affected workers after changing the setting.\n",
     "scope"),
    ("All employees must complete the training.\n", "New employees must complete the training.\n", "scope"),
    ("Every request is logged.\n", "Failed requests are logged.\n", "scope"),
    ("Reports are due every other Friday.\n", "Reports are due every Friday.\n", "number"),
    ("Backups run nightly. Reports are sent nightly.\n", "Backups run nightly. Reports are sent.\n", "number"),
])
def test_set12_diff_review_counted(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("Speed is not the goal. Predictability is.\n", "Predictability, not speed, is the goal.\n"),
    ("The bottleneck was not the database. It was the network.\n", "The bottleneck was the network, not the database.\n"),
    ("- Action: Update to the latest version.\n", "- Action: update to the latest version.\n"),
    ("The fee is $2.50 per seat.\n", "The fee is $2.5 per seat.\n"),
    ("Our SLA covers the API.\n", "Our service-level agreement covers the API.\n"),
    ("The CEO will present the ARR numbers.\n", "The CEO will present the annual recurring revenue.\n"),
    ("You're going to need to clear the cache after the upgrade.\n", "Clear the cache after the upgrade.\n"),
    ("However, the cache was very cold at startup.\n", "However, the cache was cold at startup.\n"),
    ("Also, just a quick reminder: the office is closed on Monday.\n", "Also, a reminder: the office is closed on Monday.\n"),
    ("Standups happen each Monday at 9:30.\n", "Standups happen every Monday at 9:30.\n"),
    ("Reports are due every other Friday.\n", "Reports are due every second Friday.\n"),
    ("We meet weekly, every Tuesday.\n", "We meet every Tuesday.\n"),
    ("Attendees may bring one guest.\n", "Attendees are allowed to bring one guest.\n"),
    ("In this guide, we'll walk you through everything you need to know to get started.\n",
     "This guide shows how to install and run the tool.\n"),
    ("All employees must complete the training.\n", "Employees must complete the training.\n"),
    ("Restart all workers.\n", "Restart every worker.\n"),
    ("We rarely see this error.\n", "This error is rare.\n"),
    ("Other than that, the release is on track.\n", "Otherwise, the release is on track.\n"),
])
def test_set12_diff_review_harmless(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_deleted_clause_keeps_frequency_found_elsewhere() -> None:
    orig = ("This PR fixes the flaky failures in our nightly job.\n\n"
            "Closes #482. Thanks for reviewing, I hope this helps make our nightly runs more reliable!\n")
    rev = "This PR fixes the flaky failures in our nightly job.\n\nCloses #482. Thanks for reviewing.\n"
    result = diff.compare(orig, rev, "pr")
    assert result.counted == 0
    assert any(r.kind == "number" and not r.counted and "still appears" in r.message for r in result.risks)


def test_code_risk_names_its_line() -> None:
    orig = "- Set `retries` to `5` in staging.\n- Set `timeout` to `5` in production.\n"
    rev = "- Set `retries` to `5` in staging.\n- Set `timeout` to `3` in production.\n"
    risk = next(r for r in diff.compare(orig, rev).risks if r.kind == "code")
    assert (risk.orig_line, risk.rev_line) == (2, 2) and "production" in risk.original


def test_closing_section_removed_with_heading_colon_fix() -> None:
    orig = "# Tool\n\n## Usage:\n\nRun it.\n\n## Conclusion\n\nThat is all.\n"
    rev = "# Tool\n\n## Usage\n\nRun it.\n"
    messages = [v.message for v in diff.compare(orig, rev, "manual").reviews if v.kind == "heading"]
    assert messages and messages[0].startswith("Closing section removed")


def test_material_skips_diff_hunk_headers() -> None:
    material = "--- a/job.py\n+++ b/job.py\n@@ -12,6 +12,14 @@ import os\n-TIMEOUT = 8\n+TIMEOUT = 480\n"
    result = diff.material_check(diff.tx.parse("Locks expire after 6 hours.\n"), material, "")
    assert [m["value"] for m in result["numbers_not_in_material"]] == ["6"]


def test_fact_gaps_list_vague_owner_in_conditional() -> None:
    gaps, _note = diff.fact_gaps(diff.tx.parse("Escalate to the appropriate team lead if the issue is not resolved.\n"))
    assert [g.kind for g in gaps] == ["reference"]


def test_removed_role_acronym_is_listed() -> None:
    reviews = diff.compare("Approval from the CFO is required.\n", "Approval is required.\n").reviews
    assert any(v.kind == "words_gone" and "CFO" in v.message for v in reviews)


@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("We did not choose Redis. We chose Postgres.\n", "We chose Redis, not Postgres.\n", "negation"),
    ("We didn't do a big-bang cutover. We ran both clusters side by side.\n",
     "We didn't run both clusters side by side; we did a big-bang cutover.\n", "negation"),
    ("The outage was not caused by the deploy. It was caused by a disk failure.\n",
     "The outage was caused by the deploy, not by a disk failure.\n", "negation"),
    ("Use the CLI, not the web UI.\n", "Use the web UI instead of the CLI.\n", "negation"),
    ("Customers were unable to log in.\n", "Customers logged in.\n", "negation"),
    ("Run the backup before the upgrade.\n", "Run the backup after the upgrade.\n", "condition"),
])
def test_set13_diff_review_counted(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("We did not choose Redis. We chose Postgres.\n", "We chose Postgres, not Redis.\n"),
    ("At this point in time, we do not support SAML.\n", "We do not currently support SAML.\n"),
    ("The outage was not caused by the deploy. It was caused by a disk failure.\n",
     "The outage was caused by a disk failure, not by the deploy.\n"),
    ("The delay was not due to the vendor. It was due to our own testing.\n",
     "The delay was due to our own testing, not the vendor.\n"),
    ("The ticket was not closed by Dana. Raj closed it.\n", "Raj closed the ticket, not Dana.\n"),
    ("The API will not be available on Friday. It will be available Monday.\n",
     "The API will be available Monday, not Friday.\n"),
    ("## Action items\n\n- Follow-up: Talk to finance about the invoice.\n",
     "## Action items\n\n- Follow-up: Ask finance about the invoice.\n"),
    ("Hi all,\n\nWe all need to update our passwords by Friday.\n",
     "Hi all,\n\nEveryone needs to update their password by Friday.\n"),
    ("Restart the service (after you back up the config file).\n",
     "Back up the config file before you restart the service.\n"),
    ("Wait until the build finishes, then deploy.\n", "Deploy after the build finishes.\n"),
    ("We asked the vendor about the delay. They think the parts will arrive on Monday.\n",
     "We asked the vendor about the delay. The vendor thinks the parts will arrive on Monday.\n"),
    ("Everyone except the on-call engineer can leave at 5 pm.\n",
     "Everyone apart from the on-call engineer can leave at 5 pm.\n"),
    ("Everyone except the on-call engineer can leave at 5 pm.\n", "Everyone but the on-call engineer can leave at 5 pm.\n"),
    ("Other than the login bug, the release went smoothly.\n", "Apart from the login bug, the release went smoothly.\n"),
    ("Revenue grew 8% last year.\n", "Last year, revenue grew 8%.\n"),
    ("Use the CLI, not the web UI, for bulk imports.\n", "Use the CLI instead of the web UI for bulk imports.\n"),
    ("Customers were unable to log in.\n", "Customers could not log in.\n"),
    ("Hopefully the patch lands this week.\n", "We hope the patch lands this week.\n"),
    ("Standups are on Mondays at 10:00.\n", "Standups are every Monday at 10:00.\n"),
    ("In this post, we'll look at how the migration went.\n", "We'll look at how the migration went.\n"),
    ("Staying on supported software is more than just a nice-to-have.\n",
     "Staying on supported software is more than a nice-to-have.\n"),
    ("The vendor failed to deliver on time, which delayed the launch.\n", "The vendor delivered late, which delayed the launch.\n"),
])
def test_set13_diff_review_harmless(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_material_reports_reversed_order_and_frequency() -> None:
    material = "default_pool_size 100 -> 400\nWe will get hourly call-volume reports.\n"
    final = diff.tx.parse("We raised the pool size from 400 to 100.\n\nWe will get daily call-volume reports.\n")
    values = [m["value"] for m in diff.material_check(final, material, "")["units_dates_not_in_material"]]
    assert any("order" in v for v in values) and "day (frequency)" in values
    good = diff.tx.parse("We raised the pool size from 100 to 400.\n\nWe will get hourly call-volume reports.\n")
    assert diff.material_check(good, material, "")["units_dates_not_in_material"] == []


def test_fill_from_material_notes_month_and_commitment() -> None:
    material = "We'll get hourly call-volume reports. Support ends March 31, 2027.\n"
    result = diff.compare("The tool integrates with our CRM. Support will end soon.\n",
                          "The tool integrates with our CRM, and we will get hourly call-volume reports. "
                          "Support will end on March 31, 2027.\n", materials=material)
    month = next(r for r in result.risks if r.message.startswith("Month or weekday changed"))
    assert "elsewhere in the original or material" in month.message
    assert any(r.kind == "commitment" and not r.counted for r in result.risks)


def test_code_block_risk_points_at_changed_line() -> None:
    orig = "Config:\n\n```yaml\nserver:\n  host: a\n  retries: 3\n```\n"
    rev = "Config:\n\n```yaml\nserver:\n  host: a\n  retries: 5\n```\n"
    risk = next(r for r in diff.compare(orig, rev).risks if r.kind == "code")
    assert (risk.orig_line, risk.original, risk.revised) == (6, "retries: 3", "retries: 5")
    assert "\n" not in risk.message


@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("IT Security, not the employee's manager, decides whether the device is wiped.\n",
     "The employee's manager, not IT Security, decides whether the device is wiped.\n", "negation"),
    ("IT, not the manager, decides.\n", "The manager, not IT, decides.\n", "negation"),
    ("We will move from an annual review to a semi-annual review.\n",
     "We will move from a semi-annual review to an annual review.\n", "number"),
    ("We switched from a weekly run to a daily run.\n", "We switched from a daily run to a weekly run.\n", "number"),
    ("You will see a warning when you open the file.\n", "You will see a warning.\n", "condition"),
])
def test_set14_diff_counted(orig: str, rev: str, kind: str) -> None:
    assert kind in kinds(orig, rev)


def test_set14_reversed_order_message() -> None:
    risks = diff.compare("We switched from a weekly run to a daily run.\n",
                         "We switched from a daily run to a weekly run.\n").risks
    assert any(r.kind == "number" and r.counted and "Order reversed" in r.message for r in risks)


def test_set14_actor_from_material_is_review() -> None:
    result = diff.compare("Our engineering team is investigating the issue.\n",
                          "Raj Patel from our engineering team is investigating the issue.\n", "mail",
                          materials="Owner: Raj Patel (SRE)\n")
    review = next(v for v in result.reviews if v.kind == "actor_added")
    assert "comes from the material" in review.message


def test_set14_instruction_replaces_when_clause() -> None:
    assert kinds("2. Verify the installation (you should see `2.4.1` when you run `logsift --version`).\n",
                 "2. Run `logsift --version` to verify the installation; you should see `2.4.1`.\n", "manual") == []


def test_set14_numbered_closing_heading_removed() -> None:
    orig = "# Policy\n\n## 1. Scope\n\nApplies to staff.\n\n## 7. Conclusion\n\nThat is all.\n"
    rev = "# Policy\n\n## 1. Scope\n\nApplies to staff.\n"
    result = diff.compare(orig, rev, "formal")
    assert not [r for r in result.risks if r.counted]
    assert any(v.kind == "heading" and "Closing section removed" in v.message for v in result.reviews)


@pytest.mark.parametrize(("text", "listed"), [
    ("To mitigate risk, we will run both paths in parallel for at least four weeks before switching traffic.\n", False),
    ("Send it before the deadline of Friday, December 18.\n", False),
    ("Send it before the deadline.\n", True),
])
def test_set14_fact_gaps_reference(text: str, listed: bool) -> None:
    gaps = diff.compare(text, text, want_fact_gaps=True).fact_gaps
    assert bool(gaps) is listed
    if listed:
        assert gaps[0].kind == "reference"


@pytest.mark.parametrize(("orig", "rev"), [
    ("We did not ship the fix on Friday. We shipped it on Monday.\n", "We shipped the fix on Monday, not on Friday.\n"),
    ("The team did not fix the bug in the parser. They fixed it in the lexer.\n",
     "The team fixed the bug in the lexer, not in the parser.\n"),
    ("Don't send the report to the whole team. Send it to the leads.\n", "Send the report to the leads, not the whole team.\n"),
    ("We're not able to extend the discount, but we may be able to waive the setup fee.\n",
     "We can't extend the discount, but we may be able to waive the setup fee.\n"),
    ("We didn't need a new tool. We needed a shared way to use the old one.\n",
     "We needed a shared way to use the old one, not a new tool.\n"),
])
def test_phase0_correct_joins_are_not_swaps(orig: str, rev: str) -> None:
    assert "negation" not in kinds(orig, rev)


def test_phase0_wrong_join_with_need_is_a_swap() -> None:
    assert "negation" in kinds("We didn't need a new tool. We needed a shared way to use the old one.\n",
                               "We needed a new tool, not a shared way to use the old one.\n")


# loop 1: false positives on harmless rewrites, each with a nearby change that stays caught

@pytest.mark.parametrize(("orig", "rev"), [
    ("The service is currently in preview.\n", "The service is in preview.\n"),
    ("Support is currently reviewing your ticket.\n", "Support is reviewing your ticket.\n"),
    ("The bridge is currently closed.\n", "The bridge is still closed.\n"),
])
def test_loop1_ongoing_currently_dropped(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_loop1_currently_on_a_plain_state_still_counted() -> None:
    assert "condition" in kinds("Currently, shipping is free.\n", "Shipping is free.\n")


@pytest.mark.parametrize(("orig", "rev"), [
    ("We support two platforms: Linux and macOS.\n", "We support Linux and macOS.\n"),
    ("There are four steps to follow: plan, build, test and ship.\n", "Plan, build, test and ship.\n"),
    ("There are two causes. First, the disk filled up. Second, the alert was muted.\n",
     "First, the disk filled up. Second, the alert was muted.\n"),
])
def test_loop1_count_announcement_dropped(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


@pytest.mark.parametrize(("orig", "rev"), [
    ("We support two platforms: Linux and macOS.\n", "We support Linux.\n"),
    ("We support three platforms: Linux, macOS and Windows.\n", "We support Linux and macOS.\n"),
    ("We support two platforms.\n", "We support several platforms.\n"),
])
def test_loop1_count_with_a_dropped_item_still_counted(orig: str, rev: str) -> None:
    assert "number" in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("If the build fails, you should clear the cache.\n", "If the build fails, clear the cache.\n"),
    ("The token should be kept in a secrets manager.\n", "Keep the token in a secrets manager.\n"),
    ("Old snapshots must not be shared publicly.\n", "Do not share old snapshots publicly.\n"),
])
def test_loop1_should_or_passive_duty_as_imperative(orig: str, rev: str) -> None:
    assert "obligation" not in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("You should clear the cache.\n", "You can clear the cache.\n"),
    ("The token should be kept in a secrets manager.\n", "The token is kept in a secrets manager.\n"),
    ("The patch should fix the crash.\n", "The patch fixes the crash.\n"),
])
def test_loop1_should_still_counted_without_an_imperative(orig: str, rev: str) -> None:
    assert "obligation" in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("Please note that the lab is closed on Monday.\n", "The lab is closed on Monday.\n"),
    ("Please find attached the signed contract.\n", "The signed contract is attached.\n"),
    ("Please don't hesitate to call me.\n", "Call me anytime.\n"),
])
def test_loop1_courtesy_please_is_no_request(orig: str, rev: str) -> None:
    assert "request" not in kinds(orig, rev)


def test_loop1_real_please_still_counted() -> None:
    assert "request" in kinds("Please return the badge by Friday.\n", "Return the badge by Friday.\n")


@pytest.mark.parametrize(("orig", "rev"), [
    ("Ship it to Berlin, not to the Paris office.\n", "Ship it to Berlin rather than to the Paris office.\n"),
    ("Don't text the client; phone them instead.\n", "Phone the client instead of texting them.\n"),
    ("The total is 12, not 15.\n", "The total is 12 rather than 15.\n"),
])
def test_loop1_not_rewritten_as_rather_than(orig: str, rev: str) -> None:
    assert "negation" not in kinds(orig, rev)


def test_loop1_rather_than_on_the_other_side_still_counted() -> None:
    assert "negation" in kinds("Ship it to Berlin, not to the Paris office.\n",
                               "Ship it to the Paris office rather than to Berlin.\n")


@pytest.mark.parametrize(("orig", "rev"), [
    ("It is not clear who owns the bucket.\n", "It is unclear who owns the bucket.\n"),
    ("The backup has not been tested.\n", "The backup is untested.\n"),
    ("The supplier hasn't confirmed the price.\n", "The price is unconfirmed.\n"),
    ("The root cause has not been identified.\n", "The root cause is unknown.\n"),
    ("The budget is still pending.\n", "The board has not approved the budget yet.\n"),
    ("We are still waiting for the auditor.\n", "The auditor has not replied yet.\n"),
])
def test_loop1_negation_restated(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


@pytest.mark.parametrize(("orig", "rev"), [
    ("The backup has not been tested.\n", "The backup is tested.\n"),
    ("The budget is approved.\n", "The board has not approved the budget yet.\n"),
    ("The backup has not been tested.\n", "The backup is unencrypted.\n"),
])
def test_loop1_negation_changes_still_counted(orig: str, rev: str) -> None:
    assert kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("Users might possibly lose unsaved work.\n", "Users might lose unsaved work.\n"),
    ("You may potentially need a new token.\n", "You may need a new token.\n"),
    ("We think it's likely that the cable is loose.\n", "The cable is likely loose.\n"),
    ("The painting is believed to be a copy.\n", "The painting is thought to be a copy.\n"),
])
def test_loop1_hedge_kept_in_another_form(orig: str, rev: str) -> None:
    assert "certainty" not in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("Users might possibly lose unsaved work.\n", "Users lose unsaved work.\n"),
    ("The painting is thought to be a copy.\n", "The painting is a copy.\n"),
])
def test_loop1_dropped_hedge_still_counted(orig: str, rev: str) -> None:
    assert "certainty" in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("Don't forget to lock the door.\n", "Remember to lock the door.\n"),
    ("Payment is due no later than March 3.\n", "Payment is due March 3 at the latest.\n"),
])
def test_loop1_negation_idioms(orig: str, rev: str) -> None:
    assert "negation" not in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("The backup runs every 12 hours.\n", "The backup runs every twelve hours.\n"),
    ("The index is rebuilt every 30 minutes.\n", "The index is rebuilt every thirty minutes.\n"),
    ("Plans start at $5/month.\n", "Plans start at $5 per month.\n"),
    ("The council meets four times a year.\n", "The council meets quarterly.\n"),
    ("The hotline is staffed 24/7.\n", "The hotline is staffed around the clock.\n"),
    ("We demo every other Tuesday.\n", "We demo every two weeks, on Tuesdays.\n"),
    ("The shop is open Monday through Friday.\n", "The shop is open on weekdays.\n"),
    ("Dana will call on Tuesday.\n", "Dana will call on Tuesday (Tue).\n"),
    ("Files larger than 4 GB are skipped.\n", "Files over 4 GB are skipped.\n"),
])
def test_loop1_same_number_written_another_way(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


@pytest.mark.parametrize(("orig", "rev"), [
    ("The backup runs every 12 hours.\n", "The backup runs every twenty hours.\n"),
    ("Plans start at $5/month.\n", "Plans start at $5 per year.\n"),
    ("The council meets four times a year.\n", "The council meets monthly.\n"),
    ("The shop is open Monday through Friday.\n", "The shop is open Monday through Thursday.\n"),
    ("Files larger than 4 GB are skipped.\n", "Files under 4 GB are skipped.\n"),
])
def test_loop1_number_changes_still_counted(orig: str, rev: str) -> None:
    assert "number" in kinds(orig, rev) or "approximation" in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("Please submit the form before the deadline.\n", "Please submit the form ahead of the deadline.\n"),
    ("Exceptions are approved on a case-by-case basis.\n", "Exceptions are approved case by case.\n"),
    ("A parking pass is available upon request.\n", "A parking pass is available on request.\n"),
])
def test_loop1_condition_kept_in_another_form(orig: str, rev: str) -> None:
    assert "condition" not in kinds(orig, rev)


def test_loop1_condition_dropped_still_counted() -> None:
    assert "condition" in kinds("A parking pass is available upon request.\n", "A parking pass is available.\n")


@pytest.mark.parametrize(("orig", "rev"), [
    ("Members are exempt unless their lease states otherwise.\n", "Members are exempt unless their lease says otherwise.\n"),
    ("Some customers reported delays at checkout.\n", "Some customers said checkout was slow.\n"),
    ("Economists say inflation will ease.\n", "Economists expect inflation to ease.\n"),
])
def test_loop1_hearsay_kept_or_not_hearsay(orig: str, rev: str) -> None:
    assert "hearsay" not in kinds(orig, rev)


def test_loop1_dropped_attribution_still_counted() -> None:
    assert "hearsay" in kinds("Economists expect inflation to ease.\n", "Inflation will ease.\n")


def test_loop1_dropped_relative_restriction_counted() -> None:
    assert "scope" in kinds("Tenants who have paid the deposit can collect keys on Monday.\n",
                            "Tenants can collect keys on Monday.\n")


def test_loop1_relative_restriction_reworded_not_counted() -> None:
    assert "scope" not in kinds("Tenants who have paid the deposit can collect keys on Monday.\n",
                                "Tenants can collect keys on Monday once they have paid the deposit.\n")


@pytest.mark.parametrize(("orig", "rev", "kind"), [
    ("These logs deserve a closer look.\n", "These logs need attention.\n", "obligation"),
    ("No account required.\n", "You don't need an account.\n", "obligation"),
    ("Sign-off is not required for small fixes.\n", "Small fixes do not need sign-off.\n", "permission"),
    ("The tenant is responsible for paying the utilities.\n", "The tenant must pay the utilities.\n", "obligation"),
])
def test_loop1_obligation_and_permission_forms(orig: str, rev: str, kind: str) -> None:
    assert kind not in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("These logs deserve a closer look.\n", "These logs need a cleanup.\n"),
    ("An account is optional.\n", "You need an account.\n"),
    ("The tenant pays the utilities.\n", "The tenant is responsible for paying the utilities.\n"),
])
def test_loop1_obligation_changes_still_counted(orig: str, rev: str) -> None:
    assert "obligation" in kinds(orig, rev)


@pytest.mark.parametrize(("orig", "rev"), [
    ("Let me know if Monday suits you.\n", "Does Monday suit you?\n"),
    ("Please let me know if the room is free.\n", "Is the room free?\n"),
    ("I wanted to check whether the invoice was paid.\n", "Was the invoice paid?\n"),
])
def test_loop1_indirect_question_asked_directly(orig: str, rev: str) -> None:
    assert kinds(orig, rev) == []


def test_loop1_new_question_still_counted() -> None:
    assert "question" in kinds("The room is free.\n", "Is the room free?\n")
