from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import SCRIPTS

CHECK = SCRIPTS / "readyasu_check.py"


def run(args: list[str], cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CHECK), *args], cwd=cwd, input=stdin, capture_output=True,
                          text=True, encoding="utf-8", check=False)


def write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_run_and_verify(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "The job may fail.\n")
    fin = write(tmp_path / "f.md", "The job fails.\n")
    st = str(tmp_path / "st")
    p = run(["run", "--source", src, "--final", fin, "--state-dir", st, "--no-words"], tmp_path)
    assert p.returncode == 0, p.stderr
    lines = p.stdout.splitlines()
    assert lines[0].startswith("Ran the checks (attempt 1)")
    assert lines[1].startswith("readyasu-check: executed via=run") and "meaning_risk=1" in lines[1]
    assert any(ln.startswith("Stiffness check:") for ln in lines)
    assert any(ln.startswith("Review findings: original 0 → final 0") for ln in lines)
    assert lines[-1] == lines[1]
    v = run(["verify", "--final", fin, "--state-dir", st], tmp_path)
    assert v.returncode == 0
    assert "The hash matches the record" in v.stdout.splitlines()[0]
    assert v.stdout.splitlines()[1].startswith("readyasu-check: executed via=verify")
    assert (tmp_path / "st" / ".gitignore").read_text(encoding="utf-8").strip().endswith("*")


def test_attempts_and_mismatch(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "Hello there.\n")
    fin = write(tmp_path / "f.md", "Hello.\n")
    st = str(tmp_path / "st")
    assert run(["run", "--source", src, "--final", fin, "--state-dir", st, "--no-words"], tmp_path).returncode == 0
    write(tmp_path / "f.md", "Hello, friend.\n")
    p = run(["--source", src, "--final", fin, "--state-dir", st, "--no-words"], tmp_path)
    assert "attempt 2" in p.stdout.splitlines()[0]
    p = run(["run", "--source", src, "--final", fin, "--state-dir", st, "--no-words"], tmp_path)
    assert "unchanged final draft" in p.stdout.splitlines()[0]
    write(tmp_path / "f.md", "Hello, my friend.\n")
    p = run(["run", "--source", src, "--final", fin, "--state-dir", st, "--no-words"], tmp_path)
    assert "exceeds the one-revision rule" in p.stdout.splitlines()[0]
    write(tmp_path / "f.md", "Changed after run.\n")
    v = run(["verify", "--final", fin, "--state-dir", st], tmp_path)
    assert v.returncode == 1 and "reason=no_record" in v.stdout


def test_stdin_mode(tmp_path: Path) -> None:
    st = str(tmp_path / "st")
    data = "<<<readyasu:original>>>\nWait 3 seconds.\n<<<readyasu:final>>>\nWait 5 seconds.\n"
    p = run(["run", "--stdin", "--state-dir", st, "--no-words", "--fail-on", "meaning-risk"], tmp_path, data)
    assert p.returncode == 1
    assert "verify --final -" in p.stdout.splitlines()[0]
    v = run(["verify", "--final", "-", "--state-dir", st], tmp_path, "Wait 5 seconds.\n")
    assert v.returncode == 0


def test_stdin_bad_separator(tmp_path: Path) -> None:
    p = run(["run", "--stdin", "--no-words"], tmp_path, "<<<readyasu:orignal>>>\nx\n<<<readyasu:final>>>\ny\n")
    assert p.returncode == 2 and "not_run" in p.stdout


def test_usage_errors(tmp_path: Path) -> None:
    fin = write(tmp_path / "f.md", "Text.\n")
    empty = write(tmp_path / "e.md", "\n")
    assert run(["run", "--final", fin, "--no-words"], tmp_path).returncode == 2
    assert run(["run", "--source", fin, "--final", fin, "--no-words"], tmp_path).returncode == 2
    assert run(["run", "--source", fin, "--final", empty, "--no-words"], tmp_path).returncode == 2
    assert run(["run", "--material", fin, "--final", fin, "--no-words"], tmp_path).returncode == 2
    assert run(["run", "--source", fin, "--final", fin, "--run-id", "../x"], tmp_path).returncode == 2
    assert run(["run", "--source", fin, "--final", fin, "--doc-type", "x"], tmp_path).returncode == 2


def test_no_record(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "A.\n")
    fin = write(tmp_path / "f.md", "B.\n")
    st = tmp_path / "st"
    p = run(["run", "--source", src, "--final", fin, "--state-dir", str(st), "--no-record", "--no-words"], tmp_path)
    assert p.returncode == 0 and "unrecorded" in p.stdout.splitlines()[1]
    assert not st.exists()


