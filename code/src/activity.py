"""Reconstruct operational and data-flow state at audit_at from system_activity.csv."""
from datetime import datetime, timezone
from util import pick


def _kw(s, kws):
    s = (s or "").lower()
    return any(k in s for k in kws)


def _time_value(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def _at_or_before(ts, cutoff):
    if not ts or not cutoff:
        return True
    parsed_ts, parsed_cutoff = _time_value(ts), _time_value(cutoff)
    if parsed_ts is not None and parsed_cutoff is not None:
        return parsed_ts <= parsed_cutoff
    return ts <= cutoff


def user_events(activity, ident, audit_at, cfg):
    A = cfg["activity"]
    toks = ident.all_tokens() | {u.lower() for u in ident.user_ids if u}
    uid_low = {u.lower() for u in ident.user_ids if u}
    ev = []
    for r in activity:
        ts = pick(r, A["ts"])
        if not _at_or_before(ts, audit_at):
            continue
        row_uid = pick(r, A["user_id"]).lower()
        blob = " ".join(str(v) for v in r.values()).lower()
        if (row_uid and row_uid in uid_low) or any(t in blob for t in toks):
            ev.append(
                dict(
                    id=pick(r, A["activity_id"]),
                    ts=ts,
                    sys=pick(r, A["system_id"]),
                    res=pick(r, A["resource_id"]),
                    op=pick(r, A["operation"]).upper(),
                    st=pick(r, A["status"]).lower(),
                    raw=r,
                )
            )
    return sorted(
        ev,
        key=lambda e: ((_time_value(e["ts"]) is None, _time_value(e["ts"]) or e["ts"]), e["id"]),
    )


def flows(events, cfg):
    """Return dict kind -> {(sys, res): (state, last_event_id)} using the latest event per resource."""
    K = cfg["flow_keywords"]
    last = {}
    for e in events:
        txt = f'{e["op"]} {e["res"]} {e["sys"]}'.lower()
        kind = (
            "restore"
            if _kw(txt, K["restore"])
            else "flow"
            if _kw(txt, K["flow"])
            else None
        )
        if kind:
            last[(kind, e["sys"], e["res"])] = e
    out = {"flow": {}, "restore": {}}
    for (kind, s, r), e in last.items():
        off = (
            _kw(e["op"], ["disable", "pause", "stop", "block", "revoke", "cancel", "terminate"])
            or e["st"] in K["off_status"]
        )
        out[kind][(s, r)] = ("DISABLED" if off else "ACTIVE", e["id"])
    return out


def _is_failed_status(st, cfg):
    failed = cfg.get("flow_keywords", {}).get(
        "failed_status", ["failed", "error", "rejected", "aborted", "skipped", "pending", "not_started"]
    )
    return (st or "").strip().lower() in failed


def claimed_deleted(events, cfg=None):
    """(sys, res) whose latest non-flow event is a successful delete/purge/anonymize/redact claim."""
    K = (cfg or {}).get("flow_keywords", {"flow": [], "restore": []})
    last = {}
    for e in events:
        if not e["res"]:
            continue
        txt = f'{e["op"]} {e["res"]} {e["sys"]}'.lower()
        if _kw(txt, K.get("restore", [])) or _kw(txt, K.get("flow", [])):
            continue
        last[(e["sys"], e["res"])] = e

    out = {}
    for k, e in last.items():
        if _is_failed_status(e["st"], cfg or {}):
            continue
        op = e["op"].upper()
        if any(w in op for w in ("DELETE", "PURGE", "ERASE", "REMOVE", "DROP")):
            out[k] = dict(e, claim_type="ABSENT")
        elif any(w in op for w in ("ANONYMIZ", "DEIDENTIF", "UNLINK")):
            out[k] = dict(e, claim_type="ANONYMIZED")
        elif any(w in op for w in ("REDACT", "TOMBSTONE", "MASK")):
            out[k] = dict(e, claim_type="REDACTED")
    return out
