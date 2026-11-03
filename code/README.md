# Northstar Ghost-Data Deletion Audit Agent

Deterministic, zero-token audit pipeline that investigates deletion requests across databases, logs, JSON exports, PDFs, and operational activity logs to determine whether each request is `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`, and emits the strictly ordered JSON findings, remediation steps, and verification checks.

## Repository Layout

```text
.
├── README.md
├── problem_statement.md
├── log.txt
├── dataset/
│   └── deletion_requests.csv          # Place remaining dataset/*.csv and dataset/evidence/ here
└── code/
    ├── main.py                        # Primary CLI entry point (`python code/main.py`)
    ├── config/
    │   └── schema.json                # Flexible column-name mapping & policy treatment map
    ├── evaluation/
    │   ├── main.py                    # Evaluation metric & report generator
    │   ├── evaluation_report.md       # Accuracy metrics, custom cases, and bug fixes
    │   └── usage_report.md            # Token & cost analysis report
    ├── src/
    │   ├── main.py                    # CLI implementation
    │   ├── intent.py                  # Multilingual deletion-intent classifier
    │   ├── identity.py                # Current + historical identity & hash resolver
    │   ├── evidence.py                # SQL, SQLite, JSON, log, TXT, PDF, and image scanner
    │   ├── activity.py                # Operational event & sync/restore state reconstructor
    │   ├── rules.py                   # Policy treatment & permitted_identifiers engine
    │   ├── planner.py                 # Phase/operation/system/resource step planner
    │   ├── evaluate.py                # Evaluation metrics script
    │   ├── usage_report.py            # Usage report generator
    │   └── util.py                    # Shared CSV, config, and sorting utilities
    └── tests/
        ├── test_e2e.py                # 4-case end-to-end verification suite
        └── data/                      # Synthetic dataset & evidence files
```

## Quick Start in VS Code

1. **Run the End-to-End Test Suite** (works immediately with built-in test data):
   ```bash
   python code/tests/test_e2e.py
   ```
2. **Run the Audit Pipeline on the Built-In Demo Dataset**:
   ```bash
   python code/main.py --demo
   ```
3. **Run Intent Classification on the 518 Requests in `dataset/deletion_requests.csv`**:
   ```bash
   python code/main.py intent-only --requests dataset/deletion_requests.csv --out output_intent_only.csv
   ```
4. **Run the Full Audit Pipeline** (once all `dataset/*.csv` files and `dataset/evidence/` are in `dataset/`):
   ```bash
   python code/main.py
   ```
5. **Generate the Evaluation & Usage Reports**:
   ```bash
   python code/src/evaluate.py
   python code/src/usage_report.py 518
   ```