def test_compose_mode(tmp_path: Path) -> None:
    mat = write(tmp_path / "m.txt", "<<<readyasu:material user's message>>>\nBackups are kept for 30 days.\n")
    fin = write(tmp_path / "f.md", "We keep backups for 45 days, and the old ones go away on a schedule.\n")
    p = run(["run", "--material", mat, "--final", fin, "--state-dir", str(tmp_path / "st"), "--no-words",
             "--fail-on", "meaning-risk", "--json"], tmp_path)
    data = json.loads(p.stdout)
    assert data["mode"] == "compose" and data["checks"] == ["lint", "material"]
    assert p.returncode == 1


def test_compose_adopts_similar_material(tmp_path: Path) -> None:
    mat = write(tmp_path / "m.txt", "The service may restart at night to apply updates for all customers.\n")
    fin = write(tmp_path / "f.md", "The service may restart at night to apply updates for customers.\n")
    p = run(["run", "--material", mat, "--final", fin, "--state-dir", str(tmp_path / "st"), "--no-words"], tmp_path)
    assert "mode=rewrite" in p.stdout.splitlines()[1]


def test_flagged_words_kept(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "We leverage a robust tool.\n")
    fin = write(tmp_path / "f.md", "We use a robust tool.\n")
    p = run(["run", "--source", src, "--final", fin, "--state-dir", str(tmp_path / "st"), "--no-words"], tmp_path)
    assert any(ln.startswith("Flagged words kept: robust") for ln in p.stdout.splitlines())


