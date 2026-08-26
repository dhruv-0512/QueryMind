import re
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from app.services.constraint_extraction_service import (
    constraint_extraction_service,
    QueryConstraints,
    FilterConstraint,
    GroupByConstraint,
    OrderByConstraint,
    JoinConstraint,
)
from app.utils.constraint_validator import compare_constraints

logger = logging.getLogger(__name__)

class RagCompositionService:
    """
    RAG Composition Engine (Levels 3–8).
    Composes SQL by assembling structural facets (Joins, Filters, Group By, Rankings, Aggregates)
    from retrieved pattern examples and the live schema/FK-graph,
    strictly validated through the Hard AST Constraint Gate.
    """

    NUMERIC_TYPES = {
        "INTEGER", "BIGINT", "SMALLINT", "FLOAT", "DOUBLE",
        "REAL", "NUMERIC", "SERIAL", "DOUBLE PRECISION", "DECIMAL"
    }

    def select_complementary_examples(
        self,
        target_constraints: QueryConstraints,
        retrieved_examples: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Select the best retrieved examples covering individual constraint facets:
        'aggregation', 'filter', 'join', 'group_by', 'ranking'.
        """
        facet_examples: Dict[str, Dict[str, Any]] = {}
        if not retrieved_examples:
            return facet_examples

        for ex in retrieved_examples:
            ex_sql = ex.get("sql", "")
            if not ex_sql:
                continue

            ex_c = constraint_extraction_service.extract_sql_constraints(ex_sql)

            # Aggregation facet match
            if target_constraints.aggregations and "aggregation" not in facet_examples:
                if ex_c.aggregations:
                    target_func = target_constraints.aggregations[0]["func"].upper()
                    if any(a["func"].upper() == target_func for a in ex_c.aggregations):
                        facet_examples["aggregation"] = ex

            # Group By facet match
            if target_constraints.group_by and "group_by" not in facet_examples:
                if ex_c.group_by:
                    facet_examples["group_by"] = ex

            # Join facet match
            if (target_constraints.joins or len(target_constraints.tables) >= 2) and "join" not in facet_examples:
                if len(ex_c.tables) >= 2 or ex_c.joins:
                    facet_examples["join"] = ex

            # Filter facet match
            if target_constraints.filters and "filter" not in facet_examples:
                if ex_c.filters:
                    facet_examples["filter"] = ex

            # Ranking facet match
            if (target_constraints.limit or target_constraints.order_by) and "ranking" not in facet_examples:
                if ex_c.limit or ex_c.order_by:
                    facet_examples["ranking"] = ex

        return facet_examples

    def compose_sql(
        self,
        target_constraints: QueryConstraints,
        retrieved_examples: List[Dict[str, Any]],
        schema_context: str,
        question: Optional[str] = None,
        fk_graph: Optional[Dict[str, Any]] = None,
        live_values: Optional[Dict[str, List[str]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt to compose SQL for the target constraints using retrieved examples and schema graph.
        Returns a dict with {"sql", "explanation", "confidence", "rag_mode", "facets_used"} or None.
        """
        # Parse schema metadata
        tables_meta, sample_values = constraint_extraction_service._parse_schema_metadata(schema_context)
        if live_values:
            sample_values.update(live_values)

        # 0a. RAG-Assisted Table Grounding for Paraphrases:
        # If target_constraints.tables is empty, check if top retrieved examples have grounded tables
        # that exist in the active schema and have high similarity.
        if not target_constraints.tables and retrieved_examples:
            for ex in retrieved_examples[:3]:
                ex_c = constraint_extraction_service.extract_sql_constraints(ex.get("sql", ""))
                candidate_tables = [t for t in ex_c.tables if t in tables_meta]
                if candidate_tables:
                    for tbl in candidate_tables:
                        target_constraints.tables.add(tbl)
                    logger.info(f"RAG-Assisted Table Grounding: Adopted table(s) {candidate_tables} from example '{ex.get('question')}'")
                    break

        if not target_constraints.tables:
            return None

        # 0b. RAG-Assisted Grouping Inference:
        # Only infer grouping if question has an explicit non-aggregated dimension column requested alongside aggregations
        agg_cols = {a.get("column", "").lower() for a in target_constraints.aggregations}
        non_agg_dim_cols = [c for c in target_constraints.columns if c.lower() not in agg_cols and c != "*"]
        has_grouping_intent = bool(non_agg_dim_cols and target_constraints.aggregations)
        if not target_constraints.group_by and has_grouping_intent and retrieved_examples:
            for ex in retrieved_examples[:3]:
                ex_c = constraint_extraction_service.extract_sql_constraints(ex.get("sql", ""))
                if ex_c.group_by and ex_c.group_by.columns:
                    for grp_col in ex_c.group_by.columns:
                        for tbl in target_constraints.tables:
                            if grp_col in tables_meta.get(tbl, {}):
                                target_constraints.group_by = GroupByConstraint(columns=[grp_col])
                                logger.info(f"RAG-Assisted Grouping: Inferred group_by: {grp_col} from example '{ex.get('question')}'")
                                break
                        if target_constraints.group_by:
                            break

        # Level 8 check: Conservative safety envelope
        # Fall back to LLM for subqueries, unresolved facets, or multi-hop joins (>2 tables)
        if target_constraints.has_subquery or target_constraints.unresolved_facets or len(target_constraints.tables) > 2:
            logger.info("Composition skipped: Query contains subqueries or multi-hop joins (>2 tables) -> Fallback to LLM")
            return None

        # Select facet examples
        facet_examples = self.select_complementary_examples(target_constraints, retrieved_examples)

        # 1. Build Tables and Joins
        table_list = list(target_constraints.tables)
        if len(table_list) > 1:
            if target_constraints.group_by and target_constraints.group_by.columns:
                grp_col = target_constraints.group_by.columns[0]
                for tbl in table_list:
                    if grp_col in tables_meta.get(tbl, {}):
                        table_list.remove(tbl)
                        table_list.insert(0, tbl)
                        break

        primary_table = table_list[0]
        join_clauses: List[str] = []
        aliases: Dict[str, str] = {primary_table: primary_table[0]}

        if len(table_list) > 1:
            used_aliases = {aliases[primary_table]}
            for tbl in table_list[1:]:
                a = tbl[0]
                if a in used_aliases:
                    a = f"{tbl[:2]}"
                used_aliases.add(a)
                aliases[tbl] = a

            joined_tables = {primary_table}
            for tbl in table_list[1:]:
                p_cols = set(tables_meta.get(primary_table, {}).keys())
                t_cols = set(tables_meta.get(tbl, {}).keys())
                common_keys = [c for c in p_cols.intersection(t_cols) if c.endswith(("_id", "_key", "_pk", "_fk")) or c == "id"]

                join_type = "INNER"
                if target_constraints.joins:
                    for j in target_constraints.joins:
                        if j.join_type == "LEFT" and (j.left_table == primary_table or j.right_table == tbl):
                            join_type = "LEFT"

                if common_keys:
                    join_key = common_keys[0]
                    join_clauses.append(
                        f'{join_type} JOIN "{tbl}" {aliases[tbl]} ON {aliases[primary_table]}."{join_key}" = {aliases[tbl]}."{join_key}"'
                    )
                    joined_tables.add(tbl)
                elif fk_graph and primary_table in fk_graph:
                    for edge in fk_graph.get(primary_table, []):
                        if edge.get("target_table", "").lower() == tbl:
                            src_col = edge.get("source_column", "").lower()
                            tgt_col = edge.get("target_column", "").lower()
                            join_clauses.append(
                                f'{join_type} JOIN "{tbl}" {aliases[tbl]} ON {aliases[primary_table]}."{src_col}" = {aliases[tbl]}."{tgt_col}"'
                            )
                            joined_tables.add(tbl)
                            break

            if len(joined_tables) < len(table_list):
                logger.info("Composition skipped: Cannot resolve join path across tables -> Fallback to LLM")
                return None

        # 2. Build SELECT Projection
        select_parts: List[str] = []

        # A. Grouping projection
        if target_constraints.group_by:
            for g_col in target_constraints.group_by.columns:
                owner_tbl = None
                for t in table_list:
                    if g_col in tables_meta.get(t, {}):
                        owner_tbl = t
                        break
                prefix = f'{aliases[owner_tbl]}.' if owner_tbl and len(table_list) > 1 else ''
                select_parts.append(f'{prefix}"{g_col}"')

        # B. Aggregation projection
        NUMERIC_KEYWORDS = ("INT", "NUMERIC", "DECIMAL", "FLOAT", "REAL", "DOUBLE", "BIGINT", "MONEY", "NUMBER")
        TEXT_COLUMNS = {"name", "city", "category", "status", "product_name", "title", "description", "email"}

        if target_constraints.aggregations:
            for agg in target_constraints.aggregations:
                func = agg["func"].upper()
                c_name = agg["column"]
                if func == "COUNT":
                    select_parts.append('COUNT(*)')
                elif c_name == "*":
                    # Find a numeric measure column in any of the detected tables
                    resolved = False
                    for t in table_list:
                        t_cols = tables_meta.get(t, {})
                        # Only pick numeric measure columns
                        num_meas = [
                            c for c, c_type in t_cols.items()
                            if (any(k in c_type for k in NUMERIC_KEYWORDS) or c in ("amount", "price", "cost", "quantity", "unit_price"))
                            and not c.endswith(("_id", "_key", "_pk", "_fk"))
                            and c != "id"
                        ]
                        if num_meas:
                            prefix = f'{aliases[t]}.' if len(table_list) > 1 else ''
                            select_parts.append(f'{func}({prefix}"{num_meas[0]}")')
                            resolved = True
                            break
                    if not resolved:
                        logger.info(f"Composition skipped: Cannot resolve numeric measure for {func}(*) -> Fallback to LLM")
                        return None
                else:
                    # Validate the column is numeric in the schema before applying aggregation
                    if func in ("SUM", "AVG", "MIN", "MAX") and c_name in TEXT_COLUMNS:
                        logger.info(f"Composition skipped: {func}({c_name}) on text column -> Fallback to LLM")
                        return None
                    owner_tbl = None
                    for t in table_list:
                        if c_name in tables_meta.get(t, {}):
                            # Verify column is numeric
                            col_type = tables_meta[t].get(c_name, "")
                            is_num = (any(k in col_type for k in NUMERIC_KEYWORDS) or c_name in ("amount", "price", "cost", "quantity", "unit_price"))
                            if func in ("SUM", "AVG", "MIN", "MAX") and not is_num:
                                logger.info(f"Composition skipped: {func}({c_name}) is non-numeric column (type={col_type}) -> Fallback to LLM")
                                return None
                            owner_tbl = t
                            break
                    if owner_tbl is None and func in ("SUM", "AVG", "MIN", "MAX"):
                        logger.info(f"Composition skipped: {func}({c_name}) column not found in schema -> Fallback to LLM")
                        return None
                    prefix = f'{aliases[owner_tbl]}.' if owner_tbl and len(table_list) > 1 else ''
                    select_parts.append(f'{func}({prefix}"{c_name}")')

        # C. Explicit Column-Level Entity Projections (e.g. order_id, name across joined tables)
        if not target_constraints.aggregations and target_constraints.columns:
            filter_cols = {f.column.lower() for f in target_constraints.filters if f.column and f.column != "*"}
            order_by_cols = {ob.column.lower() for ob in target_constraints.order_by} if target_constraints.order_by else set()
            predicate_cols = filter_cols | order_by_cols
            is_pure_sort_query = (
                (set(target_constraints.columns) == order_by_cols or "*" in order_by_cols)
                and len(table_list) == 1
                and bool(target_constraints.order_by)
            )
            is_pure_entity_filter_query = (len(table_list) == 1 and target_constraints.columns.issubset(predicate_cols))
            if not is_pure_sort_query and not is_pure_entity_filter_query:
                def _col_sort_key(c: str) -> int:
                    if question:
                        q_c = question.lower()
                        pos = q_c.find(c.replace("_", " "))
                        if pos == -1:
                            pos = q_c.find(c)
                        if pos != -1:
                            return pos
                    if c in ("name", "customer_name", "product_name", "city", "category"):
                        return 0
                    elif c.endswith("_id") or c == "id":
                        return 1
                    return 2

                ordered_cols = sorted(target_constraints.columns, key=_col_sort_key)
                for req_col in ordered_cols:
                    owner_tbl = None
                    for t in table_list:
                        if req_col in tables_meta.get(t, {}):
                            owner_tbl = t
                            break
                    if owner_tbl:
                        prefix = f'{aliases[owner_tbl]}.' if len(table_list) > 1 else ''
                        col_proj = f'{prefix}"{req_col}"'
                        if col_proj not in select_parts:
                            select_parts.append(col_proj)

        if not select_parts:
            # Entity query projection without explicit columns
            if len(table_list) > 1:
                # If multi-table query with no specific columns requested, do not emit bare SELECT *
                logger.info("Composition skipped: Multi-table query with no specific column projection -> Fallback to LLM")
                return None
            else:
                select_parts.append('*')

        select_sql = ", ".join(select_parts)

        # 3. Build FROM clause
        from_sql = f'"{primary_table}" {aliases[primary_table]}' if len(table_list) > 1 else f'"{primary_table}"'
        if join_clauses:
            from_sql += " " + " ".join(join_clauses)

        # 4. Build WHERE clause
        where_parts: List[str] = []
        wildcard_flts = [f for f in target_constraints.filters if f.column == "*"]
        if len(wildcard_flts) > 1:
            logger.info("Composition skipped: Multiple wildcard filters -> Fallback to LLM")
            return None

        for flt in target_constraints.filters:
            col = flt.column
            val = flt.value
            op = flt.operator

            # Find table owner
            owner_tbl = flt.table
            if not owner_tbl:
                for t, cols in tables_meta.items():
                    if t in target_constraints.tables and col in cols:
                        owner_tbl = t
                        break

            prefix = f'{aliases[owner_tbl]}.' if owner_tbl and len(table_list) > 1 else ''

            if col == "*":
                # Find suitable filter column
                candidate_cols = []
                for t in table_list:
                    for c in tables_meta.get(t, {}).keys():
                        if isinstance(val, (int, float)) and ("amount" in c or "price" in c or "cost" in c or "stock" in c or "quantity" in c):
                            candidate_cols.append((t, c))
                        elif isinstance(val, str) and ("date" in c or "time" in c):
                            candidate_cols.append((t, c))
                if candidate_cols:
                    t_cand, c_cand = candidate_cols[0]
                    pref = f'{aliases[t_cand]}.' if len(table_list) > 1 else ''
                    if isinstance(val, (int, float)):
                        where_parts.append(f'{pref}"{c_cand}" {op} {val}')
                    elif isinstance(val, str):
                        where_parts.append(f'{pref}"{c_cand}" {op} \'{val}\'')
            else:
                if isinstance(val, (int, float)):
                    where_parts.append(f'{prefix}"{col}" {op} {val}')
                elif isinstance(val, list):
                    val_str = ", ".join(f"'{v}'" for v in val)
                    where_parts.append(f'{prefix}"{col}" {op} ({val_str})')
                elif val is not None:
                    where_parts.append(f'{prefix}"{col}" {op} \'{val}\'')
                else:
                    where_parts.append(f'{prefix}"{col}" {op}')

        where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # 5. Build GROUP BY and HAVING
        group_sql = ""
        if target_constraints.group_by:
            grp_cols_sql = []
            for g_col in target_constraints.group_by.columns:
                owner_tbl = None
                for t, cols in tables_meta.items():
                    if t in target_constraints.tables and g_col in cols:
                        owner_tbl = t
                        break
                prefix = f'{aliases[owner_tbl]}.' if owner_tbl and len(table_list) > 1 else ''
                grp_cols_sql.append(f'{prefix}"{g_col}"')
            group_sql = " GROUP BY " + ", ".join(grp_cols_sql)

            if target_constraints.group_by.having_conditions:
                group_sql += " HAVING " + " AND ".join(target_constraints.group_by.having_conditions)

        # 6. Build ORDER BY and LIMIT
        order_sql = ""
        if target_constraints.order_by:
            ord_parts = []
            for ord_item in target_constraints.order_by:
                col = ord_item.column
                direction = ord_item.direction
                if target_constraints.aggregations:
                    # If ranking an aggregated query, order by the aggregate expression
                    agg = target_constraints.aggregations[0]
                    agg_func = agg["func"].upper()
                    agg_c = agg["column"].lower()
                    if agg_c == "*":
                        p_cols = list(tables_meta.get(primary_table, {}).keys())
                        meas_cols = [c for c in p_cols if c in ("amount", "quantity", "unit_price", "price", "total")]
                        agg_c = meas_cols[0] if meas_cols else p_cols[0]
                    owner_tbl = None
                    for t in table_list:
                        if agg_c in tables_meta.get(t, {}):
                            owner_tbl = t
                            break
                    prefix = f'{aliases[owner_tbl]}.' if owner_tbl and len(table_list) > 1 else ''
                    ord_parts.append(f'{agg_func}({prefix}"{agg_c}") {direction}')
                elif col == "*":
                    p_cols = list(tables_meta.get(primary_table, {}).keys())
                    # Match explicit columns present in question
                    meas = [c for c in p_cols if c.lower() in [tc.lower() for tc in target_constraints.columns]]
                    if not meas:
                        meas = [c for c in p_cols if c in ("amount", "price", "cost", "order_date", "date", "quantity")]
                    if not meas:
                        meas = [c for c in p_cols if not c.endswith(("_id", "_key")) and c != "id"]
                    if meas:
                        prefix = f'{aliases[primary_table]}.' if len(table_list) > 1 else ''
                        ord_parts.append(f'{prefix}"{meas[0]}" {direction}')
                else:
                    owner_tbl = None
                    for t in table_list:
                        if col in tables_meta.get(t, {}):
                            owner_tbl = t
                            break
                    prefix = f'{aliases[owner_tbl]}.' if owner_tbl and len(table_list) > 1 else ''
                    ord_parts.append(f'{prefix}"{col}" {direction}')
            if ord_parts:
                order_sql = " ORDER BY " + ", ".join(ord_parts)

        limit_sql = f" LIMIT {target_constraints.limit}" if target_constraints.limit else ""

        # Assembled SQL
        composed_sql = f"SELECT {select_sql} FROM {from_sql}{where_sql}{group_sql}{order_sql}{limit_sql};".strip()

        # ── 7. Mandatory Hard AST Constraint Gate ─────────────────────
        sql_constraints = constraint_extraction_service.extract_sql_constraints(composed_sql)
        passed, missing, altered = compare_constraints(target_constraints, sql_constraints)

        if not passed:
            logger.warning(
                f"Composed SQL rejected by AST constraint validator: missing={missing}, altered={altered}. SQL: {composed_sql}"
            )
            return None

        logger.info(f"Composed SQL successfully passed AST constraint gate: {composed_sql}")
        return {
            "sql": composed_sql,
            "explanation": f"Composed SQL directly from retrieved schema facets ({', '.join(facet_examples.keys()) or 'schema-graph'}) with verified constraint preservation.",
            "confidence": 0.95,
            "rag_mode": "rag_composition",
            "facets_used": list(facet_examples.keys()),
        }


rag_composition_service = RagCompositionService()
