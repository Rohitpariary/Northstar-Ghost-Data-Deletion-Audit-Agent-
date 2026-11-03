import argparse
import csv
import json
import os
import sys

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "src"))
if not os.path.isdir(SRC_DIR):
    SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from util import load_cfg, read_csv, natural_case_key
from intent import wants_deletion
from identity import resolve
from evidence import scan_all
from activity import user_events, flows, claimed_deleted
from rules import Rules
from planner import plan

REQUIRED_DATA_FILES = (
    "user_identities.csv",
    "user_audit_log.csv",
    "system_activity.csv",
    "deletion_rules.csv",
    "evidence_files.csv",
)

def _require_columns(rows, path, required):
    if not rows:
        raise ValueError(f"{path} is missing a header or has no data rows")
    groups = [[item] if isinstance(item, str) else item for item in required]
    missing = [" or ".join(group) for group in groups if not any(name.lower() in rows[0] for name in group)]
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")

def audit_case(row, D, cfg):
    if not wants_deletion(row["request_text"]):
        return "NOT_APPLICABLE", []
    ident = resolve(row["email"], D["identities"], D["audit"], cfg)
    ev = user_events(D["activity"], ident, row["audit_at"], cfg)
    hits = scan_all(D["root"], D["manifest"], ident, cfg, audit_at=row.get("audit_at"))
    return plan(ident, hits, flows(ev, cfg), claimed_deleted(ev, cfg), D["rules"])

def load(data):
    missing = [name for name in REQUIRED_DATA_FILES if not os.path.isfile(os.path.join(data, name))]
    if missing:
        raise FileNotFoundError(f"Dataset in '{os.path.abspath(data)}' is missing: {', '.join(missing)}")
    evidence_dir = os.path.join(data, "evidence")
    if not os.path.isdir(evidence_dir):
        raise FileNotFoundError(f"Evidence directory is missing: {evidence_dir}")

    cfg = load_cfg()
    p = lambda f: os.path.join(data, f)
    identities = read_csv(p("user_identities.csv"))
    audit = read_csv(p("user_audit_log.csv"))
    activity = read_csv(p("system_activity.csv"))
    manifest = read_csv(p("evidence_files.csv"))
    rule_rows = read_csv(p("deletion_rules.csv"))
    _require_columns(identities, p("user_identities.csv"), [cfg["identities"]["email"], cfg["identities"]["user_id"]])
    _require_columns(audit, p("user_audit_log.csv"), [cfg["audit_log"]["user_id"], cfg["audit_log"]["field"]])
    _require_columns(activity, p("system_activity.csv"), [cfg["activity"]["ts"], cfg["activity"]["system_id"], cfg["activity"]["operation"]])
    _require_columns(manifest, p("evidence_files.csv"), [cfg["manifest"]["file_id"], cfg["manifest"]["path"]])
    _require_columns(rule_rows, p("deletion_rules.csv"), [cfg["rules"]["treatment"]])
    return cfg, dict(root=data, identities=identities, audit=audit, activity=activity, manifest=manifest, rules=Rules(rule_rows, cfg))

def run(data, requests, out):
    cfg, D = load(data)
    request_rows = read_csv(requests)
    _require_columns(request_rows, requests, ["case_id", "email", "audit_at", "request_text"])
    rows = sorted(request_rows, key=lambda r: natural_case_key(r["case_id"]))
    out_dir = os.path.dirname(os.path.abspath(out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "deletion_status", "steps_json"])
        for r in rows:
            st, steps = audit_case(r, D, cfg)
            w.writerow([r["case_id"], st, json.dumps(steps, separators=(",", ":"))])
    print(f"wrote {len(rows)} rows -> {out}")

def inspect(data):
    if not os.path.isdir(data):
        raise FileNotFoundError(f"Data directory not found: {os.path.abspath(data)}")
    for f in sorted(os.listdir(data)):
        if f.endswith(".csv"):
            rows = read_csv(os.path.join(data, f))
            print(f"{f}: {len(rows)} rows, columns={list(rows[0].keys()) if rows else []}")
    ev_dir = os.path.join(data, "evidence")
    print("evidence files:", len(os.listdir(ev_dir)) if os.path.isdir(ev_dir) else "missing")

def main(argv=None):
    parser = argparse.ArgumentParser(description="Northstar Ghost-Data Deletion Audit Agent")
    parser.add_argument("cmd", nargs="?", default="run", choices=["run", "inspect", "intent-only"])
    parser.add_argument("--data", default="dataset")
    parser.add_argument("--requests")
    parser.add_argument("--out", default="output.csv")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args(argv)

    code_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
    repo_root = os.path.abspath(os.path.join(code_root, ".."))

    if args.demo:
        args.data = os.path.join(code_root, "tests", "data")
        if args.out == "output.csv":
            args.out = "output_demo.csv"

    if not os.path.isdir(args.data):
        for candidate in (os.path.join(repo_root, args.data), os.path.join(code_root, args.data)):
            if candidate and os.path.isdir(candidate):
                args.data = candidate
                break

    requests = args.requests or os.path.join(args.data, "deletion_requests.csv")
    if not os.path.isfile(requests):
        requests = os.path.join(repo_root, "deletion_requests.csv")

    if args.cmd == "inspect":
        inspect(args.data)
    elif args.cmd == "run":
        run(args.data, requests, args.out)
    else:
        rows = read_csv(requests)
        _require_columns(rows, requests, ["case_id", "request_text"])
        rows.sort(key=lambda row: natural_case_key(row["case_id"]))
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["case_id", "deletion_status", "steps_json"])
            for r in rows:
                status = "NOT_APPLICABLE" if not wants_deletion(r["request_text"]) else "UNRESOLVED"
                w.writerow([r["case_id"], status, "[]"])
        print(f"wrote {len(rows)} rows (intent-only) -> {args.out}")

if __name__ == "__main__":
    main()
