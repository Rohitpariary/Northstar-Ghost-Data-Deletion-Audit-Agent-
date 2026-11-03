"""Scan evidence files (SQL snapshots, SQLite DBs, JSON/JSONL, logs, TXT, PDF, images) for identifier hits."""
import json
import os
import re
import sqlite3
import subprocess
from identity import digits


def _pdf_text_fallback(path):
    """Extract PDF text using pypdf or pdfplumber when pdftotext CLI is unavailable (e.g. Windows VS Code)."""
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        pass
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception:
        return ""


def _text_of(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            res = subprocess.run(
                ["pdftotext", "-layout", path, "-"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout
        except Exception:
            pass
        return _pdf_text_fallback(path)
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"):
        try:
            res = subprocess.run(
                ["tesseract", path, "-"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout
        except Exception:
            return ""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def _is_redacted_placeholder(val_str):
    low = val_str.strip().lower()
    return low in (
        "",
        "null",
        "none",
        "[redacted]",
        "<redacted>",
        "redacted",
        "***",
        "[deleted]",
        "[anonymized]",
        "anonymized",
    )


def _value_matches_tokens(val, tokens, phone_digits):
    if val is None:
        return set()
    s = str(val).strip()
    if _is_redacted_placeholder(s):
        return set()
    low = s.lower()
    hits = {t for t in tokens if t in low}
    if phone_digits:
        d = digits(s)
        if len(d) >= 7:
            for pd in phone_digits:
                if pd in d:
                    hits.add(pd)
    return hits


def _is_sqlite_binary(path):
    try:
        with open(path, "rb") as f:
            return f.read(16).startswith(b"SQLite format 3")
    except Exception:
        return False


def _extract_resource_id(vals, uid_tokens, fallback):
    # 1. Prefer specific entity/resource ID columns (excluding user_id)
    for k, v in vals.items():
        kl = k.lower()
        if v is not None and str(v).strip() and not _is_redacted_placeholder(str(v)):
            if kl in ("resource_id", "record_id", "entity_id", "object_id"):
                return str(v).strip()
    for k, v in vals.items():
        kl = k.lower()
        if v is not None and str(v).strip() and not _is_redacted_placeholder(str(v)):
            if kl.endswith("id") and "user" not in kl and str(v).strip().lower() not in uid_tokens:
                return str(v).strip()
    # 2. Fall back to user_id if that is the primary key of the table
    for k, v in vals.items():
        kl = k.lower()
        if v is not None and str(v).strip() and ("user" in kl or kl == "id"):
            return str(v).strip()
    return str(fallback)


def scan_sql(path, ident, file_id, system_id, default_category=None):
    out = []
    con = None
    try:
        if _is_sqlite_binary(path):
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        else:
            con = sqlite3.connect(":memory:")
            with open(path, encoding="utf-8", errors="ignore") as f:
                con.executescript(f.read())
    except Exception:
        if con:
            con.close()
        return scan_text(path, ident, file_id, system_id, default_category=default_category)

    toks = ident.all_tokens()
    phone_digits = {digits(p) for p in ident.phones if len(digits(p)) >= 7}
    uid_tokens = {u.strip().lower() for u in ident.user_ids if u}

    try:
        tables = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for tbl in tables:
            try:
                cur = con.execute(f'SELECT rowid, * FROM "{tbl}"')
                cols = [d[0] for d in cur.description][1:]
                rows = [(r[0], dict(zip(cols, r[1:]))) for r in cur.fetchall()]
            except sqlite3.OperationalError:
                cur = con.execute(f'SELECT * FROM "{tbl}"')
                cols = [d[0] for d in cur.description]
                rows = [(idx + 1, dict(zip(cols, r))) for idx, r in enumerate(cur.fetchall())]

            for rowid, vals in rows:
                has_uid = any(
                    str(v).strip().lower() in uid_tokens
                    for k, v in vals.items()
                    if v is not None and ("user" in k.lower() or k.lower() in ("id", "customer_id", "account_id", "subject_id"))
                )
                pii_cols = []
                for k, v in vals.items():
                    if v is None:
                        continue
                    kl = k.lower()
                    if kl in ("user_id", "userid"):
                        continue
                    if _value_matches_tokens(v, toks, phone_digits):
                        pii_cols.append(k)
                if not (has_uid or pii_cols):
                    continue
                rid = _extract_resource_id(vals, uid_tokens, rowid)
                out.append(
                    dict(
                        file_id=file_id,
                        system_id=system_id,
                        resource_id=rid,
                        table=tbl or default_category,
                        pii_fields=sorted(set(pii_cols)),
                        has_user_ref=has_uid,
                    )
                )
    finally:
        con.close()
    return out


def _walk_json_records(node, parent_key=None):
    """Yield dict records from parsed JSON structures."""
    if isinstance(node, dict):
        # If dict looks like a container of table/category -> list of records
        scalar_vals = [v for v in node.values() if not isinstance(v, (dict, list))]
        if not scalar_vals and any(isinstance(v, (list, dict)) for v in node.values()):
            for k, v in node.items():
                yield from _walk_json_records(v, parent_key=k)
        else:
            yield (parent_key, node)
            for k, v in node.items():
                if isinstance(v, (list, dict)):
                    yield from _walk_json_records(v, parent_key=k)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_json_records(item, parent_key=parent_key)


def scan_json(path, ident, file_id, system_id, default_resource="", default_category=None):
    txt = _text_of(path).strip()
    if not txt:
        return []
    parsed_records = []
    try:
        if path.lower().endswith(".jsonl"):
            for line in txt.splitlines():
                if line.strip():
                    parsed_records.extend(_walk_json_records(json.loads(line)))
        else:
            parsed_records.extend(_walk_json_records(json.loads(txt)))
    except Exception:
        return scan_text(path, ident, file_id, system_id, default_resource, default_category)

    toks = ident.all_tokens()
    phone_digits = {digits(p) for p in ident.phones if len(digits(p)) >= 7}
    uid_tokens = {u.strip().lower() for u in ident.user_ids if u}
    out = {}

    for tbl, rec in parsed_records:
        if not isinstance(rec, dict):
            continue
        flat_vals = {
            k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
            for k, v in rec.items()
        }
        has_uid = any(
            str(v).strip().lower() in uid_tokens
            for k, v in flat_vals.items()
            if v is not None and ("user" in k.lower() or k.lower() in ("id", "customer_id", "account_id", "subject_id"))
        )
        pii_cols = []
        for k, v in flat_vals.items():
            if v is None or k.lower() in ("user_id", "userid"):
                continue
            if _value_matches_tokens(v, toks, phone_digits):
                pii_cols.append(k)
        if not (has_uid or pii_cols):
            continue
        rec_sys = str(rec.get("system_id") or system_id).strip()
        rid = _extract_resource_id(flat_vals, uid_tokens, default_resource or file_id)
        key = (rec_sys, rid)
        entry = out.setdefault(
            key,
            {
                "file_id": file_id,
                "system_id": rec_sys,
                "resource_id": rid,
                "table": tbl or rec.get("category") or rec.get("data_category") or default_category,
                "pii_fields": set(),
                "has_user_ref": False,
            },
        )
        entry["pii_fields"].update(pii_cols)
        entry["has_user_ref"] = entry["has_user_ref"] or has_uid

    if not out:
        return scan_text(path, ident, file_id, system_id, default_resource, default_category)
    return [dict(v, pii_fields=sorted(v["pii_fields"])) for v in out.values()]


def scan_text(path, ident, file_id, system_id, default_resource="", default_category=None):
    txt = _text_of(path)
    toks = ident.all_tokens()
    phone_digits = {digits(p) for p in ident.phones if len(digits(p)) >= 7}
    uid_tokens = {u.lower() for u in ident.user_ids if u}
    records = {}
    for line in txt.splitlines() or [txt]:
        found = _value_matches_tokens(line, toks, phone_digits)
        line_words = set(re.findall(r"\b[a-z0-9_-]+\b", line.lower()))
        uid_found = bool(uid_tokens & line_words)
        if not found and not uid_found:
            continue
        candidate_ids = [
            m
            for m in re.findall(r"\b[a-z][a-z0-9]*_\d+\b", line, flags=re.I)
            if m.lower() not in uid_tokens and m.lower() != file_id.lower() and m.lower() != system_id.lower()
        ]
        resource_ids = set(candidate_ids) if candidate_ids else {default_resource or file_id}
        for rid in resource_ids:
            record = records.setdefault(
                rid,
                {
                    "file_id": file_id,
                    "system_id": system_id,
                    "resource_id": rid,
                    "table": default_category,
                    "pii_fields": set(),
                    "has_user_ref": False,
                },
            )
            record["pii_fields"].update(found)
            record["has_user_ref"] = record["has_user_ref"] or uid_found
    return [dict(record, pii_fields=sorted(record["pii_fields"])) for record in records.values()]


def scan_all(root, manifest, ident, cfg, audit_at=None, **kwargs):
    from util import pick

    M = cfg["manifest"]
    hits = []
    for m in manifest:
        fid = pick(m, M["file_id"])
        rel = pick(m, M["path"])
        resource_id = pick(m, M["resource_id"])
        category = pick(m, M.get("category", ["data_category", "category"]))
        candidates = [
            os.path.join(root, rel),
            os.path.join(root, "evidence", rel),
            os.path.join(root, "evidence", os.path.basename(rel)),
        ]
        p = next((c for c in candidates if os.path.isfile(c)), None)
        if not p:
            continue
        sysid = pick(m, M["system_id"]) or os.path.splitext(os.path.basename(p))[0]
        low_p = p.lower()
        if low_p.endswith((".sql", ".sqlite", ".db")):
            hits += scan_sql(p, ident, fid, sysid, default_category=category or None)
        elif low_p.endswith((".json", ".jsonl")):
            hits += scan_json(p, ident, fid, sysid, resource_id, default_category=category or None)
        else:
            hits += scan_text(p, ident, fid, sysid, resource_id, default_category=category or None)
    return hits
