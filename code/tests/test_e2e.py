"""End-to-end test suite verifying all 4 canonical scenarios and generating evaluation metrics."""
import csv
import json
import os
import subprocess
import sys

CODE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(CODE_DIR, "tests", "data")
PRED_PATH = os.path.join(DATA_DIR, "predicted_output.csv")
GOLD_PATH = os.path.join(DATA_DIR, "expected_output.csv")


def run_tests():
    subprocess.check_call(
        [
            sys.executable,
            os.path.join(CODE_DIR, "main.py"),
            "run",
            "--data",
            DATA_DIR,
            "--out",
            PRED_PATH,
        ],
        cwd=CODE_DIR,
    )
    with open(PRED_PATH, newline="", encoding="utf-8") as f:
        rows = {r["case_id"]: r for r in csv.DictReader(f)}

    # Case 1: INCOMPLETE (historical email -> u1, tombstone PII, support log, active CRM sync)
    assert rows["case_1"]["deletion_status"] == "INCOMPLETE", rows["case_1"]
    s1 = json.loads(rows["case_1"]["steps_json"])
    assert [x["step_no"] for x in s1] == list(range(1, len(s1) + 1))
    assert [x["phase"] for x in s1] == ["FINDING"] * 3 + ["REMEDIATION"] * 3 + ["VERIFICATION"] * 4
    assert all(x["evidence_id"] for x in s1 if x["phase"] == "FINDING")
    assert all(x["evidence_id"] == "" for x in s1 if x["phase"] != "FINDING")

    # Case 2: NOT_APPLICABLE
    assert rows["case_2"]["deletion_status"] == "NOT_APPLICABLE"
    assert rows["case_2"]["steps_json"] == "[]"

    # Case 3: COMPLETE (all records properly deleted/redacted/retained/anonymized and flows disabled/blocked)
    assert rows["case_3"]["deletion_status"] == "COMPLETE", rows["case_3"]
    s3 = json.loads(rows["case_3"]["steps_json"])
    assert all(x["phase"] == "VERIFICATION" for x in s3)
    assert all(x["evidence_id"] != "" for x in s3), f"Missing evidence_id in COMPLETE case: {s3}"
    ops3 = [x["operation"] for x in s3]
    assert ops3 == [
        "VERIFY_RECORD_ABSENT",
        "VERIFY_RECORD_PRESENT",
        "VERIFY_RECORD_REDACTED",
        "VERIFY_RECORD_ANONYMIZED",
        "VERIFY_DATA_FLOW_DISABLED",
        "VERIFY_RESTORE_BLOCKED",
    ], f"Unexpected operation order in case_3: {ops3}"

    # Case 4: INCOMPLETE (multi-line JSON PII exposure + active restore risk)
    assert rows["case_4"]["deletion_status"] == "INCOMPLETE", rows["case_4"]
    s4 = json.loads(rows["case_4"]["steps_json"])
    assert any(x["operation"] == "REPORT_EXPOSED_PII" and x["resource_id"] == "export_404" for x in s4), s4
    assert any(x["operation"] == "REPORT_RESTORE_RISK" and x["resource_id"] == "restore_pipe_3" for x in s4), s4

    # Save canonical gold output for evaluate.py verification
    with open(PRED_PATH, encoding="utf-8") as src, open(GOLD_PATH, "w", encoding="utf-8", newline="") as dst:
        dst.write(src.read())

    print("All 4 E2E test cases passed:")
    for cid in ("case_1", "case_2", "case_3", "case_4"):
        steps = json.loads(rows[cid]["steps_json"])
        print(f"  {cid}: {rows[cid]['deletion_status']} ({len(steps)} steps)")


if __name__ == "__main__":
    run_tests()
