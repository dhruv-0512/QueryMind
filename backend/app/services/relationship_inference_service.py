import re
import logging
from typing import Dict, Any, List, Set, Tuple, Optional

logger = logging.getLogger(__name__)

# Configurable Scoring Weights (Must sum to 1.0)
WEIGHT_NAME_SIMILARITY: float = 0.35
WEIGHT_DATATYPE_COMPAT: float = 0.20
WEIGHT_VALUE_OVERLAP: float = 0.25
WEIGHT_UNIQUENESS: float = 0.15
WEIGHT_CARDINALITY: float = 0.05

# Configurable Confidence Thresholds
CONFIDENCE_STRONG_THRESHOLD: float = 0.85
CONFIDENCE_POSSIBLE_THRESHOLD: float = 0.70

# Datatype Groupings
TYPE_GROUPS = {
    "integer": {"integer", "bigint", "smallint", "serial", "int", "int4", "int8", "number"},
    "float": {"float", "double", "real", "numeric", "decimal"},
    "string": {"varchar", "text", "char", "string"},
    "uuid": {"uuid"},
    "date": {"date", "timestamp", "timestamptz", "datetime"},
}

# Explicit Exclusion Patterns for Ordinary Attribute/Descriptive Columns
EXCLUDED_ATTRIBUTE_EXACT = {
    "name", "first_name", "last_name", "full_name", "user_name", "username", "prospect_full_name",
    "email", "emails", "contact_email", "contact_emails", "work_email",
    "phone", "mobile", "contact_mobile_phone", "contact_number", "contact_phone", "phone_number",
    "address", "street", "city", "country", "state", "zip", "postal_code",
    "title", "job_title", "prospect_job_title", "position", "role",
    "company", "company_name", "prospect_company", "prospect_company_name", "organization",
    "description", "notes", "status", "type", "category", "gender", "age",
    "created_at", "updated_at", "deleted_at", "timestamp", "date", "created_date",
    "url", "website", "linkedin", "prospect_linkedin", "prospect_company_website", "avatar", "image"
}

EXCLUDED_SUFFIXES = (
    "_name", "_email", "_emails", "_phone", "_mobile", "_address", "_date",
    "_time", "_at", "_url", "_website", "_linkedin", "_title", "_status",
    "_type", "_company", "_city", "_country", "_state", "_zip", "_description",
    "_notes", "_comment", "_comments", "_code"
)


