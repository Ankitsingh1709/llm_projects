"""Validation harness for Tool 3 (QA scorer) — the project's "trust metric".

The scorer produces numbers, but a number nobody has checked is unfalsifiable.
This harness answers "how far can you trust it?" by scoring calls and comparing
the result against the dataset's documented ground truth (the answer key in
``data/README_DATA.md``). It reports three things:

  1. Overall verdict accuracy — does a bad call score FAIL and a good call PASS?
     (The worst error is a *missed bad call*: a bad call the scorer passed.)
  2. Defect-detection recall — for each bad call, did the LLM actually FAIL the
     *specific* parameter(s) it is supposed to fail (per the answer key)? Catching
     a bad call for the wrong reason is not really catching it.
  3. False-alarm rate — on good calls, how often did the LLM wrongly FAIL a
     parameter that should have passed?

``sla_met`` is DETERMINISTIC (read from the CSV, not LLM-judged), and every bad
call in the dataset is ``sla_met == "No"`` by construction, so it is correct for
free and is reported separately — it is not evidence about the LLM's judgment.

Ground truth below is hand-encoded from ``data/README_DATA.md`` (the answer key),
so it does not depend on fragile free-text parsing of that file.

Run from the repo root (uses the active provider in config.json):
    python -m src.eval.validate_scorer            # balanced sample (default)
    python -m src.eval.validate_scorer --limit 12 # N bad + N good
    python -m src.eval.validate_scorer --all      # all 50 calls (slow)
"""

from __future__ import annotations

import argparse
import time

import pandas as pd

from src.config import REPO_ROOT
from src.tools.qa_scorer import PARAM_NAMES, SLA_PARAM, score_call

# --------------------------------------------------------------------------- #
# Ground truth (from data/README_DATA.md answer key). Values are the LLM-judged
# parameters each bad call is INTENDED to fail — sla_met is excluded on purpose
# (deterministic; every bad call is sla_met=No by construction).
# --------------------------------------------------------------------------- #

EXPECTED_FAILURES: dict[str, set[str]] = {
    "CALL-1006": {"greeting"},
    "CALL-1010": {"identity_verification"},
    "CALL-1013": {"proper_closure"},
    "CALL-1016": {"professional_tone"},
    "CALL-1020": {"greeting", "identity_verification"},
    "CALL-1022": {"professional_tone", "proper_closure"},
    "CALL-1026": {"identity_verification", "policy_compliance"},
    "CALL-1028": {"greeting", "professional_tone"},
    "CALL-1029": {"proper_closure"},
    "CALL-1030": {"identity_verification", "professional_tone", "proper_closure"},
    "CALL-1032": {"greeting"},
    "CALL-1035": {"identity_verification"},
    "CALL-1038": {"proper_closure"},
    "CALL-1041": {"professional_tone"},
    "CALL-1044": {"greeting", "proper_closure"},
    "CALL-1047": {"identity_verification", "policy_compliance"},
    "CALL-1050": {"professional_tone", "proper_closure"},
}
BAD_IDS = set(EXPECTED_FAILURES)

# The 8 LLM-judged parameters (everything except the deterministic sla_met).
LLM_PARAMS = [p for p in PARAM_NAMES if p != SLA_PARAM]

CALLS_CSV = REPO_ROOT / "data" / "calls.csv"
SLEEP_BETWEEN = 1.0  # seconds between calls (cloud rate limits; local needs little)


# --------------------------------------------------------------------------- #
# Parse a scorecard string back into {param: PASS/FAIL} + overall verdict.
# The report is the Markdown table from qa_scorer._format_report, whose rows are
# "| <param> | ✅ PASS | .. |" / "| <param> | ❌ FAIL | .. |" and whose footer
# ends "— PASS" / "— FAIL".
# --------------------------------------------------------------------------- #

def _parse_report(report: str) -> tuple[dict[str, str], str]:
    per_param: dict[str, str] = {}
    for line in report.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] not in PARAM_NAMES:
            continue
        per_param[cells[0]] = "PASS" if "PASS" in cells[1] else "FAIL"
    # Read the verdict from the footer line only — LLM-written justification cells
    # can contain "— PASS"/"— FAIL" and must not decide the overall verdict.
    footer = next((l for l in report.splitlines() if l.startswith("**Weighted score:")), "")
    overall = "PASS" if "— PASS" in footer else "FAIL" if "— FAIL" in footer else "?"
    return per_param, overall


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #

def _select(df: pd.DataFrame, limit: int | None, run_all: bool) -> list[str]:
    ids = list(df["call_id"])
    if run_all:
        return ids
    bad = [i for i in ids if i in BAD_IDS]
    good = [i for i in ids if i not in BAD_IDS]
    n = limit or 8
    return bad[:n] + good[:n]


