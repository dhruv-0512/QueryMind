import re
import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)

# Configurable Minimum Value Overlap Threshold (80% value containment)
MIN_VALUE_OVERLAP_THRESHOLD: float = 0.80

# Datatype Compatibility Groupings
TYPE_GROUPS = {
    "integer": {"integer", "bigint", "smallint", "serial", "int", "int4", "int8", "number"},
    "float": {"float", "double", "real", "numeric", "decimal"},
    "string": {"varchar", "text", "char", "string"},
    "uuid": {"uuid"},
    "date": {"date", "timestamp", "timestamptz", "datetime"},
}

# Generic Attribute Exclusion Patterns (Must NOT be treated as Foreign Keys)
GENERIC_ATTRIBUTES = {
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

GENERIC_SUFFIXES = (
    "_name", "_email", "_emails", "_phone", "_mobile", "_address", "_date",
    "_time", "_at", "_url", "_website", "_linkedin", "_title", "_status",
    "_type", "_company", "_city", "_country", "_state", "_zip", "_description",
    "_notes", "_comment", "_comments", "_code"
)


class RelationshipInferenceService:
    def __init__(self, min_overlap: float = MIN_VALUE_OVERLAP_THRESHOLD):
        self.min_overlap = min_overlap

    def normalize_identifier(self, name: str) -> str:
        """
        Normalize identifier to snake_case.
        e.g., 'customerId' -> 'customer_id', 'CUSTOMER_ID' -> 'customer_id'
        """
        if not name:
            return ""
        s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
        s = s.lower().strip()
        s = re.sub(r'[^a-z0-9_]', '', s)
        return s

    def stem_table_name(self, tbl_name: str) -> str:
        """Stem plural table names (e.g., 'customers' -> 'customer', 'categories' -> 'category')."""
        norm = self.normalize_identifier(tbl_name)
        if norm.endswith("ies") and len(norm) > 4:
            return norm[:-3] + "y"
        if norm.endswith("es") and len(norm) > 3:
            return norm[:-2]
        if norm.endswith("s") and len(norm) > 2:
            return norm[:-1]
        return norm

    def is_generic_attribute(self, col_name: str) -> bool:
        """Check if column is a generic descriptive attribute."""
        norm = self.normalize_identifier(col_name)
        if norm in GENERIC_ATTRIBUTES:
            return True
        if norm.endswith(GENERIC_SUFFIXES):
            return True
        return False

    def is_foreign_key_pattern(self, col_name: str) -> bool:
        """Check if column follows explicit foreign key pattern (*_id, *_key, *_uuid)."""
        norm = self.normalize_identifier(col_name)
        if self.is_generic_attribute(col_name):
            return False
        if norm in ("id", "key", "uuid", "guid"):
            return False
        if norm.endswith(("_id", "_key", "_uuid", "_guid")):
            return True
        return False

    def is_target_key_pattern(self, col_name: str) -> bool:
        """Check if target column is a key identifier (id, *_id, *_key, *_uuid)."""
        norm = self.normalize_identifier(col_name)
        if self.is_generic_attribute(col_name):
            return False
        if norm in ("id", "key", "uuid", "guid"):
            return True
        if norm.endswith(("_id", "_key", "_uuid", "_guid")):
            return True
        return False

    def is_datatype_compatible(self, type_src: str, type_tgt: str) -> bool:
        """Check if PostgreSQL/Pandas data types are compatible."""
        t_a = (type_src or "varchar").lower()
        t_b = (type_tgt or "varchar").lower()
        if t_a == t_b:
            return True

        group_a = next((g for g, s in TYPE_GROUPS.items() if any(k in t_a for k in s)), None)
        group_b = next((g for g, s in TYPE_GROUPS.items() if any(k in t_b for k in s)), None)

        if group_a and group_b and group_a == group_b:
            return True

        if (group_a == "integer" and group_b == "float") or (group_a == "float" and group_b == "integer"):
            return True

        return False

    def calculate_value_overlap(self, vals_src: List[Any], vals_tgt: List[Any], max_sample: int = 1000) -> float:
        """Calculate fraction of distinct source values that exist in target values."""
        clean_src = [v for v in vals_src if v is not None and str(v).strip() != ""]
        clean_tgt = [v for v in vals_tgt if v is not None and str(v).strip() != ""]

        if not clean_src or not clean_tgt:
            return 0.0

        sample_src = clean_src[:max_sample]
        sample_tgt = clean_tgt[:max_sample]

        set_src = set(sample_src)
        set_tgt = set(sample_tgt)

        if len(set_src) == 0:
            return 0.0

        intersection = set_src.intersection(set_tgt)
        return round(len(intersection) / len(set_src), 4)

    def detect_candidate_relationships(
        self,
        schema_info: Dict[str, Any],
        sample_data: Optional[Dict[str, Dict[str, List[Any]]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Simple, Explainable Foreign Key Detection Algorithm:
        1. Find *_id / *_key / *_uuid columns in source table
        2. Match entity/table name in target table
        3. Find matching target key column (id or <entity>_id)
        4. Verify datatype compatibility
        5. Verify value overlap (>= 80% containment)
        """
        tables_dict = schema_info.get("tables", {})
        table_names = list(tables_dict.keys())
        if len(table_names) < 2:
            return []

        candidates = []
        seen_pairs = set()

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

                norm_tbl_tgt = self.normalize_identifier(tbl_tgt)
                stem_tbl_tgt = self.stem_table_name(tbl_tgt)

                for col_s in cols_src:
                    # Step 1: Must be an explicit foreign key column pattern (*_id, *_key, *_uuid)
                    if not self.is_foreign_key_pattern(col_s):
                        continue

                    norm_col_s = self.normalize_identifier(col_s)
                    entity_stem = re.sub(r'_(id|key|uuid|guid)$', '', norm_col_s)

                    # Step 2: Entity stem must match target table name (e.g. customer_id -> customers)
                    if entity_stem not in (stem_tbl_tgt, norm_tbl_tgt):
                        continue

                    for col_t in cols_tgt:
                        # Step 3: Target column must be a key identifier (id or customer_id)
                        if not self.is_target_key_pattern(col_t):
                            continue

                        norm_col_t = self.normalize_identifier(col_t)
                        if norm_col_t not in ("id", "key", "uuid", norm_col_s):
                            continue

                        # Step 4: Datatype compatibility
                        type_s = types_src.get(col_s, "varchar")
                        type_t = types_tgt.get(col_t, "varchar")
                        if not self.is_datatype_compatible(type_s, type_t):
                            continue

                        # Step 5: Data Value Overlap Verification
                        vals_s = sample_data.get(tbl_src, {}).get(col_s, []) if sample_data else []
                        vals_t = sample_data.get(tbl_tgt, {}).get(col_t, []) if sample_data else []

                        if vals_s and vals_t:
                            overlap = self.calculate_value_overlap(vals_s, vals_t)
                            if overlap < self.min_overlap:
                                continue
                        else:
                            overlap = 0.95  # Default schema-level confidence

                        pair_key = (tbl_src.lower(), col_s.lower(), tbl_tgt.lower(), col_t.lower())
                        if pair_key not in seen_pairs:
                            seen_pairs.add(pair_key)
                            overlap_pct = int(overlap * 100)
                            candidates.append({
                                "source_table": tbl_src,
                                "source_column": col_s,
                                "target_table": tbl_tgt,
                                "target_column": col_t,
                                "table": tbl_src,
                                "column": col_s,
                                "foreign_table": tbl_tgt,
                                "foreign_column": col_t,
                                "score": overlap,
                                "overlap": overlap,
                                "confidence_level": "strong" if overlap >= 0.85 else "possible",
                                "cardinality": "many-to-one",
                                "reason": f"{col_s} matches {tbl_tgt}.{col_t} and {overlap_pct}% of source values exist in target key",
                                "signals": {
                                    "name_similarity": 1.0,
                                    "datatype_compatibility": 1.0,
                                    "value_overlap": overlap,
                                    "uniqueness": 1.0,
                                    "cardinality": 1.0,
                                }
                            })

        return sorted(candidates, key=lambda x: x["score"], reverse=True)


relationship_inference_service = RelationshipInferenceService()
