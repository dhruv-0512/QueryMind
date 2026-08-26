import logging
from typing import Tuple, List, Optional
from app.services.constraint_extraction_service import QueryConstraints, FilterConstraint

logger = logging.getLogger(__name__)

def compare_constraints(
    expected: QueryConstraints,
    actual: QueryConstraints
) -> Tuple[bool, List[str], List[str]]:
    """
    Compare expected query constraints (extracted from user question)
    against actual SQL constraints (extracted from generated SQL AST).
    
    Enforces strict bidirectional invariant:
    - Expected constraints ⊆ Actual SQL constraints
    - Actual SQL constraints ⊆ Expected constraints (no spurious/invented clauses)
    """
    missing: List[str] = []
    altered: List[str] = []

    # 0a. Zero-Constraint Safety Guard:
    # If NL extraction resolved NO discriminating constraints (no filters, no group_by,
    # no aggregations, no order_by, no limit) AND actual SQL is a bare SELECT *,
    # the composition is meaningless — reject and let LLM handle it.
    nl_has_no_constraints = (
        not expected.filters
        and not expected.group_by
        and not expected.aggregations
        and not expected.order_by
        and expected.limit is None
    )
    actual_is_bare_select_star = (
        not actual.filters
        and not actual.group_by
        and not actual.aggregations
        and not actual.order_by
        and actual.limit is None
    )
    if nl_has_no_constraints and actual_is_bare_select_star and len(expected.tables) == 1:
        # Single-table bare SELECT * with no extractable constraints: cannot validate correctness
        missing.append("under_constrained:cannot_validate_bare_select_star")

    # 0b. Subquery / Unresolved Facets Safety Check
    if expected.has_subquery or expected.unresolved_facets:
        altered.append("complex_subquery_or_unresolved_facets")

    # 1. Table Coverage & Multi-Table Join Validation
    for req_table in expected.tables:
        if req_table.lower() not in actual.tables:
            missing.append(f"table:{req_table}")

    if len(expected.tables) >= 2:
        if len(actual.tables) < len(expected.tables) or not actual.joins:
            missing.append(f"joins:expected_{len(expected.tables)}_tables_joined")

        for req_join in expected.joins:
            if req_join.join_type == "LEFT":
                actual_left_joins = [j for j in actual.joins if "LEFT" in j.join_type.upper()]
                if not actual_left_joins:
                    altered.append("join_type:expected_LEFT_JOIN_got_INNER")

    # 2. Projection & Multi-Entity Attribute Validation
    TEXT_COLUMNS = {"name", "city", "category", "status", "product_name", "title", "description", "email"}

    if len(expected.tables) >= 2 and len(actual.tables) == 1:
        missing.append("projection:single_table_cannot_satisfy_multi_table_entities")

    # Column coverage for explicit entity projections without aggregations
    if not expected.aggregations and expected.columns:
        for req_col in expected.columns:
            if req_col.lower() not in actual.columns:
                missing.append(f"column:{req_col}")

    # 3. Bidirectional Filter Validation (Never drop WHERE & Never invent spurious WHERE)
    if not expected.filters and actual.filters:
        for act_f in actual.filters:
            altered.append(f"spurious_filter:{act_f.column}{act_f.operator}'{act_f.value}'")
    else:
        # Check all expected filters are present
        for req_filter in expected.filters:
            if req_filter.column == "*":
                if not actual.filters:
                    missing.append(f"filter:{req_filter.operator}_{req_filter.value}")
                continue

            matched_filter = None
            for act_filter in actual.filters:
                if act_filter.column == req_filter.column or act_filter.column == "*":
                    matched_filter = act_filter
                    break

            if not matched_filter:
                missing.append(f"filter:{req_filter.column}{req_filter.operator}'{req_filter.value}'")
            else:
                if req_filter.value is not None and matched_filter.value is not None:
                    exp_val_str = str(req_filter.value).strip().lower()
                    act_val_str = str(matched_filter.value).strip().lower()
                    if exp_val_str != act_val_str and exp_val_str not in act_val_str and act_val_str not in exp_val_str:
                        altered.append(f"filter_value:{req_filter.column}:expected_{exp_val_str}_got_{act_val_str}")

        # Check actual does not contain unrequested filters
        if expected.filters:
            exp_filter_cols = {f.column.lower() for f in expected.filters if f.column != "*"}
            has_wildcard = any(f.column == "*" for f in expected.filters)
            for act_f in actual.filters:
                if act_f.column != "*" and act_f.column.lower() not in exp_filter_cols:
                    if has_wildcard and any(f.column == "*" and f.operator == act_f.operator for f in expected.filters):
                        continue
                    altered.append(f"spurious_filter:{act_f.column}{act_f.operator}'{act_f.value}'")

    # 4. Bidirectional Grouping Validation (Never drop GROUP BY & Never invent spurious GROUP BY)
    if not expected.group_by and actual.group_by:
        altered.append(f"spurious_group_by:{','.join(actual.group_by.columns)}")
    elif expected.group_by and not actual.group_by:
        missing.append(f"group_by:{','.join(expected.group_by.columns)}")
    elif expected.group_by and actual.group_by:
        exp_cols = set(c.lower() for c in expected.group_by.columns)
        act_cols = set(c.lower() for c in actual.group_by.columns)
        if not exp_cols.intersection(act_cols):
            has_fuzzy_match = any(ec in ac or ac in ec for ec in exp_cols for ac in act_cols)
            if not has_fuzzy_match:
                altered.append(f"group_by_columns:expected_{exp_cols}_got_{act_cols}")

    # 5. Bidirectional Aggregation & Measure Datatype Validation
    if not expected.aggregations and actual.aggregations:
        altered.append(f"spurious_aggregations:{','.join(a['func'] for a in actual.aggregations)}")
    elif expected.aggregations and not actual.aggregations:
        missing.append(f"aggregations:{','.join(a['func'] for a in expected.aggregations)}")
    elif expected.aggregations and actual.aggregations:
        for req_agg in expected.aggregations:
            req_func = req_agg["func"].upper()
            act_funcs = [a["func"].upper() for a in actual.aggregations]
            if req_func not in act_funcs:
                missing.append(f"aggregation:{req_func}")

    # Datatype safety: Disallow SUM, AVG, MIN, MAX on text/varchar columns
    for act_agg in actual.aggregations:
        func = act_agg["func"].upper()
        col = act_agg["column"].lower()
        if func in ("SUM", "AVG", "MIN", "MAX") and col in TEXT_COLUMNS:
            altered.append(f"invalid_measure_datatype:{func}({col})")

    # 6. Order By & Limit Preservation
    if expected.limit is not None:
        if actual.limit is None and expected.limit > 0:
            missing.append(f"limit:{expected.limit}")
        elif actual.limit is not None and actual.limit != expected.limit:
            altered.append(f"limit:expected_{expected.limit}_got_{actual.limit}")
    elif expected.limit is None and actual.limit is not None and not actual.order_by:
        altered.append(f"spurious_limit:{actual.limit}")

    if expected.order_by:
        if not actual.order_by:
            missing.append("order_by")
        else:
            exp_dir = expected.order_by[0].direction.upper()
            act_dir = actual.order_by[0].direction.upper()
            if exp_dir != act_dir:
                altered.append(f"order_by_direction:expected_{exp_dir}_got_{act_dir}")

    passed = len(missing) == 0 and len(altered) == 0
    return passed, missing, altered
