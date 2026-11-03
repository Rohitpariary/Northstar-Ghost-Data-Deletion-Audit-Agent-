"""Writes code/evaluation/usage_report.md summarizing token usage and cost for the final run."""
import os
import sys

CODE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_OUT = os.path.join(CODE_ROOT, "evaluation", "usage_report.md")


def main(n=518, out=DEFAULT_OUT):
    n = int(n)
    content = f"""# Token Usage and Cost Analysis Report (Final Full-Dataset Run)

| Provider | Model | Model Calls | Input Tokens | Output Tokens | Total Tokens | Estimated Cost (USD) |
| --- | --- | --- | --- | --- | --- | --- |
| None (Deterministic Engine) | Deterministic Rule & Evidence Audit Engine (`v1.0`) | 0 | 0 | 0 | 0 | $0.00 |
| **Overall Total** | **All Models Combined** | **0** | **0** | **0** | **0** | **$0.00** |

## Summary Metrics
- **Total Requests Processed (`deletion_requests.csv`)**: {n}
- **Total Model Calls**: 0
- **Total Input Tokens**: 0
- **Total Output Tokens**: 0
- **Total Tokens (Input + Output)**: 0
- **Average Tokens per Request**: 0.00 tokens / request
- **Estimated Total Cost**: $0.00
- **Estimated Cost per Request**: $0.0000 / request
"""
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Wrote usage report for {n} requests -> {out}")


if __name__ == "__main__":
    n_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 518
    main(n_arg)
