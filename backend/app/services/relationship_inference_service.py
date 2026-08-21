import re
import logging
from typing import Dict, Any, List, Set, Tuple, Optional
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Configurable Scoring Weights (Must sum to 1.0)
WEIGHT_NAME_SIMILARITY: float = 0.30
WEIGHT_DATATYPE_COMPAT: float = 0.20
WEIGHT_VALUE_OVERLAP: float = 0.30
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
        e.g., 'customerId' -> 'customer_id' -> 'customer id'
        """
        if not name:
            return ""
        # Convert camelCase to snake_case
        s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
        s = s.lower().strip()
        s = re.sub(r'[^a-z0-9_]', '', s)
        return s

    def _stem_table_name(self, tbl_name: str) -> str:
        """Remove trailing 's' or 'es' plural suffixes for stemming."""
        norm = self._normalize_name(tbl_name)
        if norm.endswith("ies") and len(norm) > 4:
            return norm[:-3] + "y"
        if norm.endswith("es") and len(norm) > 3:
            return norm[:-2]
        if norm.endswith("s") and len(norm) > 2:
            return norm[:-1]
        return norm

    def calculate_name_similarity(
        self,
        col_src: str,
        tbl_src: str,
        col_tgt: str,
        tbl_tgt: str
    ) -> float:
        """
        Signal A: Column & Table Name Similarity.
        Handles suffixes: _id, id, _key, key, camelCase.
        """
        norm_src_col = self._normalize_name(col_src)
        norm_tgt_col = self._normalize_name(col_tgt)
        norm_src_tbl = self._normalize_name(tbl_src)
        norm_tgt_tbl = self._normalize_name(tbl_tgt)
        stem_tgt_tbl = self._stem_table_name(tbl_tgt)

        # Exact column match on non-generic column name (e.g., customer_id == customer_id)
        if norm_src_col == norm_tgt_col and norm_src_col not in ("id", "key", "code"):
            return 1.0

        # Pattern: orders.customer_id -> customers.id or customers.customer_id
        src_stem_col = re.sub(r'_(id|key)$', '', norm_src_col)
        tgt_stem_col = re.sub(r'_(id|key)$', '', norm_tgt_col)

        if (src_stem_col == stem_tgt_tbl or src_stem_col == norm_tgt_tbl) and norm_tgt_col in ("id", "key", norm_src_col):
            return 0.98

        if (tgt_stem_col == stem_tgt_tbl or tgt_stem_col == norm_tgt_tbl) and norm_src_col in ("id", "key", norm_tgt_col):
            return 0.95

        if norm_src_col in ("id", "key") and (tgt_stem_col == self._stem_table_name(tbl_src)):
            return 0.90

        # Fuzzy string similarity ratio
        seq_ratio = SequenceMatcher(None, norm_src_col, norm_tgt_col).ratio()
        if norm_src_col == norm_tgt_col:
            return 0.80  # exact match on generic 'id'

        return round(seq_ratio * 0.7, 4)

    def calculate_datatype_compatibility(self, type_src: str, type_tgt: str) -> float:
        """
        Signal B: Datatype Compatibility.
        Compares inferred PostgreSQL/Pandas data types.
        """
        t_a = (type_src or "varchar").lower()
        t_b = (type_tgt or "varchar").lower()

        if t_a == t_b:
            return 1.0

        # Find matching group
        group_a = None
        group_b = None
        for g_name, g_set in TYPE_GROUPS.items():
            if any(k in t_a for k in g_set):
                group_a = g_name
            if any(k in t_b for k in g_set):
                group_b = g_name

        if group_a and group_b and group_a == group_b:
            return 0.90  # compatible within same group (e.g. int4 vs int8)

        if (group_a == "integer" and group_b == "float") or (group_a == "float" and group_b == "integer"):
            return 0.60  # numeric cross-compatibility

        if group_a is None or group_b is None:
            return 0.50  # unknown/unmapped fallback

        return 0.0  # incompatible types (e.g., date vs integer)

    def calculate_value_overlap_and_stats(
        self,
        vals_src: List[Any],
        vals_tgt: List[Any],
        max_sample: int = 1000
    ) -> Tuple[float, float, float, str]:
        """
        Signal C, D, E: Value Overlap, Uniqueness, and Cardinality.
        Returns: (value_overlap_score, target_uniqueness_score, cardinality_score, cardinality_type)
        """
        # Filter non-null and string-convert non-empty
        clean_src = [v for v in vals_src if v is not None and str(v).strip() != ""]
        clean_tgt = [v for v in vals_tgt if v is not None and str(v).strip() != ""]

        if not clean_src or not clean_tgt:
            return (0.0, 0.0, 0.5, "many-to-many")

        # Bounded sampling for efficiency
        sample_src = clean_src[:max_sample]
        sample_tgt = clean_tgt[:max_sample]

        set_src = set(sample_src)
        set_tgt = set(sample_tgt)

        # 1. Containment value overlap: what fraction of source values exist in target?
        intersection = set_src.intersection(set_tgt)
        if len(set_src) == 0:
            containment = 0.0
        else:
            containment = len(intersection) / len(set_src)

        # 2. Target uniqueness score: is target column unique (primary key / unique index candidate)?
        tgt_total = len(sample_tgt)
        tgt_distinct = len(set_tgt)
        uniqueness_ratio = (tgt_distinct / tgt_total) if tgt_total > 0 else 0.0
        target_uniqueness_score = 1.0 if uniqueness_ratio >= 0.95 else round(uniqueness_ratio, 4)

        # 3. Source uniqueness for cardinality analysis
        src_total = len(sample_src)
        src_distinct = len(set_src)
        src_uniqueness_ratio = (src_distinct / src_total) if src_total > 0 else 0.0

        # Cardinality determination
        if target_uniqueness_score >= 0.90 and src_uniqueness_ratio < 0.90:
            cardinality_type = "many-to-one"
            cardinality_score = 1.0
        elif target_uniqueness_score >= 0.90 and src_uniqueness_ratio >= 0.90:
            cardinality_type = "one-to-one"
            cardinality_score = 0.90
        elif target_uniqueness_score < 0.90 and src_uniqueness_ratio >= 0.90:
            cardinality_type = "one-to-many"
            cardinality_score = 0.40
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
        Main deterministic discovery engine.
        Accepts schema_info metadata + optional column sample data.
        Returns candidate relationships sorted by confidence score.
        """
        tables_dict = schema_info.get("tables", {})
        table_names = list(tables_dict.keys())
        if len(table_names) < 2:
            return []

        candidates = []

        # Step 1: Pre-filter candidate pairs by name and datatype before expensive overlap analysis
        for i in range(len(table_names)):
            for j in range(len(table_names)):
                if i == j:
                    continue
                tbl_src = table_names[i]
                tbl_tgt = table_names[j]

                meta_src = tables_dict[tbl_src]
                meta_tgt = tables_dict[tbl_tgt]

                cols_src = meta_src.get("columns", []) if isinstance(meta_src, dict) else meta_src
                cols_tgt = meta_tgt.get("columns", []) if isinstance(meta_tgt, dict) else meta_tgt

                types_src = meta_src.get("column_types", {}) if isinstance(meta_src, dict) else {}
                types_tgt = meta_tgt.get("column_types", {}) if isinstance(meta_tgt, dict) else {}

                for col_s in cols_src:
                    for col_t in cols_tgt:
                        type_s = types_src.get(col_s, "varchar")
                        type_t = types_tgt.get(col_t, "varchar")

                        # Signal A: Name Similarity
                        score_name = self.calculate_name_similarity(col_s, tbl_src, col_t, tbl_tgt)
                        # Signal B: Datatype Compatibility
                        score_type = self.calculate_datatype_compatibility(type_s, type_t)

                        # Efficiency Guard: Skip if name similarity is very low AND datatypes are incompatible
                        if score_name < 0.20 and score_type == 0.0:
                            continue

                        # Signal C, D, E: Value Overlap, Uniqueness, Cardinality
                        vals_s = []
                        vals_t = []
                        if sample_data and tbl_src in sample_data and col_s in sample_data[tbl_src]:
                            vals_s = sample_data[tbl_src][col_s]
                        if sample_data and tbl_tgt in sample_data and col_t in sample_data[tbl_tgt]:
                            vals_t = sample_data[tbl_tgt][col_t]

                        if vals_s and vals_t:
                            score_overlap, score_uniq, score_card, card_type = self.calculate_value_overlap_and_stats(vals_s, vals_t)
                        else:
                            # If no sample data available, fallback gracefully using name and type signals
                            score_overlap = 0.80 if score_name >= 0.85 else 0.50
                            score_uniq = 1.0 if (col_t.lower() == "id" or col_t.lower() == f"{tbl_tgt.lower()[:-1]}_id") else 0.70
                            score_card = 1.0
                            card_type = "many-to-one"

                        # Weighted Score Calculation
                        total_score = round(
                            (score_name * self.w_name) +
                            (score_type * self.w_type) +
                            (score_overlap * self.w_overlap) +
                            (score_uniq * self.w_uniq) +
                            (score_card * self.w_card),
                            4
                        )

                        # Determine confidence level
                        if total_score >= self.strong_thresh:
                            confidence_level = "strong"
                        elif total_score >= self.possible_thresh:
                            confidence_level = "possible"
                        else:
                            confidence_level = "weak"

                        if total_score >= self.possible_thresh:
                            candidates.append({
                                "source_table": tbl_src,
                                "source_column": col_s,
                                "target_table": tbl_tgt,
                                "target_column": col_t,
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

        # Deduplicate and sort candidates descending by score
        seen_cand_keys = set()
        unique_candidates = []
        for cand in sorted(candidates, key=lambda x: x["score"], reverse=True):
            key = (cand["source_table"].lower(), cand["source_column"].lower(), cand["target_table"].lower(), cand["target_column"].lower())
            if key not in seen_cand_keys:
                seen_cand_keys.add(key)
                unique_candidates.append(cand)

        return unique_candidates


relationship_inference_service = RelationshipInferenceService()
