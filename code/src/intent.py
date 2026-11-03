"""Deterministic request-intent classifier."""
import re

NEG = re.compile(
    r"(not asking for deletion|not a deletion request|not a request to (delete|erase|remove|close)|"
    r"don'?t\s+(?:want\s+you\s+to\s+|want\s+|need\s+to\s+)?(delete|erase|remove|close)|"
    r"do not\s+(?:want\s+you\s+to\s+|want\s+|need\s+to\s+)?(delete|erase|remove|close)|"
    r"do not close|please don'?t (delete|erase|remove|close)|"
    r"leave the account active|keep the account|keep my account|marketing lists only|stop the promotional|"
    r"without removing|leave my profile|not asking to delete|continue using the service|"
    r"n[aã]o quero (excluir|apagar|deletar)|no quiero (eliminar|borrar)|"
    r"ne (supprimez|fermez) pas|삭제하지|削除しないで)",
    re.I,
)

POS = re.compile(
    r"(delet(e|ed|ing|ion)|eras(e|ed|ing|ure)|permanent(ly)? (account|deleted|removal|erasure)|"
    r"clos(e|ed|ing)|remove\s+(the|my|this)?\s*(profile|account|personal|record|information)|"
    r"exclus[aã]o|excluir|eliminaci[oó]n|eliminar|suppression|supprimer|삭제|削除|"
    r"right to be forgotten|gdpr)",
    re.I,
)

def wants_deletion(text: str) -> bool:
    if not text or not text.strip():
        return False
    if NEG.search(text):
        return False
    return bool(POS.search(text))
