# Evaluation Report — Northstar Ghost-Data Deletion Audit Agent

## 1. Quantitative Accuracy Metrics
- **Evaluated Dataset**: `output_sample.csv` vs `sample_output.csv` (32 cases)
- **Case-Level Status Accuracy**: 24/32 (0.750)
- **Exact Step-List Match Rate**: 0/32 (0.000)
- **Step-Level Precision / Recall / F1**: Precision = 0.012, Recall = 0.016, F1 = 0.014
- **Sequence Ordering Accuracy** (among cases with matching step sets): 0.000 (0 cases with right steps in wrong order)

### Field-Level Accuracy (Aligned Steps)
- **`phase` accuracy**: 84/167 (0.503)
- **`system_id` accuracy**: 5/167 (0.030)
- **`resource_id` accuracy**: 30/167 (0.180)
- **`operation` accuracy**: 36/167 (0.216)
- **`state` accuracy**: 62/167 (0.371)
- **`evidence_id` accuracy**: 108/167 (0.647)

## 2. Intent Classification Verification on Full Request Set (518 Cases)
- **Total Requests Audited**: 518 (`case_33` through `case_550`)
- **Authorized Deletion Requests**: 508 (including English, Portuguese, Spanish, Korean, Japanese, and French templates)
- **Non-Deletion Requests (`NOT_APPLICABLE`)**: 10 (`case_533` through `case_542` — profile updates, marketing opt-outs, data-portability exports, login resets, and invoice copy requests)

## 3. Additional Custom Evaluation Cases (`code/tests/data/`)
1. **`case_1` — Historical Email Resolution, Tombstone PII Exposure & Active Sync Recreation (`INCOMPLETE`)**:
   - Request submitted under historical email `OLD.JANE@x.com`, mapped via `user_audit_log.csv` (`au1`) to `u1` (`new.jane@x.com`).
   - Detects unredacted PII on account tombstone (`account_005`), remaining support attachment (`ticket_9`), and active CRM sync (`sync_job_7`), while honoring previously deleted search index (`idx_1`).
2. **`case_2` — Non-Deletion Account Retention Request (`NOT_APPLICABLE`)**:
   - User states *"Please keep the account as it is."* Classified as `NOT_APPLICABLE` with `[]`.
3. **`case_3` — Compliant End-to-End Completed Deletion (`COMPLETE`)**:
   - User `u2`'s primary profile was deleted (`a3`), account tombstone (`account_008`) was properly redacted (retaining only `user_id`), billing invoice (`inv_201`) was retained per policy with only permitted `user_id`, analytics record (`evt_88`) was anonymized (`a4`), sync job (`sync_job_8`) was disabled (`a5`), and backup restore (`backup_09`) was blocked (`a6`). Produces `COMPLETE` with all verification steps citing valid `evidence_id` references.
4. **`case_4` — Multi-Line JSON Evidence & Unblocked Backup Restore Risk (`INCOMPLETE`)**:
   - User `u3`'s personal data persists inside a multi-line JSON export (`export_404`) and an active snapshot restore pipeline (`restore_pipe_3`) threatens to re-import deleted records. Produces `INCOMPLETE` with `REPORT_REMAINING_RECORD` and `REPORT_RESTORE_RISK`.

## 4. Failures Found & Improvements Made
1. **Missing `evidence_id` on `VERIFY_RECORD_PRESENT` in `COMPLETE` Cases**:
   - *Failure Found*: `planner.py` previously appended `("VERIFY_RECORD_PRESENT", s, r, "")` with an empty `evidence_id`, violating the rule that `COMPLETE` verification steps must cite a `file_id`, `activity_id`, or `audit_id`.
   - *Improvement*: Passed `h["file_id"]` into `VERIFY_RECORD_PRESENT` so `COMPLETE` cases cite the evidence file while `INCOMPLETE` cases clear it during remediation emission.
2. **Multi-Line JSON & Binary SQLite Evidence Scanning**:
   - *Failure Found*: `scan_text()` scanned `.json` files line-by-line, missing `resource_id` fields when `"resource_id"` and `"email"` appeared on separate lines of pretty-printed JSON. `scan_sql()` also called `executescript()` on binary `.sqlite`/`.db` files and crashed on `WITHOUT ROWID` tables.
   - *Improvement*: Added structured `scan_json()` parser, binary SQLite detection, `WITHOUT ROWID` fallback, and pure-Python `pypdf`/`pdfplumber` fallback for Windows VS Code environments without `pdftotext`.
3. **`ANONYMIZE_RECORD` vs `REDACT_RECORD` & `permitted_identifiers` Policy Enforcement**:
   - *Failure Found*: `rules.py` ignored `permitted_identifiers`, and `planner.py` treated `ANONYMIZE_RECORD` identically to `REDACT_RECORD` even when `user_id` still linked the record to the user. `activity.py` also ignored failed status values on deletion claims.
   - *Improvement*: Enforced `permitted_identifiers` in `rules.py` and `planner.py`, required `ANONYMIZE_RECORD` targets to unlink `user_id`, and filtered out failed operation claims in `activity.py`.
