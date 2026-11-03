"""Build ordered steps_json for one deletion audit case according to specification."""

FIND = [
    "REPORT_REMAINING_RECORD",
    "REPORT_EXPOSED_PII",
    "REPORT_ACTIVE_DATA_FLOW",
    "REPORT_RESTORE_RISK",
]
REM = [
    "DISABLE_DATA_FLOW",
    "BLOCK_RESTORE",
    "DELETE_RECORD",
    "REDACT_RECORD",
    "ANONYMIZE_RECORD",
]
VER = [
    "VERIFY_RECORD_ABSENT",
    "VERIFY_RECORD_PRESENT",
    "VERIFY_RECORD_REDACTED",
    "VERIFY_RECORD_ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED",
    "VERIFY_RESTORE_BLOCKED",
]
STATE = {
    "REPORT_REMAINING_RECORD": "PRESENT",
    "REPORT_EXPOSED_PII": "PRESENT",
    "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
    "REPORT_RESTORE_RISK": "ACTIVE",
    "DISABLE_DATA_FLOW": "DISABLED",
    "BLOCK_RESTORE": "BLOCKED",
    "DELETE_RECORD": "ABSENT",
    "REDACT_RECORD": "REDACTED",
    "ANONYMIZE_RECORD": "ANONYMIZED",
    "VERIFY_RECORD_ABSENT": "ABSENT",
    "VERIFY_RECORD_PRESENT": "PRESENT",
    "VERIFY_RECORD_REDACTED": "REDACTED",
    "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
    "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}
VERIFY_FOR = {
    "DELETE_RECORD": "VERIFY_RECORD_ABSENT",
    "REDACT_RECORD": "VERIFY_RECORD_REDACTED",
    "ANONYMIZE_RECORD": "VERIFY_RECORD_ANONYMIZED",
    "DISABLE_DATA_FLOW": "VERIFY_DATA_FLOW_DISABLED",
    "BLOCK_RESTORE": "VERIFY_RESTORE_BLOCKED",
}


def plan(ident, hits, ev_flows, deleted_claims, rules):
    """Build (deletion_status, steps_list) from resolved identity, evidence hits, flows, and rules."""
    F, R, V = [], [], []
    for h in hits:
        s, r, e = h["system_id"], h["resource_id"], h["file_id"]
        t = rules.treatment(s, h.get("table"), r)
        allowed = rules.permitted_fields(s, h.get("table"), r)
        exposed_pii = [f for f in h.get("pii_fields", []) if f.lower() not in allowed]

        if t == "DELETE_RECORD":
            F.append(("REPORT_REMAINING_RECORD", s, r, e))
            R.append(("DELETE_RECORD", s, r, ""))
            V.append(("VERIFY_RECORD_ABSENT", s, r, ""))
        elif t == "RETAIN":
            if exposed_pii:
                F.append(("REPORT_EXPOSED_PII", s, r, e))
                R.append(("REDACT_RECORD", s, r, ""))
                V.append(("VERIFY_RECORD_REDACTED", s, r, ""))
            # Retained records must be verified present; cite evidence `e` when case is COMPLETE
            V.append(("VERIFY_RECORD_PRESENT", s, r, e))
        elif t == "ANONYMIZE_RECORD":
            # Anonymized records must be unlinked from user_id unless user_id is explicitly permitted
            user_linked = bool(h.get("has_user_ref")) and ("user_id" not in allowed)
            if exposed_pii or user_linked:
                F.append(("REPORT_EXPOSED_PII", s, r, e))
                R.append(("ANONYMIZE_RECORD", s, r, ""))
                V.append(("VERIFY_RECORD_ANONYMIZED", s, r, ""))
            else:
                V.append(("VERIFY_RECORD_ANONYMIZED", s, r, e))
        else:  # REDACT_RECORD (e.g. account tombstones: user_id may stay, direct PII must go)
            if exposed_pii:
                F.append(("REPORT_EXPOSED_PII", s, r, e))
                R.append(("REDACT_RECORD", s, r, ""))
                V.append(("VERIFY_RECORD_REDACTED", s, r, ""))
            else:
                V.append(("VERIFY_RECORD_REDACTED", s, r, e))

    for kind, op_f, op_r in (
        ("flow", "REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW"),
        ("restore", "REPORT_RESTORE_RISK", "BLOCK_RESTORE"),
    ):
        for (s, r), (st, aid) in ev_flows[kind].items():
            if st == "ACTIVE":
                F.append((op_f, s, r, aid))
                R.append((op_r, s, r, ""))
                V.append((VERIFY_FOR[op_r], s, r, ""))
            else:
                V.append((VERIFY_FOR[op_r], s, r, aid))

    hit_keys = {(h["system_id"], h["resource_id"]) for h in hits}
    for (s, r), e in deleted_claims.items():
        if (s, r) not in hit_keys:
            claim_type = e.get("claim_type", "ABSENT")
            if claim_type == "ANONYMIZED":
                V.append(("VERIFY_RECORD_ANONYMIZED", s, r, e["id"]))
            elif claim_type == "REDACTED":
                V.append(("VERIFY_RECORD_REDACTED", s, r, e["id"]))
            else:
                V.append(("VERIFY_RECORD_ABSENT", s, r, e["id"]))

    incomplete = bool(F)
    order_key = lambda order: (lambda x: (order.index(x[0]), x[1], x[2]))
    steps, n = [], 0

    def emit(phase, items, order, keep_ev):
        nonlocal n
        # Deduplicate by (op, system_id, resource_id), preferring items with non-empty evidence_id
        dedup = {}
        for op, s, r, ev in items:
            k = (op, s, r)
            if k not in dedup or (not dedup[k] and ev):
                dedup[k] = ev
        sorted_items = sorted(
            [(op, s, r, ev) for (op, s, r), ev in dedup.items()],
            key=order_key(order),
        )
        for op, s, r, ev in sorted_items:
            n += 1
            steps.append(
                dict(
                    step_no=n,
                    phase=phase,
                    system_id=s,
                    resource_id=r,
                    operation=op,
                    state=STATE[op],
                    evidence_id=ev if keep_ev else "",
                )
            )

    if incomplete:
        emit("FINDING", F, FIND, True)
        emit("REMEDIATION", R, REM, False)
        emit("VERIFICATION", V, VER, False)
        return "INCOMPLETE", steps

    emit("VERIFICATION", V, VER, True)
    return "COMPLETE", steps