def validate(limit: int | None = 8, run_all: bool = False) -> dict:
    df = pd.read_csv(CALLS_CSV)
    tcol = next(c for c in df.columns if "transcript" in c.lower())
    df = df.set_index("call_id")

    selected = _select(df.reset_index(), limit, run_all)
    print(
        f"[validate] scoring {len(selected)} call(s) "
        f"({sum(i in BAD_IDS for i in selected)} bad / "
        f"{sum(i not in BAD_IDS for i in selected)} good) — this makes live LLM calls...\n"
    )

    rows = []
    for n, call_id in enumerate(selected, 1):
        transcript = df.loc[call_id, tcol]
        try:
            report = score_call(transcript, call_id=call_id)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{n}/{len(selected)}] {call_id}: ERROR {exc}")
            continue
        per_param, overall = _parse_report(report)
        is_bad = call_id in BAD_IDS
        expected_overall = "FAIL" if is_bad else "PASS"
        rows.append(
            {
                "call_id": call_id,
                "is_bad": is_bad,
                "overall": overall,
                "expected_overall": expected_overall,
                "verdict_ok": overall == expected_overall,
                "per_param": per_param,
            }
        )
        mark = "✓" if overall == expected_overall else "✗"
        print(f"  [{n}/{len(selected)}] {call_id} {'BAD ' if is_bad else 'good'} -> {overall} {mark}")
        if n < len(selected):
            time.sleep(SLEEP_BETWEEN)

    return _report(rows)


def _report(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        print("\n[validate] no calls scored (all errored?)")
        return {}

    bad_rows = [r for r in rows if r["is_bad"]]
    good_rows = [r for r in rows if not r["is_bad"]]

    verdict_ok = sum(r["verdict_ok"] for r in rows)
    missed_bad = [r["call_id"] for r in bad_rows if r["overall"] == "PASS"]     # dangerous
    false_alarm_calls = [r["call_id"] for r in good_rows if r["overall"] == "FAIL"]

    # Defect-detection recall over the LLM params (exclude deterministic sla_met).
    caught = expected = 0
    per_defect_miss = []
    for r in bad_rows:
        for param in EXPECTED_FAILURES[r["call_id"]]:
            expected += 1
            if r["per_param"].get(param) == "FAIL":
                caught += 1
            else:
                per_defect_miss.append(f"{r['call_id']}:{param}")

    # False param-level alarms on good calls (LLM params only).
    good_param_checks = len(good_rows) * len(LLM_PARAMS)
    good_param_false_fails = sum(
        1 for r in good_rows for p in LLM_PARAMS if r["per_param"].get(p) == "FAIL"
    )

    def pct(a, b):
        return f"{100 * a / b:.0f}%" if b else "n/a"

    print("\n" + "=" * 68)
    print("QA SCORER — VALIDATION vs. ground truth (data/README_DATA.md)")
    print("=" * 68)
    print(f"Calls scored: {n}  ({len(bad_rows)} bad / {len(good_rows)} good)\n")

    print(f"1) Overall verdict accuracy : {verdict_ok}/{n}  ({pct(verdict_ok, n)})")
    print(f"     - missed bad calls (scored PASS): {len(missed_bad)}  {missed_bad or ''}")
    print(f"     - false alarms (good scored FAIL): {len(false_alarm_calls)}  {false_alarm_calls or ''}")

    print(f"\n2) Defect-detection recall  : {caught}/{expected}  ({pct(caught, expected)})")
    print("     (of the specific parameters each bad call SHOULD fail, per the answer key)")
    if per_defect_miss:
        print(f"     - missed defects: {per_defect_miss}")

    print(
        f"\n3) False param-alarms on good: {good_param_false_fails}/{good_param_checks} "
        f"({pct(good_param_false_fails, good_param_checks)} of good-call parameter checks)"
    )
    print("=" * 68)

    return {
        "n": n,
        "verdict_accuracy": verdict_ok / n,
        "missed_bad": missed_bad,
        "false_alarm_calls": false_alarm_calls,
        "defect_recall": (caught / expected) if expected else None,
        "missed_defects": per_defect_miss,
        "good_param_false_fail_rate": (good_param_false_fails / good_param_checks)
        if good_param_checks
        else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=8, help="N bad + N good calls (default 8)")
    ap.add_argument("--all", action="store_true", help="score all 50 calls (slow)")
    args = ap.parse_args()
    validate(limit=args.limit, run_all=args.all)


if __name__ == "__main__":
    main()
