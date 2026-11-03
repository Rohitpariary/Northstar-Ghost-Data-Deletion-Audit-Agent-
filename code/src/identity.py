"""Resolve current and historical identifiers for a request email."""
import hashlib
from util import pick, norm_email

PHONE_FIELDS = ("phone", "mobile", "tel", "contact")


def digits(s):
    return "".join(ch for ch in (s or "") if ch.isdigit())


def hashes_of(value):
    if not value:
        return set()
    v_bytes = value.strip().encode("utf-8")
    low_bytes = value.strip().lower().encode("utf-8")
    out = set()
    for b in (v_bytes, low_bytes):
        for algo in ("md5", "sha1", "sha256"):
            out.add(getattr(hashlib, algo)(b).hexdigest().lower())
    return out


class Identity:
    def __init__(self):
        self.user_ids = set()
        self.emails = set()
        self.phones = set()
        self.names = set()
        self.hashes = set()
        self.audit_ids = set()

    def phone_tokens(self):
        out = set()
        for p in self.phones:
            d = digits(p)
            if len(d) >= 7:
                out.add(p.strip().lower())
                out.add(d)
                if len(d) > 10:
                    out.add(d[-10:])
        return out

    def all_tokens(self):
        t = set(self.emails) | set(self.hashes)
        t |= {n.strip().lower() for n in self.names if len(n.strip()) > 3}
        t |= self.phone_tokens()
        return {x for x in t if x}


def resolve(email, identities, audit, cfg):
    I, A = cfg["identities"], cfg["audit_log"]
    ident = Identity()
    raw_email = (email or "").strip()
    target = norm_email(raw_email)
    if target:
        ident.emails.add(target)
        ident.hashes |= hashes_of(raw_email)

    # Seed user_ids from current identities or historical audit log by email or email_hash
    for r in identities:
        row_email = norm_email(pick(r, I["email"]))
        row_hash = pick(r, I["email_hash"]).lower()
        if (row_email and row_email == target) or (row_hash and row_hash in ident.hashes):
            ident.user_ids.add(pick(r, I["user_id"]))

    for r in audit:
        old_val = pick(r, A["old"])
        new_val = pick(r, A["new"])
        if target in (norm_email(old_val), norm_email(new_val)) or (
            old_val.lower() in ident.hashes or new_val.lower() in ident.hashes
        ):
            ident.user_ids.add(pick(r, A["user_id"]))
            aid = pick(r, A["audit_id"])
            if aid:
                ident.audit_ids.add(aid)

    ident.user_ids.discard("")

    # Expand all current identifiers for matched user_ids
    for r in identities:
        uid = pick(r, I["user_id"])
        if uid in ident.user_ids:
            em = norm_email(pick(r, I["email"]))
            if em:
                ident.emails.add(em)
                ident.hashes |= hashes_of(pick(r, I["email"]))
            ph = pick(r, I["phone"])
            if ph:
                ident.phones.add(ph)
            nm = pick(r, I["name"])
            if nm:
                ident.names.add(nm)
            eh = pick(r, I["email_hash"])
            if eh:
                ident.hashes.add(eh.lower())

    # Expand all historical identifiers from user_audit_log for matched user_ids
    for r in audit:
        uid = pick(r, I["user_id"]) or pick(r, A["user_id"])
        if uid in ident.user_ids:
            aid = pick(r, A["audit_id"])
            if aid:
                ident.audit_ids.add(aid)
            f = pick(r, A["field"]).lower()
            for v in (pick(r, A["old"]), pick(r, A["new"])):
                if not v:
                    continue
                if "email" in f and "hash" not in f:
                    ident.emails.add(norm_email(v))
                    ident.hashes |= hashes_of(v)
                elif "hash" in f:
                    ident.hashes.add(v.lower())
                elif any(p in f for p in PHONE_FIELDS):
                    ident.phones.add(v)
                elif "name" in f:
                    ident.names.add(v)

    ident.emails.discard("")
    for e in list(ident.emails):
        ident.hashes |= hashes_of(e)
    return ident
