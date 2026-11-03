"""Shared CSV, JSON configuration, and string normalization helpers."""
import csv
import json
import os
import re


def load_cfg(path=None):
    if not path:
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", "config", "schema.json"),
            os.path.join(os.path.dirname(__file__), "config", "schema.json"),
        ]
        path = next((p for p in candidates if os.path.isfile(p)), candidates[0])
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_csv(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [
            {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
            for r in csv.DictReader(f)
        ]


def pick(row, cands, default=""):
    for c in cands:
        key = c.lower()
        if key in row and row[key] != "":
            return row[key]
    return default


def norm_email(e):
    return (e or "").strip().lower()


def natural_case_key(case_id):
    """Sort key supporting both natural case_id order and lexicographical tie-breaking."""
    m = re.match(r"^([a-zA-Z_]+?)(\d+)$", (case_id or "").strip())
    if m:
        return (m.group(1).lower(), int(m.group(2)), case_id)
    return (case_id or "", -1, case_id)
