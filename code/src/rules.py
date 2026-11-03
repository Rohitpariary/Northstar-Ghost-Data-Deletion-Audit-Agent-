"""Policy rules lookup from deletion_rules.csv, including required treatment and permitted identifiers."""
import re
from util import pick


class Rules:
    def __init__(self, rows, cfg):
        self.cfg = cfg
        self.rows = rows
        self.R = cfg["rules"]

    def _match_rule(self, system_id, table=None, resource_id=""):
        best, best_score = None, -1
        target_system = (system_id or "").strip().casefold()
        target_table = (table or "").strip().replace("_", " ").casefold()
        target_res = re.sub(r"_\d+$", "", (resource_id or "").strip()).replace("_", " ").casefold()

        for r in self.rows:
            rule_system = pick(r, self.R["system_id"]).strip().casefold()
            category = pick(r, self.R["category"]).strip().replace("_", " ").casefold()
            score = 0
            if rule_system:
                if rule_system == target_system:
                    score += 100
                elif rule_system in target_system or target_system in rule_system:
                    score += 60
                else:
                    continue
            if category:
                if target_table and target_table == category:
                    score += 50
                elif target_table and (target_table in category or category in target_table):
                    score += 25
                elif target_res and (target_res == category or target_res in category or category in target_res):
                    score += 20
                elif target_system and (target_system in category or category in target_system):
                    score += 15
            if score > best_score:
                best, best_score = r, score
        return best if best_score > 0 else None

    def treatment(self, system_id, table=None, resource_id=""):
        best = self._match_rule(system_id, table, resource_id)
        if not best:
            return "DELETE_RECORD"  # Default-safe: unknown copies must be deleted
        t = pick(best, self.R["treatment"]).lower()
        for k, v in sorted(self.cfg["treatment_map"].items(), key=lambda item: len(item[0]), reverse=True):
            if k in t:
                return v
        return "DELETE_RECORD"

    def permitted_fields(self, system_id, table=None, resource_id=""):
        best = self._match_rule(system_id, table, resource_id)
        if not best:
            return set()
        raw = pick(best, self.R.get("keep_fields", ["permitted_identifiers", "retained_fields", "allowed_identifiers"]))
        if not raw or raw.strip().lower() in ("none", "null", "-", "n/a"):
            return set()
        return {
            tok.strip().lower()
            for tok in re.split(r"[,;|/\s]+", raw)
            if tok.strip() and tok.strip().lower() not in ("none", "null", "-", "n/a")
        }
