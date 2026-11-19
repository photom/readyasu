#!/usr/bin/env python3
"""readyasu check: run lint and diff together on a final draft and keep a record.

`run` runs lint on the final draft and diff on the original and the final draft
(compose mode: the material match) and writes a record. `verify` checks right
before submitting that the final draft is the one that was checked.
The record shows that the checks ran. It does not show that meaning was kept or
that the text passed a readability test. Anyone who can edit both the draft and
the record can change them; the record finds skipped runs, it does not prevent
tampering. Standard library only; Python 3.9+.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import datetime as _dt
import difflib
import json
import math
import os
import re
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import readyasu_text as tx  # noqa: E402

__version__ = tx.__version__
TOOL = "readyasu-check"
STATUS_PREFIX = "readyasu-check:"
SCRIPTS = Path(__file__).resolve().parent
LINT = SCRIPTS / "readyasu_lint.py"
DIFF = SCRIPTS / "readyasu_diff.py"
MARKER = re.compile(r"^<<<readyasu:(original|final|material)(?:[ \t]+([^\n]{1,200}?))?>>>[ \t]*$")
MARKER_ANY = re.compile(r"^<<<readyasu:")
RUN_WINDOW_SECONDS = 2 * 60 * 60  # a run continues only within this time and the same working folder
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
WINDOWS_NAMES = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
KEPT_WORD_RULES = ("project_term", "ai_vocabulary", "metaphor_verb", "jargon")
NOT_A_SCORE = "(lint rule matches; not a score. A rise or fall does not mean better or worse readability.)"

USAGE = """readyasu_check.py run --final FINAL (--source ORIGINAL | --material MATERIAL) [options]
       readyasu_check.py run --stdin [options]
       readyasu_check.py verify --final FINAL|- [options]
       readyasu_check.py --version"""

EPILOG = """Exit codes:
  0  run: all checks finished and no --fail-on condition matched (status executed or unrecorded,
     with or without findings). verify: the record matches (executed).
  1  run: a --fail-on condition matched (the record is still written). verify: no record, or the
     record does not match.
  2  usage or input error (file cannot be read, not UTF-8, bad separators, bad values, the original
     and final are the same file, material identical to the final draft, empty final draft, bad word
     list). Nothing is written (status not_run).
  3  some checks did not finish (lint or diff failed or timed out, or the final draft changed during
     the run; status partial with reason=check_error), the record could not be written (status partial
     with reason=record_error), or an unexpected internal error (status partial with reason=internal_error)."""


class Usage(Exception):
    pass


# ---------------------------------------------------------------- helpers


def now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def new_run_id() -> str:
    return now_utc().strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)


def valid_run_id(value: str) -> bool:
    if not RUN_ID.match(value) or value.endswith("."):
        return False
    return value.split(".")[0].lower() not in WINDOWS_NAMES


def state_dir(arg: Optional[str]) -> Path:
    if arg:
        return Path(arg).resolve()
    env = os.environ.get("READYASU_STATE_DIR", "").strip()
    if env and "${" not in env:
        return Path(env).resolve()
    cwd = Path.cwd().resolve()
    top = tx.git_top(cwd) or cwd
    return top / tx.STATE_DIR_NAME


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def ensure_state(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    ignore = folder / ".gitignore"
    if not ignore.exists():
        ignore.write_text("# Records of readyasu check runs. Not meant to be committed.\n*\n", encoding="utf-8")


def strip_markers(text: str) -> str:
    return "\n".join(ln for ln in text.split("\n") if not MARKER.match(ln))


def parse_stdin(data: str) -> tuple[Optional[str], list[tuple[str, str]], str]:
    """Split standard input into (original, [(source, material)], final)."""
    sections: list[tuple[str, str, list[str]]] = []
    for line in data.split("\n"):
        m = MARKER.match(line)
        if m:
            sections.append((m.group(1), (m.group(2) or "").strip(), []))
            continue
        if MARKER_ANY.match(line):
            raise Usage(f"Unknown separator line: {line.strip()[:80]}. Use <<<readyasu:original>>>, "
                        "<<<readyasu:material SOURCE>>> or <<<readyasu:final>>> exactly.")
        if not sections:
            if line.strip():
                raise Usage("Standard input must start with a <<<readyasu:original>>>, <<<readyasu:material>>> "
                            "or <<<readyasu:final>>> line.")
            continue
        sections[-1][2].append(line)
    original: Optional[str] = None
    materials: list[tuple[str, str]] = []
    final: Optional[str] = None
    for kind, source, lines in sections:
        body = "\n".join(lines).strip("\n") + "\n"
        if kind == "original":
            if original is not None:
                raise Usage("Standard input has more than one <<<readyasu:original>>> section.")
            original = body
        elif kind == "final":
            if final is not None:
                raise Usage("Standard input has more than one <<<readyasu:final>>> section.")
            final = body
        else:
            materials.append((source or "standard input", body))
    if final is None:
        raise Usage("Standard input has no <<<readyasu:final>>> section.")
    return original, materials, final


def run_tool(cmd: list[str], timeout: float) -> tuple[Optional[dict[str, Any]], str]:
    if timeout <= 0:
        return None, "timed out"
    try:
        proc = subprocess.run([sys.executable, *cmd], capture_output=True, timeout=timeout, check=False,
                              env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    except subprocess.TimeoutExpired:
        return None, "timed out"
    except OSError as exc:
        return None, f"could not start ({exc})"
    if proc.returncode not in (0, 1):
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        return None, f"exit {proc.returncode}" + (f": {err[-1]}" if err else "")
    try:
        return json.loads(proc.stdout.decode("utf-8")), ""
    except ValueError:
        return None, "unreadable output"


def kept_words(findings: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for f in findings:
        word = str(f.get("match", ""))
        if f.get("rule") in KEPT_WORD_RULES and word and word.lower() not in (s.lower() for s in seen):
            seen.append(word)
    return seen


# ---------------------------------------------------------------- run


def cmd_run(args: argparse.Namespace) -> int:
    started = time.monotonic()
    try:
        words = tx.load_words(args.words, args.no_words)
        fail_on: set[str] = set()
        for value in args.fail_on or []:
            for part in value.split(","):
                part = part.strip()
                if not part:
                    continue
                if part not in ("meaning-risk", "warn", "error"):
                    raise Usage(f"--fail-on accepts meaning-risk, warn or error (got {part}).")
                fail_on.add(part)
        if args.run_id and not valid_run_id(args.run_id):
            raise Usage("--run-id must start with a letter or digit and use only letters, digits, '.', '_' and '-' "
                        "(up to 64 characters, not ending with '.', not a reserved Windows name).")
        if args.run_id and args.new_run:
            raise Usage("Use either --run-id or --new-run, not both.")
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise Usage("--timeout must be a positive number of seconds.")
        materials: list[tuple[str, str]] = []
        if args.stdin:
            if args.final or args.source:
                raise Usage("With --stdin, pass the texts on standard input, not --final or --source.")
            original, stdin_materials, final = parse_stdin(tx.read_text("-"))
            materials.extend(stdin_materials)
            if original is None and not stdin_materials and not args.material:
                raise Usage("Standard input needs a <<<readyasu:original>>> section (revising) or a "
                            "<<<readyasu:material>>> section (composing) before the final draft.")
            final_label = "-"
            source_label = "-" if original is not None else None
        else:
            if not args.final:
                raise Usage("run needs --final (or --stdin).")
            if not args.source and not args.material:
                raise Usage("run needs --source (revising) or --material (composing).")
            if [args.final, args.source, *(args.material or [])].count("-") > 1:
                raise Usage("Only one input can be standard input.")
            final = tx.read_text(args.final)
            original = tx.read_text(args.source) if args.source else None
            final_label = args.final
            source_label = args.source
            if args.source and args.final != "-" and args.source != "-" and \
                    Path(args.source).resolve() == Path(args.final).resolve():
                raise Usage("The original and the final draft are the same file. Save the final draft separately.")
        if args.stdin and "-" in (args.material or []):
            raise Usage("With --stdin, put the material in a <<<readyasu:material>>> section, not --material -.")
        for name in args.material or []:
            materials.append((name, tx.read_text(name)))
        if not final.strip():
            raise Usage("The final draft is empty.")
        if original is not None and not original.strip():
            raise Usage("The original is empty.")
        for source, body in materials:
            if not strip_markers(body).strip():
                raise Usage(f"The material {source} is empty.")
        for source, body in materials:
            if strip_markers(body).strip() == final.strip():
                raise Usage(f"The material {source} has the same content as the final draft.")
    except (tx.InputError, Usage) as exc:
        sys.stderr.write(f"readyasu_check.py: {exc}\n")
        sys.stdout.write(f"{STATUS_PREFIX} not_run reason=usage_error\n")
        return 2

    material_text = "\n".join(strip_markers(body) for _src, body in materials)
    given_original = original is not None
    mode = "rewrite" if given_original else "compose"
    adopted = ""
    if original is None:
        final_words = final.split()
        best, best_ratio = None, 0.0
        for source, body in materials:
            ratio = difflib.SequenceMatcher(None, strip_markers(body).split(), final_words).quick_ratio()
            if ratio > best_ratio:
                best, best_ratio = (source, strip_markers(body)), ratio
        if best is not None and best_ratio >= 0.75 and \
                difflib.SequenceMatcher(None, best[1].split(), final_words).ratio() >= 0.6:
            original = best[1]
            mode = "rewrite"
            adopted = best[0]
    started = time.monotonic()  # the timeout covers the child processes only

    final_hash = tx.sha256_text(final)
    source_hash = tx.sha256_text(original) if original is not None else ""
    material_hashes = sorted(tx.sha256_text(body) for _s, body in materials)

    with tempfile.TemporaryDirectory(prefix="readyasu-") as tmp:
        tmpdir = Path(tmp)
        final_path = tmpdir / "final.md"
        final_path.write_text(final, encoding="utf-8")
        common: list[str] = []
        if args.doc_type:
            common += ["--doc-type", args.doc_type]
        if args.reader:
            common += ["--reader", args.reader]
        if words.folder:
            common += ["--words", str(words.folder)]
        else:
            common += ["--no-words"]
        deadline = started + args.timeout
        problems: list[str] = []
        lint_final, err = run_tool([str(LINT), "--json", *common, str(final_path)], deadline - time.monotonic())
        if lint_final is None:
            problems.append(f"lint ({err})")
        lint_orig: Optional[dict[str, Any]] = None
        if original is not None:
            orig_path = tmpdir / "original.md"
            orig_path.write_text(original, encoding="utf-8")
            lint_orig, err = run_tool([str(LINT), "--json", *common, str(orig_path)], deadline - time.monotonic())
            if lint_orig is None:
                problems.append(f"lint of the original ({err})")
        diff_cmd = [str(DIFF), "--json", *common]
        if args.stance:
            diff_cmd += ["--stance", args.stance]
        if args.fact_gaps:
            diff_cmd += ["--fact-gaps"]
        if material_text.strip():
            mat_path = tmpdir / "material.txt"
            mat_path.write_text(material_text, encoding="utf-8")
            diff_cmd += ["--material", str(mat_path)]
        if original is not None:
            diff_cmd += [str(tmpdir / "original.md"), str(final_path)]
        else:
            diff_cmd += ["--compose", str(final_path)]
        diff, err = run_tool(diff_cmd, deadline - time.monotonic())
        if diff is None:
            problems.append(f"diff ({err})")

    if final_label != "-":
        try:
            if tx.sha256_text(tx.read_text(final_label)) != final_hash:
                problems.append("the final draft changed during the run")
        except tx.InputError:
            problems.append("the final draft could not be read again")

    checks = []
    if lint_final is not None:
        checks.append("lint")
    if diff is not None and mode == "rewrite":
        checks.append("diff")
    if diff is not None and material_text.strip():
        checks.append("material")
    meaning_risk = int(diff.get("meaning_risk_count", 0)) if diff else 0
    final_count = int(lint_final.get("review_findings", 0)) if lint_final else 0
    orig_count = int(lint_orig.get("review_findings", 0)) if lint_orig else None
    lint_counts = lint_final.get("counts", {}) if lint_final else {}

    status = "partial" if problems else ("unrecorded" if args.no_record else "executed")
    record_error = ""
    other_run: Optional[tuple[str, str]] = None
    run_id = ""
    attempt = 0
    revisions = 0
    same_as_previous = False
    record_path: Optional[Path] = None
    folder = state_dir(args.state_dir)
    if not problems and not args.no_record:
        try:
            ensure_state(folder)
            # The run key comes from the inputs as given, so adopting a material as the original in one attempt
            # and not in the next does not start a new run.
            key = source_hash if given_original else tx.sha256_text("\n".join(material_hashes))
            session = args.session or os.environ.get("READYASU_SESSION") or None
            if session:
                # each session keeps its own run on the same original, so interleaved sessions do not reset counts
                key += "-" + tx.sha256_text(session)[:12]
            cwd = str(Path.cwd().resolve())
            # one index entry per original (and session) and working folder, so each folder keeps its own run
            index_dir = folder / "index" / "by-source"
            by_source = index_dir / f"{key}~{tx.sha256_text(cwd)[:12]}.json"
            previous = read_json(by_source) or {}
            if not valid_run_id(str(previous.get("run", ""))):
                previous = {}
            try:
                age = now_utc().timestamp() - float(previous.get("updated_ts", 0))
            except (TypeError, ValueError):
                age = RUN_WINDOW_SECONDS + 1
            if args.run_id:
                run_id = args.run_id
            elif args.new_run or not previous.get("run") or age > RUN_WINDOW_SECONDS:
                run_id = new_run_id()
                if not args.new_run and index_dir.is_dir():
                    for other in sorted(index_dir.glob(f"{key}~*.json")):
                        data = read_json(other) or {}
                        try:
                            fresh = now_utc().timestamp() - float(data.get("updated_ts", 0)) <= RUN_WINDOW_SECONDS
                        except (TypeError, ValueError):
                            fresh = False
                        if other != by_source and fresh and valid_run_id(str(data.get("run", ""))):
                            other_run = (str(data["run"]), str(data.get("cwd")))
                            break
            else:
                run_id = str(previous["run"])
            run_dir = folder / "runs" / run_id
            existing = [int(m.group(1)) for p in run_dir.glob("attempt-*.json")
                        if (m := re.match(r"attempt-(\d+)\.json$", p.name))] if run_dir.is_dir() else []
            attempt = (max(existing) + 1) if existing else 1
            # the latest record of this run (not the index) says how many revisions it already had
            last = read_json(run_dir / f"attempt-{max(existing)}.json") or {} if existing else {}
            last_final = last.get("final_sha256") or (previous.get("last_final") if previous.get("run") == run_id else None)
            same_as_previous = attempt > 1 and last_final == final_hash
            fallback = previous.get("revisions", 0) if previous.get("run") == run_id else 0
            try:
                revisions = int((last.get("revisions") if last else fallback) or 0)
            except (TypeError, ValueError):
                revisions = 0
            if attempt > 1 and not same_as_previous:
                revisions += 1
            record_path = run_dir / f"attempt-{attempt}.json"
            record = {
                "format": 1, "tool": TOOL, "version": __version__, "status": "executed",
                "run": run_id, "attempt": attempt, "revisions": revisions, "same_as_previous": same_as_previous,
                "created": now_utc().isoformat(timespec="seconds"),
                "mode": mode, "checks": checks, "final_sha256": final_hash, "source_sha256": source_hash or None,
                "material_sha256": material_hashes, "adopted_material_as_original": adopted or None,
                "final_path": None if final_label == "-" else str(Path(final_label).resolve()),
                "source_path": None if not source_label or source_label == "-" else str(Path(source_label).resolve()),
                "via": "stdin" if args.stdin else "files",
                "doc_type": args.doc_type, "reader": args.reader, "stance": args.stance,
                "meaning_risk": meaning_risk, "lint_counts": lint_counts,
                "review_findings": {"original": orig_count, "final": final_count},
                "changed_places": len(diff.get("changes", [])) if diff else 0,
                "words": {"folder": str(words.folder) if words.folder else None, "count": words.count,
                          "sha256": words.digest or None},
                "session": session,
            }
            write_json(record_path, record)
            if diff is not None:
                record_path.with_suffix(".diff.txt").write_text(str(diff.get("full_diff", "")) + "\n", encoding="utf-8")
            write_json(by_source, {"run": run_id, "attempts": attempt, "revisions": revisions, "last_final": final_hash,
                                   "cwd": cwd, "session": session, "updated_ts": now_utc().timestamp()})
            write_json(folder / "index" / "by-final" / f"{final_hash}.json",
                       {"run": run_id, "attempt": attempt, "record": str(record_path.relative_to(folder))})
            write_json(folder / "state.json", {"last_run": run_id, "last_attempt": attempt,
                                               "updated": now_utc().isoformat(timespec="seconds")})
        except OSError as exc:
            sys.stderr.write(f"readyasu_check.py: cannot write the record in {folder}: {exc}\n")
            record_error = str(exc.strerror or exc)
            status = "partial"
            record_path = None

    status_line = (f"{STATUS_PREFIX} {status} via=run" + (f" run={run_id} attempt={attempt}" if run_id else "")
                   + f" final=sha256:{final_hash[:12]} mode={mode} checks={','.join(checks)} meaning_risk={meaning_risk}")
    if problems:
        status_line += " reason=check_error"
    elif record_error:
        status_line += " reason=record_error"

    hit = False
    if diff and "meaning-risk" in fail_on and meaning_risk:
        hit = True
    if lint_counts and (("error" in fail_on and lint_counts.get("error")) or
                        ("warn" in fail_on and (lint_counts.get("warn") or lint_counts.get("error")))):
        hit = True

    if record_error:
        first = (f"The checks ran, but the record could not be written in {folder} ({record_error}). Run the same "
                 "command again with --state-dir set to a folder you can write to, or with --no-record if there is no "
                 "such folder; then follow the first line of that output.")
    else:
        args.mode = mode
        first = first_line(status, attempt, revisions, same_as_previous, args, problems, folder, meaning_risk)
        sourced = sum(1 for r in (diff or {}).get("meaning_risks", [])
                      if r.get("counted") and "elsewhere in the original or material" in str(r.get("message", "")))
        if sourced and meaning_risk:
            label = tx.plural(meaning_risk, "counted meaning risk")
            verb = "involves" if sourced == 1 else "involve"
            first = first.replace(label, f"{label} (of which {sourced} {verb} numbers found elsewhere in the original or "
                                  "material; check each against that line)", 1)
        if other_run:
            first += (f" (A run of the same original from another folder exists: {other_run[0]} in {other_run[1]}. If this "
                      f"is a revision of it, run the same command again with --run-id {other_run[0]}.)")
    kept_added = split_kept_added(lint_final, lint_orig, original, material_text)
    if args.json:
        out = {"format": 1, "tool": TOOL, "version": __version__, "status": status, "first_line": first,
               "status_line": status_line, "run": run_id or None, "attempt": attempt or None,
               "record": str(record_path) if record_path else None, "mode": mode, "checks": checks,
               "problems": problems + ([f"record ({record_error})"] if record_error else []),
               "meaning_risk": meaning_risk,
               "review_findings": {"original": orig_count, "final": final_count},
               "flagged_words_kept": kept_added[0], "flagged_words_added": kept_added[1],
               "lint": lint_final, "diff": diff}
        sys.stdout.write(json.dumps(out, ensure_ascii=True, indent=1) + "\n")
    else:
        sys.stdout.write(format_run(first, status_line, mode, checks, record_path, lint_final, lint_orig, diff,
                                    orig_count, final_count, adopted, problems, original, material_text))
    if problems or record_error:
        return 3
    return 1 if hit else 0


def first_line(status: str, attempt: int, revisions: int, same_as_previous: bool, args: argparse.Namespace,
               problems: list[str], folder: Path, meaning_risk: int = 0) -> str:
    if problems == ["the final draft changed during the run"]:
        return ("The final draft changed while the checks ran. Run the same command again without changing the file, "
                "then follow the first line of that output.")
    if problems:
        return ("Some checks did not finish: " + "; ".join(problems) + ". Report them under \"Checks not run\" "
                "with the reason check_error.")
    sd = f' --state-dir "{folder}"' if args.state_dir else ""
    verify = (f"pass the same final draft on standard input to verify --final -{sd}" if args.stdin or args.final == "-"
              else f'run verify --final "{args.final}"{sd}')
    if status == "unrecorded":
        return ("Ran the checks (not recorded, as requested). verify cannot match an unrecorded run; report the final "
                "match as a check that was not run (no record was kept).")
    if attempt == 1 or revisions == 0:
        base = "the material" if getattr(args, "mode", "rewrite") == "compose" else "the original"
        risks = (f" {tx.plural(meaning_risk, 'counted meaning risk')}: compare each with {base} and restore "
                 "unintended changes in your revision." if meaning_risk else "")
        return (f"Ran the checks (attempt {attempt}).{risks} Check the findings below against the original and material. Revise at "
                "most once: if you revise, run the same command again; if not, right before submitting and without "
                f"changing the body, {verify} once.")
    if same_as_previous:
        return (f"Ran the checks again on an unchanged final draft (attempt {attempt}, revisions so far: {revisions}). "
                f"Do not change the body. Right before submitting, {verify} once.")
    if revisions <= 1:
        return (f"Ran the checks (attempt {attempt}). That was your one revision: do not change the body again. Right "
                f"before submitting, {verify} once. (If this was the first run for a new request about this text, run it "
                "again with --new-run instead.)")
    return (f"Ran the checks (attempt {attempt}, revision {revisions}). This exceeds the one-revision rule. Proceed only if this revision "
            "only reverted fills without a source (references/fact-recovery.md section 2, step 7), and say so in the "
            f"report. Right before submitting, {verify} once. (If this was the first run for a new request about this "
            "text, run it again with --new-run instead.)")


def split_kept_added(lint_final: Optional[dict[str, Any]], lint_orig: Optional[dict[str, Any]],
                     original_text: Optional[str], material_text: str = "") -> tuple[list[str], list[str]]:
    """Flagged words in the final draft: (kept from the original, added by the rewrite). In compose mode the
    material stands in for the original: words not in it were added by the composer."""
    if lint_final is None:
        return [], []
    final_words = kept_words(list(lint_final.get("findings", [])))
    if lint_orig is None:
        if not material_text.strip():
            return final_words, []
        mat_low = material_text.lower()
        in_mat = [w for w in final_words if re.search(r"(?<![\w-])" + re.escape(w.lower()), mat_low)]
        return in_mat, [w for w in final_words if w not in in_mat]
    orig_words = {w.lower() for w in kept_words(list(lint_orig.get("findings", [])))}
    orig_low = original_text.lower() if original_text else ""
    in_orig = [w for w in final_words if w.lower() in orig_words or
               (orig_low and re.search(r"(?<![\w-])" + re.escape(w.lower()), orig_low))]
    return in_orig, [w for w in final_words if w not in in_orig]


def format_run(first: str, status_line: str, mode: str, checks: list[str], record: Optional[Path],
               lint_final: Optional[dict[str, Any]], lint_orig: Optional[dict[str, Any]],
               diff: Optional[dict[str, Any]], orig_count: Optional[int], final_count: int, adopted: str,
               problems: list[str], original_text: Optional[str] = None, material_text: str = "") -> str:
    out = [first, status_line]
    parts = []
    if lint_final is not None:
        parts.append(f"lint (final draft) {tx.plural(final_count, 'finding')}")
    if diff is not None and mode == "rewrite":
        parts.append(f"diff (original → final) {tx.plural(len(diff.get('changes', [])), 'changed place')}, "
                     f"{tx.plural(int(diff.get('meaning_risk_count', 0)), 'meaning risk')} counted")
    if "material" in checks and diff is not None:
        mat = diff.get("material", {}) or {}
        parts.append(f"material match {tx.plural(len(mat.get('numbers_not_in_material', [])), 'number')} and "
                     f"{tx.plural(len(mat.get('names_not_in_material', [])), 'name')} not in the material")
    out.append("Checks run: " + ("; ".join(parts) if parts else "none"))
    if adopted:
        out.append(f"Compose mode found that the material {adopted} is close to the final draft, so it was used as "
                   "the original for diff.")
    out.append("The record shows only that the checks ran, not that meaning was kept or that the text reads well.")
    if record is not None:
        out.append(f"Record: {record}")
    if diff is not None and mode == "rewrite":
        out.append(f"Stiffness check: {diff.get('stiffness', {}).get('line', 'none')}")
        out.append(f"Energy check: {diff.get('energy', {}).get('line', 'none')}")
    if orig_count is not None:
        out.append(f"Review findings: original {orig_count} → final {final_count} {NOT_A_SCORE}")
    else:
        out.append(f"Review findings: final {final_count} {NOT_A_SCORE}")
    if lint_final is not None:
        kept, added = split_kept_added(lint_final, lint_orig, original_text, material_text)
        if kept:
            project = {str(f.get("match", "")).lower() for f in lint_final.get("findings", []) if f.get("rule") == "project_term"}
            proj_kept = [w for w in kept if w.lower() in project]
            note = (f"; project words ({', '.join(proj_kept)}): use the term after \"→\" in the lint finding, or ask"
                    if proj_kept else "")
            out.append("Flagged words kept: " + ", ".join(kept)
                       + " (reread these sentences; ask the writer or give the reason under \"AI-like wording kept\"" + note + ")")
        if added:
            fix = "restore the original wording" if original_text else "use the plain word"
            out.append("Flagged words added by the rewrite: " + ", ".join(added) + f" (do not add them; {fix})")
    out.append("When you add the report sections after the body, write their headings exactly as in SKILL.md section 3.")
    out.append("Read the sections below in full; do not cut the output.")
    out.append("")
    if diff is not None:
        import readyasu_diff as dmod
        out.extend(dmod_sections(dmod, diff))
        out.append("")
    if lint_final is not None:
        findings = lint_final.get("findings", [])
        out.append(f"== Lint findings on the final draft ({len(findings)}) ==")
        if lint_final.get("doc_type"):
            out.append(f"Doc type {lint_final['doc_type']}: {lint_final.get('exempted', 0)} findings exempted")
        if not findings:
            out.append("- None. Places without findings still need to be read against the original.")
        for f in findings:
            col = int(f.get("col", 1) or 1)
            out.append(f"L{f['line']}:{col} [{str(f['severity']).upper()}] {f['rule']}: {f['message']}")
            out.append(f"  > {tx.excerpt(str(f['text']), col, len(str(f.get('match', '')) or ' '))}")
        out.append("")
    if problems:
        out.append("Not finished: " + "; ".join(problems))
        out.append("")
    out.append(first)
    out.append(status_line)
    return "\n".join(out) + "\n"


def dmod_sections(dmod: ModuleType, diff: dict[str, Any]) -> list[str]:
    """Rebuild the diff text sections from its JSON."""
    risks = [dmod.Risk(**r) for r in diff.get("meaning_risks", [])]
    reviews = [dmod.Review(**v) for v in diff.get("review", [])]
    gaps = [dmod.Review(**g) for g in diff.get("fact_gaps", [])]
    st = diff.get("stiffness", {})
    en = diff.get("energy", {})
    result = dmod.DiffResult(diff.get("changes", []), risks, reviews, st.get("items", []), st.get("reference_only", False),
                             en.get("items", []), en.get("reference", []), gaps, diff.get("fact_gaps_note", ""),
                             diff.get("material", {}) or {}, diff.get("full_diff", ""), diff.get("doc_type"),
                             diff.get("reader"), diff.get("stance"), diff.get("mode", "rewrite"),
                             fact_gaps_checked=bool(diff.get("fact_gaps_checked")))
    lines: list[str] = dmod.format_sections(result)
    return lines


# ---------------------------------------------------------------- verify


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        if not args.final:
            raise Usage("verify needs --final FILE (or --final - for standard input).")
        final = tx.read_text(args.final)
    except (tx.InputError, Usage) as exc:
        sys.stderr.write(f"readyasu_check.py: {exc}\n")
        sys.stdout.write(f"{STATUS_PREFIX} not_run reason=usage_error\n")
        return 2
    digest = tx.sha256_text(final)
    folder = state_dir(args.state_dir)
    pointer = read_json(folder / "index" / "by-final" / f"{digest}.json")
    record: Optional[dict[str, Any]] = None
    record_path: Optional[Path] = None
    reason = "no_record"
    if pointer and isinstance(pointer.get("record"), str):
        record_path = (folder / pointer["record"]).resolve()
        try:
            record_path.relative_to(folder.resolve())
        except ValueError:
            record_path = None
        if record_path is not None:
            record = read_json(record_path)
            reason = "record_unreadable" if record is None else reason
    ok = bool(record and record.get("final_sha256") == digest and record.get("status") == "executed")
    if record and not ok:
        reason = "hash_mismatch"
    latest = 0
    if ok and record is not None and record_path is not None:
        latest = max((int(m.group(1)) for q in record_path.parent.glob("attempt-*.json")
                      if (m := re.match(r"attempt-(\d+)\.json$", q.name))), default=0)
        try:
            matched_attempt = int(record.get("attempt", 0))
        except (TypeError, ValueError):
            matched_attempt = 0
        if latest > matched_attempt:
            later = read_json(record_path.parent / f"attempt-{latest}.json") or {}
            if later.get("final_sha256") != digest:
                ok = False
                reason = "superseded"
    if args.json:
        sys.stdout.write(json.dumps({"format": 1, "tool": TOOL, "status": "executed" if ok else "unverified",
                                     "final_sha256": digest, "record": str(record_path) if record_path else None,
                                     "problems": [] if ok else [reason]}, indent=1) + "\n")
        return 0 if ok else 1
    if ok and record is not None:
        line2 = (f"{STATUS_PREFIX} executed via=verify run={record.get('run')} attempt={record.get('attempt')} "
                 f"final=sha256:{digest[:12]} mode={record.get('mode')} checks={','.join(record.get('checks', []))} "
                 f"meaning_risk={record.get('meaning_risk')}")
        rf = record.get("review_findings", {}) or {}
        sys.stdout.write(
            "The hash matches the record: the required checks ("
            + ", ".join(record.get("checks", [])) + ") were run on this final draft. This is not a pass/fail judgment. "
            "When you add a check record, copy the second line of this output.\n"
            + line2 + "\n"
            + f"Record: {record_path}\n"
            + f"Recorded: review findings final {rf.get('final')}, changed places {record.get('changed_places')} "
              "(the original's count and the changes are in the run output).\n")
        return 0
    if reason == "superseded" and record is not None:
        sys.stdout.write(
            f"This text matches attempt {record.get('attempt')} of run {record.get('run')}, but attempt {latest} is "
            "the latest. Submit the final draft of the latest attempt, or run the checks on this text and verify "
            "again.\n"
            + f"{STATUS_PREFIX} unverified via=verify final=sha256:{digest[:12]} reason=superseded\n"
            + f"State folder: {folder}\n")
        return 1
    sys.stdout.write(
        "No record matches the hash of this final draft. Run the run command on exactly this text, then verify "
        "again without changing it.\n"
        + f"{STATUS_PREFIX} unverified via=verify final=sha256:{digest[:12]} reason={reason}\n"
        + f"State folder: {folder}\n")
    return 1


# ---------------------------------------------------------------- CLI


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        sys.stdout.write(f"{STATUS_PREFIX} not_run reason=usage_error\n")
        sys.exit(2)


def build_parser() -> argparse.ArgumentParser:
    desc = ("Run lint on the final draft and diff on the original and the final draft (compose mode: the material "
            "match) together, and keep a record. The result means 'the checks ran', not that meaning was kept or that "
            "the text passed a readability test.")
    p = _Parser(prog="readyasu_check.py", usage=USAGE, description=desc, epilog=EPILOG,
                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", metavar="{run,verify}", parser_class=_Parser)
    run = sub.add_parser("run", prog="readyasu_check.py run", help="run the checks and write a record; once for the final draft, again after a "
                         "revision", description=desc, epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    run.add_argument("--final", metavar="FINAL", help="final draft (UTF-8); - for standard input")
    run.add_argument("--source", "--original", dest="source", metavar="ORIGINAL",
                     help="the original before rewriting; must be a different file from the final draft")
    run.add_argument("--material", "--materials", action="append", metavar="MATERIAL",
                     help="material file; repeatable. Separator lines <<<readyasu:material SOURCE>>> are allowed")
    run.add_argument("--stdin", action="store_true",
                     help="read the original (or material) and the final draft from standard input, separated by "
                          "lines <<<readyasu:original>>>, <<<readyasu:material SOURCE>>>, <<<readyasu:final>>>")
    run.add_argument("--stance", choices=tx.STANCES, help="stance: recommend, rule or explain")
    run.add_argument("--doc-type", choices=tx.DOC_TYPES, metavar="TYPE", help="document type: " + ", ".join(tx.DOC_TYPES))
    run.add_argument("--reader", choices=tx.READERS, metavar="READER", help="expected reader (recorded only)")
    run.add_argument("--fail-on", action="append", metavar="meaning-risk|warn|error",
                     help="exit 1 (after writing the record) if the condition matches; repeatable or comma-separated")
    run.add_argument("--timeout", type=float, default=90.0, metavar="SECONDS",
                     help="total seconds for the lint and diff child processes (default 90)")
    run.add_argument("--run-id", metavar="ID", help="run ID to continue (letters, digits, '.', '_', '-'; up to 64)")
    run.add_argument("--new-run", action="store_true", help="start a new run ID instead of continuing")
    run.add_argument("--session", metavar="ID", help="session ID stored in the record (default: READYASU_SESSION)")
    run.add_argument("--state-dir", metavar="DIR", help=f"state folder (default: READYASU_STATE_DIR, else "
                     f"{tx.STATE_DIR_NAME}/ at the git top or working folder)")
    run.add_argument("--no-record", action="store_true", help="do not write a record (only when the user asked, or when no writable folder exists)")
    run.add_argument("--fact-gaps", action="store_true", help="list some fact-gap candidates (not counted; not for "
                     "essay or promo)")
    run.add_argument("--json", action="store_true", help="print the result as JSON")
    run.add_argument("--words", metavar="DIR", help=f"project word-list folder (default: {tx.WORDS_DIR_NAME}/)")
    run.add_argument("--no-words", action="store_true", help="do not look for or read a project word list")
    ver = sub.add_parser("verify", prog="readyasu_check.py verify", help="right before submitting, match the final draft's hash with the record "
                         "(reads only)", epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ver.add_argument("--final", metavar="FINAL", help="final draft to submit; - for standard input")
    ver.add_argument("--state-dir", metavar="DIR", help="state folder (same default as run)")
    ver.add_argument("--json", action="store_true", help="print the result as JSON")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    tx.configure_stdout()
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("run", "verify", "-h", "--help", "--version"):
        argv.insert(0, "run")
    args = build_parser().parse_args(argv)
    if args.command is None:
        build_parser().print_help()
        return 0
    try:
        if args.command == "verify":
            return cmd_verify(args)
        return cmd_run(args)
    except BrokenPipeError:
        return 3
    except Exception as exc:  # noqa: BLE001 - report any unexpected error with a status line and exit 3
        sys.stderr.write(f"readyasu_check.py: internal error: {type(exc).__name__}: {exc}\n")
        sys.stdout.write(f"{STATUS_PREFIX} partial via={args.command} reason=internal_error\n")
        return 3


if __name__ == "__main__":
    sys.exit(main())