def test_default_state_dir_at_git_top(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "docs"
    sub.mkdir()
    src = write(sub / "o.md", "A.\n")
    fin = write(sub / "f.md", "B.\n")
    assert run(["run", "--source", src, "--final", fin, "--no-words"], sub).returncode == 0
    assert (tmp_path / ".readyasu" / "state.json").is_file()
    assert run(["verify", "--final", fin], sub).returncode == 0


def test_stdin_only_final_is_usage_error(tmp_path: Path) -> None:
    p = run(["run", "--stdin", "--no-words"], tmp_path, "<<<readyasu:final>>>\nText.\n")
    assert p.returncode == 2 and "not_run" in p.stdout


def test_verify_tolerates_trailing_newlines(tmp_path: Path) -> None:
    st = str(tmp_path / "st")
    data = "<<<readyasu:original>>>\nThe job may fail.\n<<<readyasu:final>>>\nThe job can fail.\n\n\n"
    assert run(["run", "--stdin", "--state-dir", st, "--no-words"], tmp_path, data).returncode == 0
    assert run(["verify", "--final", "-", "--state-dir", st], tmp_path, "The job can fail.").returncode == 0
    fin = write(tmp_path / "f.md", "The job can fail.\n")
    assert run(["verify", "--final", fin, "--state-dir", st], tmp_path).returncode == 0


def test_new_run_in_other_folder(tmp_path: Path) -> None:
    st = str(tmp_path / "st")
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    for folder in (a, b):
        write(folder / "o.md", "Same original.\n")
        write(folder / "f.md", "Same final.\n")
    run(["run", "--source", "o.md", "--final", "f.md", "--state-dir", st, "--no-words"], a)
    p = run(["run", "--source", "o.md", "--final", "f.md", "--state-dir", st, "--no-words"], b)
    assert "attempt 1" in p.stdout.splitlines()[0]


def test_reference_lines_follow_doc_type(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "We're done and it's great!\n")
    fin = write(tmp_path / "f.md", "We are done and it is great.\n")
    p = run(["run", "--source", src, "--final", fin, "--state-dir", str(tmp_path / "st"), "--no-words",
             "--doc-type", "formal"], tmp_path)
    lines = p.stdout.splitlines()
    assert "Stiffness check: reference 1" in lines
    assert "Energy check: reference 1" in lines


def test_unchanged_rerun_before_revision_keeps_revision(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "A.\n")
    fin = write(tmp_path / "f.md", "B.\n")
    st = str(tmp_path / "st")
    run(["run", "--source", src, "--final", fin, "--state-dir", st, "--no-words"], tmp_path)
    p = run(["run", "--source", src, "--final", fin, "--state-dir", st, "--no-words"], tmp_path)
    assert "Revise at most once" in p.stdout.splitlines()[0]


# ---- set 4 review

def test_new_session_starts_a_new_run(tmp_path: Path) -> None:
    import os
    src = write(tmp_path / "o.md", "We leverage a robust pipeline.\n")
    fin = write(tmp_path / "f.md", "We use a robust pipeline.\n")
    st = str(tmp_path / "st")
    env = {**os.environ, "READYASU_SESSION": "chat-1"}
    args = [sys.executable, str(CHECK), "run", "--source", src, "--final", fin, "--state-dir", st, "--no-words"]
    subprocess.run(args, cwd=tmp_path, env=env, capture_output=True, check=False)
    write(tmp_path / "f.md", "We use a pipeline.\n")
    subprocess.run(args, cwd=tmp_path, env=env, capture_output=True, check=False)
    write(tmp_path / "f.md", "We run a pipeline.\n")
    env["READYASU_SESSION"] = "chat-2"
    p = subprocess.run(args, cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", check=False)
    assert p.stdout.splitlines()[0].startswith("Ran the checks (attempt 1)")


def test_verify_rejects_superseded_attempt(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "We leverage a robust pipeline.\n")
    fin = write(tmp_path / "f.md", "We use a robust pipeline.\n")
    old = write(tmp_path / "old.md", "We use a robust pipeline.\n")
    st = str(tmp_path / "st")
    run(["run", "--source", src, "--final", fin, "--state-dir", st, "--no-words"], tmp_path)
    write(tmp_path / "f.md", "We use a pipeline.\n")
    run(["run", "--source", src, "--final", fin, "--state-dir", st, "--no-words"], tmp_path)
    v = run(["verify", "--final", old, "--state-dir", st], tmp_path)
    assert v.returncode == 1 and "reason=superseded" in v.stdout
    assert run(["verify", "--final", fin, "--state-dir", st], tmp_path).returncode == 0


def test_record_error_has_its_own_first_line(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "Hello there.\n")
    fin = write(tmp_path / "f.md", "Hello.\n")
    blocker = write(tmp_path / "blocker", "")
    p = run(["run", "--source", src, "--final", fin, "--state-dir", blocker, "--no-words"], tmp_path)
    assert p.returncode == 3
    assert "--state-dir" in p.stdout.splitlines()[0] and "--no-record" in p.stdout.splitlines()[0]
    assert "reason=record_error" in p.stdout.splitlines()[1]


def test_compose_run_continues_when_adoption_changes(tmp_path: Path) -> None:
    mat = write(tmp_path / "m.txt", "Backups run nightly at 2:00 and are kept for 30 days.\n")
    fin = write(tmp_path / "f.md", "Backups run every night at 2:00 and are kept for 30 days.\n")
    st = str(tmp_path / "st")
    run(["run", "--material", mat, "--final", fin, "--state-dir", st, "--no-words"], tmp_path)
    write(tmp_path / "f.md", "Hi team,\n\nQuick update on storage: backups run every night at 2:00 and are kept "
          "for 30 days.\n\nThanks,\nSam\n")
    p = run(["run", "--material", mat, "--final", fin, "--state-dir", st, "--no-words"], tmp_path)
    assert "attempt=2" in p.stdout.splitlines()[1]


def test_more_usage_errors(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "Hello there.\n")
    fin = write(tmp_path / "f.md", "Hello.\n")
    empty = write(tmp_path / "m.txt", "<<<readyasu:material notes>>>\n")
    for args, stdin in (
        (["run", "--material", empty, "--final", fin], None),
        (["run", "--source", src, "--final", fin, "--timeout", "inf"], None),
        (["run", "--source", "-", "--material", "-", "--final", fin], "x\n"),
        (["run", "--stdin"], "<<<readyasu:original>>>\n\n<<<readyasu:final>>>\nHello.\n"),
    ):
        p = run([*args, "--state-dir", str(tmp_path / "st"), "--no-words"], tmp_path, stdin)
        assert p.returncode == 2, (args, p.stdout, p.stderr)
        assert "not_run reason=usage_error" in p.stdout


def test_separator_source_may_contain_angle_bracket(tmp_path: Path) -> None:
    stdin = ("<<<readyasu:material output of git diff (retry.py -> retry_v2.py)>>>\nRetry after 0.5 seconds.\n"
             "<<<readyasu:final>>>\nRetries now wait 0.5 seconds.\n")
    p = run(["run", "--stdin", "--state-dir", str(tmp_path / "st"), "--no-words"], tmp_path, stdin)
    assert p.returncode == 0, p.stdout + p.stderr


def test_flagged_word_with_longer_form_in_original_is_not_added(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "We improved the robustness of the retry logic.\n")
    fin = write(tmp_path / "f.md", "The retry logic is more robust.\n")
    p = run(["run", "--source", src, "--final", fin, "--state-dir", str(tmp_path / "st"), "--no-words"], tmp_path)
    assert "Flagged words added by the rewrite" not in p.stdout


# ---- set 5 review

def test_interleaved_sessions_keep_their_own_runs(tmp_path: Path) -> None:
    import os
    src = write(tmp_path / "o.md", "We leverage a robust pipeline.\n")
    r1 = write(tmp_path / "r1.md", "We use a robust pipeline.\n")
    r2 = write(tmp_path / "r2.md", "We use a pipeline.\n")
    st = str(tmp_path / "st")

    def go(session: str, final: str) -> str:
        env = {**os.environ, "READYASU_SESSION": session}
        p = subprocess.run([sys.executable, str(CHECK), "run", "--source", src, "--final", final, "--state-dir", st,
                            "--no-words"], cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8",
                           check=False)
        return p.stdout.splitlines()[0]

    go("a", r1)
    go("b", r1)
    assert "attempt 2" in go("a", r2)


def test_run_id_resumes_with_its_own_revision_count(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "We leverage a robust pipeline.\n")
    st = str(tmp_path / "st")
    for text, args in (("We use a robust pipeline.\n", ["--run-id", "old1"]), ("We use a pipeline.\n", ["--run-id", "old1"]),
                       ("We use a robust pipeline.\n", ["--new-run"])):
        fin = write(tmp_path / "f.md", text)
        run(["run", "--source", src, "--final", fin, "--state-dir", st, "--no-words", *args], tmp_path)
    fin = write(tmp_path / "f.md", "We run a pipeline.\n")
    p = run(["run", "--source", src, "--final", fin, "--state-dir", st, "--no-words", "--run-id", "old1"], tmp_path)
    assert "exceeds the one-revision rule" in p.stdout.splitlines()[0]


def test_invalid_run_id_in_index_is_ignored(tmp_path: Path) -> None:
    import json as _json
    sys.path.insert(0, str(SCRIPTS))
    import readyasu_text as tx
    src = write(tmp_path / "o.md", "Hello there.\n")
    fin = write(tmp_path / "f.md", "Hello.\n")
    idx = tmp_path / "st" / "index" / "by-source"
    idx.mkdir(parents=True)
    (idx / f"{tx.sha256_text('Hello there.' + chr(10))}.json").write_text(
        _json.dumps({"run": "../../escape", "cwd": str(tmp_path), "updated_ts": 9e9}), encoding="utf-8")
    p = run(["run", "--source", src, "--final", fin, "--state-dir", str(tmp_path / "st"), "--no-words"], tmp_path)
    assert p.returncode == 0 and not (tmp_path / "escape").exists()


def test_json_splits_kept_and_added_words(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "We use the tool to check logs.\n")
    fin = write(tmp_path / "f.md", "We leverage the tool to delve into logs.\n")
    p = run(["run", "--source", src, "--final", fin, "--state-dir", str(tmp_path / "st"), "--no-words", "--json"],
            tmp_path)
    data = json.loads(p.stdout)
    assert data["flagged_words_kept"] == [] and set(data["flagged_words_added"]) == {"leverage", "delve"}


def test_first_line_hints_new_run_after_one_revision(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "We leverage a robust pipeline.\n")
    fin = write(tmp_path / "f.md", "We use a robust pipeline.\n")
    st = str(tmp_path / "st")
    run(["run", "--source", src, "--final", fin, "--state-dir", st, "--no-words"], tmp_path)
    write(tmp_path / "f.md", "We use a pipeline.\n")
    p = run(["run", "--source", src, "--final", fin, "--state-dir", st, "--no-words"], tmp_path)
    assert "--new-run" in p.stdout.splitlines()[0]


def test_first_line_names_counted_risks(tmp_path: Path) -> None:
    src = write(tmp_path / "o.md", "The job may fail.\n")
    fin = write(tmp_path / "f.md", "The job fails.\n")
    p = run(["run", "--source", src, "--final", fin, "--state-dir", str(tmp_path / "st"), "--no-words"], tmp_path)
    assert "1 counted meaning risk" in p.stdout.splitlines()[0]


def test_compose_lists_composer_words_as_added(tmp_path: Path) -> None:
    mat = write(tmp_path / "m.txt", "Notes: backups kept 30 days.\n")
    fin = write(tmp_path / "f.md", "We leverage a seamless backup process that keeps backups for 30 days.\n")
    p = run(["run", "--material", mat, "--final", fin, "--state-dir", str(tmp_path / "st"), "--no-words"], tmp_path)
    assert "Flagged words kept" not in p.stdout and "Flagged words added by the rewrite" in p.stdout