class RelationshipInferenceService:
    def __init__(self):
        self.w_name = WEIGHT_NAME_SIMILARITY
        self.w_type = WEIGHT_DATATYPE_COMPAT
        self.w_overlap = WEIGHT_VALUE_OVERLAP
        self.w_uniq = WEIGHT_UNIQUENESS
        self.w_card = WEIGHT_CARDINALITY
        self.strong_thresh = CONFIDENCE_STRONG_THRESHOLD
        self.possible_thresh = CONFIDENCE_POSSIBLE_THRESHOLD

    def _normalize_name(self, name: str) -> str:
        """
        Normalize identifier by handling camelCase, lowercasing,
        and stripping non-alphanumeric characters.
        e.g., 'customerId' -> 'customer_id'
        """
        if not name:
            return ""
        s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
        s = s.lower().strip()
        s = re.sub(r'[^a-z0-9_]', '', s)
        return s

    def _stem_table_name(self, tbl_name: str) -> str:
        """Remove trailing 's' or 'es' plural suffixes for table stemming."""
        norm = self._normalize_name(tbl_name)
        if norm.endswith("ies") and len(norm) > 4:
            return norm[:-3] + "y"
        if norm.endswith("es") and len(norm) > 3:
            return norm[:-2]
        if norm.endswith("s") and len(norm) > 2:
            return norm[:-1]
        return norm

    def is_attribute_column(self, col_name: str) -> bool:
        """Check if column is a generic attribute (name, email, phone, timestamp, company, etc)."""
        norm = self._normalize_name(col_name)
        if norm in EXCLUDED_ATTRIBUTE_EXACT:
            return True
        if norm.endswith(EXCLUDED_SUFFIXES):
            return True
        return False

    def is_key_candidate(self, col_name: str) -> bool:
        """Check if column plausibly represents a Foreign Key or Primary Key identifier."""
        norm = self._normalize_name(col_name)
        if self.is_attribute_column(col_name):
            return False
        if norm in ("id", "key", "uuid", "guid"):
            return True
        if norm.endswith(("_id", "_key", "_uuid", "_guid")):
            return True
        return False

    def calculate_name_similarity(
        self,
        col_src: str,
        tbl_src: str,
        col_tgt: str,
        tbl_tgt: str
    ) -> float:
        """
        Signal A: Key-Aware Column & Table Name Alignment.
        Requires key semantics and table-column stem matching.
        """
        norm_src_col = self._normalize_name(col_src)
        norm_tgt_col = self._normalize_name(col_tgt)
        norm_src_tbl = self._normalize_name(tbl_src)
        norm_tgt_tbl = self._normalize_name(tbl_tgt)
        stem_tgt_tbl = self._stem_table_name(tbl_tgt)
        stem_src_tbl = self._stem_table_name(tbl_src)

        src_stem_col = re.sub(r'_(id|key|uuid|guid)$', '', norm_src_col)
        tgt_stem_col = re.sub(r'_(id|key|uuid|guid)$', '', norm_tgt_col)

        # Exact match on key column name where column stem matches target table stem (e.g. orders.customer_id -> customers.customer_id)
        if norm_src_col == norm_tgt_col and norm_src_col.endswith(("_id", "_key", "_uuid")):
            if src_stem_col in (stem_tgt_tbl, norm_tgt_tbl, stem_src_tbl, norm_src_tbl):
                return 1.0
            return 0.85

        # Key mapping pattern: orders.customer_id -> customers.id
        if (src_stem_col == stem_tgt_tbl or src_stem_col == norm_tgt_tbl) and norm_tgt_col in ("id", "key", "uuid", norm_src_col):
            return 0.98

        # Reverse key mapping pattern: customers.id <- orders.customer_id
        if (tgt_stem_col == stem_src_tbl or tgt_stem_col == norm_src_tbl) and norm_src_col in ("id", "key", "uuid", norm_tgt_col):
            return 0.95

        # Unrelated generic 'id' to 'id' across tables without matching table stems (e.g. customers.id ↔ products.id)
        if norm_src_col in ("id", "key") and norm_tgt_col in ("id", "key"):
            return 0.0

        return 0.0

    def calculate_datatype_compatibility(self, type_src: str, type_tgt: str) -> float:
        """
        Signal B: Datatype Compatibility.
        """
        t_a = (type_src or "varchar").lower()
        t_b = (type_tgt or "varchar").lower()

        if t_a == t_b:
            return 1.0

        group_a = None
        group_b = None
        for g_name, g_set in TYPE_GROUPS.items():
            if any(k in t_a for k in g_set):
                group_a = g_name
            if any(k in t_b for k in g_set):
                group_b = g_name

        if group_a and group_b and group_a == group_b:
            return 0.90

        if (group_a == "integer" and group_b == "float") or (group_a == "float" and group_b == "integer"):
            return 0.60

        return 0.0

    def calculate_value_overlap_and_stats(
        self,
        vals_src: List[Any],
        vals_tgt: List[Any],
        max_sample: int = 1000
    ) -> Tuple[float, float, float, str]:
        """
        Signal C, D, E: Value Overlap Containment, Target Uniqueness, and Cardinality.
        """
        clean_src = [v for v in vals_src if v is not None and str(v).strip() != ""]
        clean_tgt = [v for v in vals_tgt if v is not None and str(v).strip() != ""]

        if not clean_src or not clean_tgt:
            return (0.0, 0.0, 0.5, "many-to-many")

        sample_src = clean_src[:max_sample]
        sample_tgt = clean_tgt[:max_sample]

        set_src = set(sample_src)
        set_tgt = set(sample_tgt)

        # Value containment: fraction of source FK values existing in target PK values
        intersection = set_src.intersection(set_tgt)
        containment = (len(intersection) / len(set_src)) if len(set_src) > 0 else 0.0

        tgt_total = len(sample_tgt)
        tgt_distinct = len(set_tgt)
        uniqueness_ratio = (tgt_distinct / tgt_total) if tgt_total > 0 else 0.0
        target_uniqueness_score = 1.0 if uniqueness_ratio >= 0.95 else round(uniqueness_ratio, 4)

        src_total = len(sample_src)
        src_distinct = len(set_src)
        src_uniqueness_ratio = (src_distinct / src_total) if src_total > 0 else 0.0

        if target_uniqueness_score >= 0.90 and src_uniqueness_ratio < 0.90:
            cardinality_type = "many-to-one"
            cardinality_score = 1.0
        elif target_uniqueness_score >= 0.90 and src_uniqueness_ratio >= 0.90:
            cardinality_type = "one-to-one"
            cardinality_score = 0.90
        else:
            cardinality_type = "many-to-many"
            cardinality_score = 0.30

        return (round(containment, 4), target_uniqueness_score, cardinality_score, cardinality_type)

    def detect_candidate_relationships(
        self,
        schema_info: Dict[str, Any],
        sample_data: Optional[Dict[str, Dict[str, List[Any]]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Key-Aware Deterministic Discovery Engine.
        Returns candidate foreign-key relationships sorted by score.
        Gated strictly by key semantics and directional uniqueness to prevent false positives.
        """
        tables_dict = schema_info.get("tables", {})
        table_names = list(tables_dict.keys())
        if len(table_names) < 2:
            return []

        candidates = []
        evaluated_pairs = set()

        for i in range(len(table_names)):
            for j in range(i + 1, len(table_names)):
                tbl_a = table_names[i]
                tbl_b = table_names[j]

                meta_a = tables_dict[tbl_a]
                meta_b = tables_dict[tbl_b]

                cols_a = meta_a.get("columns", []) if isinstance(meta_a, dict) else meta_a
                cols_b = meta_b.get("columns", []) if isinstance(meta_b, dict) else meta_b

                types_a = meta_a.get("column_types", {}) if isinstance(meta_a, dict) else {}
                types_b = meta_b.get("column_types", {}) if isinstance(meta_b, dict) else {}

                for col_a in cols_a:
                    for col_b in cols_b:
                        # 1. HARD GATE: Reject attribute columns (names, emails, phones, created_at, etc)
                        if self.is_attribute_column(col_a) or self.is_attribute_column(col_b):
                            continue

                        # 2. HARD GATE: At least one column MUST be a key candidate (id, *_id, *_key, *_uuid)
                        if not self.is_key_candidate(col_a) and not self.is_key_candidate(col_b):
                            continue

                        # 3. Datatype Compatibility
                        type_a = types_a.get(col_a, "varchar")
                        type_b = types_b.get(col_b, "varchar")
                        score_type = self.calculate_datatype_compatibility(type_a, type_b)
                        if score_type == 0.0:
                            continue

                        # Determine correct direction: tbl_src (FK, contains duplicates) -> tbl_tgt (PK, unique)
                        vals_a = sample_data.get(tbl_a, {}).get(col_a, []) if sample_data else []
                        vals_b = sample_data.get(tbl_b, {}).get(col_b, []) if sample_data else []

                        sim_a_to_b = self.calculate_name_similarity(col_a, tbl_a, col_b, tbl_b)
                        sim_b_to_a = self.calculate_name_similarity(col_b, tbl_b, col_a, tbl_a)

                        if sim_a_to_b == 0.0 and sim_b_to_a == 0.0:
                            continue

                        # Decide direction based on name alignment & target uniqueness
                        if sim_a_to_b >= sim_b_to_a:
                            tbl_src, col_src, type_src, vals_src = tbl_a, col_a, type_a, vals_a
                            tbl_tgt, col_tgt, type_tgt, vals_tgt = tbl_b, col_b, type_b, vals_b
                            score_name = sim_a_to_b
                        else:
                            tbl_src, col_src, type_src, vals_src = tbl_b, col_b, type_b, vals_b
                            tbl_tgt, col_tgt, type_tgt, vals_tgt = tbl_a, col_a, type_a, vals_a
                            score_name = sim_b_to_a

                        # Overlap stats
                        if vals_src and vals_tgt:
                            score_overlap, score_uniq, score_card, card_type = self.calculate_value_overlap_and_stats(vals_src, vals_tgt)
                        else:
                            score_overlap = 0.85
                            score_uniq = 1.0 if (col_tgt.lower() in ("id", "key", "uuid") or col_tgt.lower() == f"{tbl_tgt.lower()[:-1]}_id") else 0.75
                            score_card = 1.0
                            card_type = "many-to-one"

                        # Weighted Score
                        total_score = round(
                            (score_name * self.w_name) +
                            (score_type * self.w_type) +
                            (score_overlap * self.w_overlap) +
                            (score_uniq * self.w_uniq) +
                            (score_card * self.w_card),
                            4
                        )

                        if total_score >= self.possible_thresh:
                            confidence_level = "strong" if total_score >= self.strong_thresh else "possible"

                            pair_key = (tbl_src.lower(), col_src.lower(), tbl_tgt.lower(), col_tgt.lower())
                            if pair_key not in evaluated_pairs:
                                evaluated_pairs.add(pair_key)
                                candidates.append({
                                    "source_table": tbl_src,
                                    "source_column": col_src,
                                    "target_table": tbl_tgt,
                                    "target_column": col_tgt,
                                    "score": total_score,
                                    "confidence_level": confidence_level,
                                    "cardinality": card_type,
                                    "signals": {
                                        "name_similarity": score_name,
                                        "datatype_compatibility": score_type,
                                        "value_overlap": score_overlap,
                                        "uniqueness": score_uniq,
                                        "cardinality": score_card,
                                    }
                                })

        return sorted(candidates, key=lambda x: x["score"], reverse=True)


relationship_inference_service = RelationshipInferenceService()
