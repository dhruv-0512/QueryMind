import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
import sqlglot
from sqlglot import exp

logger = logging.getLogger(__name__)

@dataclass
class FilterConstraint:
    column: str
    table: Optional[str] = None
    operator: str = "="  # '=', '>', '<', '>=', '<=', '!=', 'LIKE', 'ILIKE', 'IN', 'NOT IN', 'IS NULL', 'IS NOT NULL'
    value: Any = None
    is_negated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column": self.column,
            "table": self.table,
            "operator": self.operator,
            "value": str(self.value) if self.value is not None else None,
            "is_negated": self.is_negated,
        }

@dataclass
class JoinConstraint:
    left_table: str
    right_table: str
    join_type: str = "INNER"  # 'INNER', 'LEFT', 'RIGHT', 'FULL'
    on_conditions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "left_table": self.left_table,
            "right_table": self.right_table,
            "join_type": self.join_type,
            "on_conditions": self.on_conditions,
        }

@dataclass
class GroupByConstraint:
    columns: List[str] = field(default_factory=list)
    having_conditions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "columns": self.columns,
            "having_conditions": self.having_conditions,
        }

@dataclass
class OrderByConstraint:
    column: str
    direction: str = "ASC"  # 'ASC', 'DESC'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column": self.column,
            "direction": self.direction,
        }

@dataclass
class QueryConstraints:
    tables: Set[str] = field(default_factory=set)
    columns: Set[str] = field(default_factory=set)
    aggregations: List[Dict[str, str]] = field(default_factory=list)  # e.g. [{"func": "AVG", "column": "amount"}]
    filters: List[FilterConstraint] = field(default_factory=list)
    joins: List[JoinConstraint] = field(default_factory=list)
    group_by: Optional[GroupByConstraint] = None
    order_by: List[OrderByConstraint] = field(default_factory=list)
    limit: Optional[int] = None
    is_distinct: bool = False
    has_subquery: bool = False
    confidence: float = 1.0
    unresolved_facets: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tables": sorted(list(self.tables)),
            "columns": sorted(list(self.columns)),
            "aggregations": self.aggregations,
            "filters": [f.to_dict() for f in self.filters],
            "joins": [j.to_dict() for j in self.joins],
            "group_by": self.group_by.to_dict() if self.group_by else None,
            "order_by": [o.to_dict() for o in self.order_by],
            "limit": self.limit,
            "is_distinct": self.is_distinct,
            "has_subquery": self.has_subquery,
            "confidence": self.confidence,
            "unresolved_facets": self.unresolved_facets,
        }


class ConstraintExtractionService:
    """Service to extract structured semantic constraints from SQL ASTs and natural language questions."""

    NUMERIC_TYPES = {
        "INTEGER", "BIGINT", "SMALLINT", "FLOAT", "DOUBLE",
        "REAL", "NUMERIC", "SERIAL", "DOUBLE PRECISION", "DECIMAL"
    }

    # ── 1. SQL AST Constraint Extraction ──────────────────────────────
    def extract_sql_constraints(self, sql: str) -> QueryConstraints:
        """Parse SQL query using sqlglot and extract all structural constraints."""
        constraints = QueryConstraints()
        if not sql or not sql.strip():
            return constraints

        clean_sql = sql.strip().rstrip(";")
        try:
            parsed = sqlglot.parse_one(clean_sql, read="postgres")
        except Exception:
            try:
                parsed = sqlglot.parse_one(clean_sql)
            except Exception as e:
                logger.warning(f"Failed to parse SQL with sqlglot: {e}")
                return constraints

        # Tables
        for table in parsed.find_all(exp.Table):
            t_name = table.name.lower()
            if t_name:
                constraints.tables.add(t_name)

        # Columns
        for col in parsed.find_all(exp.Column):
            c_name = col.name.lower()
            if c_name and c_name != "*":
                constraints.columns.add(c_name)

        # Aggregations
        for node in parsed.walk():
            if isinstance(node, (exp.Count, exp.Avg, exp.Sum, exp.Min, exp.Max)):
                func_name = node.key.upper()
                arg = node.this
                col_name = "*"
                if isinstance(arg, exp.Column):
                    col_name = arg.name.lower()
                elif isinstance(arg, exp.Star):
                    col_name = "*"
                constraints.aggregations.append({
                    "func": func_name,
                    "column": col_name
                })
            elif isinstance(node, exp.Anonymous):
                func_name = node.name.upper()
                if func_name in ("COUNT", "AVG", "SUM", "MIN", "MAX"):
                    arg = node.expressions[0] if node.expressions else None
                    col_name = "*"
                    if isinstance(arg, exp.Column):
                        col_name = arg.name.lower()
                    constraints.aggregations.append({
                        "func": func_name,
                        "column": col_name
                    })

        # Distinct
        if parsed.find(exp.Distinct):
            constraints.is_distinct = True

        # Joins
        for join in parsed.find_all(exp.Join):
            join_type = "INNER"
            if join.args.get("kind"):
                join_type = str(join.args.get("kind")).upper()
            if join.args.get("side"):
                join_type = f"{str(join.args.get('side')).upper()} {join_type}".strip()

            right_table = ""
            if isinstance(join.this, exp.Table):
                right_table = join.this.name.lower()

            on_conds = []
            if join.args.get("on"):
                on_conds.append(join.args.get("on").sql())

            # Find from table if available
            from_table = ""
            from_node = parsed.find(exp.From)
            if from_node and isinstance(from_node.this, exp.Table):
                from_table = from_node.this.name.lower()

            constraints.joins.append(JoinConstraint(
                left_table=from_table or "unknown",
                right_table=right_table or "unknown",
                join_type=join_type,
                on_conditions=on_conds
            ))

        # Where Filters
        where_node = parsed.find(exp.Where)
        if where_node:
            self._extract_where_filters(where_node.this, constraints.filters)

        # Group By & Having
        group_node = parsed.find(exp.Group)
        if group_node:
            grp_cols = []
            for g_col in group_node.expressions:
                if isinstance(g_col, exp.Column):
                    grp_cols.append(g_col.name.lower())
                else:
                    grp_cols.append(g_col.sql().lower())

            having_conds = []
            having_node = parsed.find(exp.Having)
            if having_node:
                having_conds.append(having_node.this.sql())

            constraints.group_by = GroupByConstraint(
                columns=grp_cols,
                having_conditions=having_conds
            )

        # Order By
        order_node = parsed.find(exp.Order)
        if order_node:
            for ordered in order_node.expressions:
                col_name = ""
                direction = "ASC"
                if isinstance(ordered, exp.Ordered):
                    if isinstance(ordered.this, exp.Column):
                        col_name = ordered.this.name.lower()
                    else:
                        col_name = ordered.this.sql().lower()
                    if ordered.args.get("desc"):
                        direction = "DESC"
                elif isinstance(ordered, exp.Column):
                    col_name = ordered.name.lower()
                if col_name:
                    constraints.order_by.append(OrderByConstraint(
                        column=col_name,
                        direction=direction
                    ))

        # Limit
        limit_node = parsed.find(exp.Limit)
        if limit_node and limit_node.expression:
            try:
                constraints.limit = int(limit_node.expression.sql())
            except Exception:
                pass

        # Subqueries
        for select_node in parsed.find_all(exp.Select):
            if select_node != parsed:
                constraints.has_subquery = True
                break

        return constraints

    def _extract_where_filters(self, node: exp.Expression, filters_list: List[FilterConstraint]):
        """Recursively inspect WHERE clause expressions to extract FilterConstraint objects."""
        if not node:
            return

        if isinstance(node, exp.And):
            self._extract_where_filters(node.left, filters_list)
            self._extract_where_filters(node.right, filters_list)
            return

        if isinstance(node, (exp.EQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.NEQ, exp.Like, exp.ILike)):
            col_name = ""
            tbl_name = None
            if isinstance(node.left, exp.Column):
                col_name = node.left.name.lower()
                if node.left.table:
                    tbl_name = node.left.table.lower()
            elif isinstance(node.right, exp.Column):
                col_name = node.right.name.lower()
                if node.right.table:
                    tbl_name = node.right.table.lower()

            op_map = {
                exp.EQ: "=", exp.GT: ">", exp.GTE: ">=",
                exp.LT: "<", exp.LTE: "<=", exp.NEQ: "!=",
                exp.Like: "LIKE", exp.ILike: "ILIKE"
            }
            op_symbol = op_map.get(type(node), "=")
            val = node.right.sql() if isinstance(node.left, exp.Column) else node.left.sql()
            val = val.strip("'\"")

            if col_name:
                filters_list.append(FilterConstraint(
                    column=col_name,
                    table=tbl_name,
                    operator=op_symbol,
                    value=val
                ))
            return

        if isinstance(node, (exp.In, exp.NotIn)):
            col_name = ""
            if isinstance(node.this, exp.Column):
                col_name = node.this.name.lower()
            op = "NOT IN" if isinstance(node, exp.NotIn) or node.args.get("is_not") else "IN"
            val = [x.sql().strip("'\"") for x in node.expressions] if node.expressions else []
            if col_name:
                filters_list.append(FilterConstraint(
                    column=col_name,
                    operator=op,
                    value=val
                ))
            return

        # Generic condition fallback
        sql_cond = node.sql()
        filters_list.append(FilterConstraint(
            column="*",
            operator="EXPR",
            value=sql_cond
        ))

    # ── 2. Natural Language Question Constraint Extraction ─────────────
    def extract_query_constraints(
        self,
        question: str,
        schema_context: str,
        live_values: Optional[Dict[str, List[str]]] = None
    ) -> QueryConstraints:
        """Extract expected structural constraints from user natural language query and live schema context."""
        constraints = QueryConstraints()
        q_clean = question.strip().lower()

        # Extract schema tables and column metadata
        tables_meta, sample_values = self._parse_schema_metadata(schema_context)
        if live_values:
            sample_values.update(live_values)

        # 1. Detect Tables Mentioned (including multi-word phrases & domain aliases)
        table_aliases_map = {
            "order item": "order_items",
            "order items": "order_items",
            "item": "order_items",
            "items": "order_items",
            "customer": "customers",
            "customers": "customers",
            "order": "orders",
            "orders": "orders",
            "product": "products",
            "products": "products",
            "purchase record": "orders",
            "purchase records": "orders",
            "purchase": "orders",
            "purchases": "orders",
            "sale": "orders",
            "sales": "orders",
        }
        for phrase, tbl_target in table_aliases_map.items():
            if tbl_target in tables_meta and re.search(rf'\b{re.escape(phrase)}\b', q_clean):
                constraints.tables.add(tbl_target)

        for tbl in tables_meta.keys():
            tbl_low = tbl.lower()
            if re.search(rf'\b{re.escape(tbl_low)}(?:s|es)?\b', q_clean):
                constraints.tables.add(tbl_low)

        # 2. Detect Columns Mentioned (including underscore and multi-word variations)
        all_cols_map: Dict[str, str] = {}
        col_to_owners: Dict[str, List[str]] = {}
        for tbl, cols in tables_meta.items():
            for c in cols.keys():
                c_low = c.lower()
                col_to_owners.setdefault(c_low, []).append(tbl.lower())
                if c_low not in all_cols_map or c_low.startswith(tbl.lower().rstrip('s')):
                    all_cols_map[c_low] = tbl.lower()

        for c_low, owners in col_to_owners.items():
            matched = False
            if c_low.endswith("y"):
                stem = c_low[:-1]
                pattern = rf'\b(?:{re.escape(stem)}ies|{re.escape(c_low)}(?:s|es)?)\b'
            else:
                pattern = rf'\b{re.escape(c_low)}(?:s|es)?\b'

            if re.search(pattern, q_clean):
                matched = True
            else:
                c_words = c_low.replace("_", " ")
                if c_words != c_low:
                    if c_words.endswith("y"):
                        stem_w = c_words[:-1]
                        pattern_w = rf'\b(?:{re.escape(stem_w)}ies|{re.escape(c_words)}(?:s|es)?)\b'
                    else:
                        pattern_w = rf'\b{re.escape(c_words)}(?:s|es)?\b'
                    if re.search(pattern_w, q_clean):
                        matched = True

            if matched:
                is_entity_query = bool(re.search(r'\b(find|show|list|get|retrieve|display)\s+(?:all\s+)?(?:the\s+)?(?:orders?|customers?|products?|items?|records?)\b', q_clean))
                has_explicit_projection = bool(re.search(r'\b(?:names?|cities|city|order_ids?|product_names?|ids?|status(?:es)?|categories|category)\s+(?:and|with|of)\b|\b(?:names?|cities|city|order_ids?|product_names?|ids?|status(?:es)?|categories|category)\s+of\b', q_clean))
                in_predicate = bool(re.search(rf'\b{re.escape(c_low)}\s*(?:>|<|=|is|greater|less|under|over|above|below|between|in|\bwith\s+{re.escape(c_low)})\b', q_clean))

                # For pure entity retrieval queries, predicate-only columns should not become projection columns
                if not (is_entity_query and in_predicate and not has_explicit_projection):
                    constraints.columns.add(c_low)

                if len(owners) == 1:
                    constraints.tables.add(owners[0])
                else:
                    pref_owner = None
                    for o in owners:
                        if o in constraints.tables:
                            pref_owner = o
                            break
                        if c_low.startswith(o.rstrip('s')):
                            pref_owner = o
                    if not pref_owner:
                        pref_owner = owners[0]
                    constraints.tables.add(pref_owner)

        # Specific semantic phrases for names
        if re.search(r'\b(customer\s+name|name\s+of\s+the\s+customer|name\s+of\s+customer)\b', q_clean):
            constraints.columns.add("name")
            constraints.tables.add("customers")
        elif re.search(r'\b(product\s+name|name\s+of\s+the\s+product|name\s+of\s+product)\b', q_clean):
            constraints.columns.add("product_name")
            constraints.tables.add("products")

        # Temporal / Date range expressions that cannot be deterministically translated into exact filters -> Safety Gate
        temporal_pattern = r'\b(in\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+\d{4})?|during\s+[a-z]+|last\s+(?:year|month|week)|this\s+(?:month|year|week)|between\s+[a-zA-Z0-9\s]+\s+and\s+[a-zA-Z0-9\s]+|q[1-4]\s+\d{4}|in\s+20\d{2}|in\s+19\d{2}|placed\s+in\s+[a-zA-Z]+|signed\s+up\s+in\s+[a-zA-Z]+)\b'
        if re.search(temporal_pattern, q_clean):
            constraints.has_subquery = True
            constraints.unresolved_facets.append("temporal_constraint")

        # Check for complex comparison subqueries (e.g. "higher than the average", "above average", "never ordered", "distinct")
        if re.search(r'\b(above\s+(?:the\s+)?average|higher\s+than\s+(?:the\s+)?average|greater\s+than\s+(?:the\s+)?average|more\s+than\s+(?:the\s+)?average|below\s+(?:the\s+)?average|lower\s+than\s+(?:the\s+)?average|never\s+placed|never\s+ordered|never\s+been|not\s+in|percentage|percent|relative\s+to|ratio|highest\s+average|lowest\s+average|distinct)\b', q_clean):
            constraints.has_subquery = True
            constraints.unresolved_facets.append("subquery_comparison")

        # Detect spending superlative phrases (e.g. "spent the most", "highest spending", "biggest spender", "top spender")
        spending_superlative = re.search(r'\b(spent\s+the\s+most|highest\s+spending|greatest\s+spending|biggest\s+spender|top\s+spender|most\s+money\s+spent|spent\s+most)\b', q_clean)
        if spending_superlative:
            constraints.tables.add("customers")
            constraints.tables.add("orders")
            constraints.columns.add("name" if "name" in all_cols_map else "customer_id")
            constraints.aggregations.append({"func": "SUM", "column": "amount"})
            constraints.group_by = GroupByConstraint(columns=["name" if "name" in all_cols_map else "customer_id"])
            constraints.order_by.append(OrderByConstraint(column="amount", direction="DESC"))
            constraints.limit = 1

        # Detect top entities by spending (e.g. "top 3 customers by total spending", "top 3 customers by total spending with their cities")
        top_spending_match = re.search(r'\btop\s+(\d+)?\s*(?:customers|users|people|clients)?\s*by\s+(?:total\s+)?spending(?:\s+with\s+their\s+(?:cities|city))?\b', q_clean)
        if top_spending_match:
            m_lim = re.search(r'\btop\s+(\d+)\b', q_clean)
            lim_val = int(m_lim.group(1)) if m_lim else 3
            constraints.tables.add("customers")
            constraints.tables.add("orders")
            constraints.columns.add("name" if "name" in all_cols_map else "customer_id")
            if re.search(r'\b(?:cities|city)\b', q_clean):
                constraints.columns.add("city")
                constraints.group_by = GroupByConstraint(columns=["name" if "name" in all_cols_map else "customer_id", "city"])
            else:
                constraints.group_by = GroupByConstraint(columns=["name" if "name" in all_cols_map else "customer_id"])
            constraints.aggregations.append({"func": "SUM", "column": "amount"})
            constraints.order_by.append(OrderByConstraint(column="amount", direction="DESC"))
            constraints.limit = lim_val

        # Detect best-selling / most sold products
        if re.search(r'\b(best[- ]selling|most\s+sold|highest\s+selling|top\s+selling)\b', q_clean):
            m_lim = re.search(r'\btop\s+(\d+)\b', q_clean)
            lim_val = int(m_lim.group(1)) if m_lim else 1
            constraints.tables.add("products")
            constraints.tables.add("order_items")
            constraints.columns.add("product_name" if "product_name" in all_cols_map else "product_id")
            constraints.aggregations.append({"func": "SUM", "column": "quantity"})
            constraints.group_by = GroupByConstraint(columns=["product_name" if "product_name" in all_cols_map else "product_id"])
            constraints.order_by.append(OrderByConstraint(column="quantity", direction="DESC"))
            constraints.limit = lim_val

        if not constraints.has_subquery and not spending_superlative:
            if re.search(r'\b(count|how\s+many|number\s+of|total\s+(?:number|count))\b', q_clean):
                constraints.aggregations.append({"func": "COUNT", "column": "*"})
            elif re.search(r'\b(average|avg|mean)\b', q_clean):
                target_col = self._resolve_target_column(q_clean, constraints.tables, tables_meta, "avg")
                constraints.aggregations.append({"func": "AVG", "column": target_col or "*"})
            elif re.search(r'\b(total|sum|grand\s+total|overall\s+(?:amount|value|revenue|spend|cost)|spending|spend|revenue|sales)\b', q_clean) and not re.search(r'\b(total\s+(?:number|count)\s+of|count)\b', q_clean):
                target_col = self._resolve_target_column(q_clean, constraints.tables, tables_meta, "sum")
                if target_col is None and re.search(r'\b(spending|spend|revenue|sales)\b', q_clean):
                    constraints.unresolved_facets.append("unresolved_spending_measure")
                constraints.aggregations.append({"func": "SUM", "column": target_col or "*"})
            elif re.search(r'\b(minimum|min|lowest|smallest)\b', q_clean) and not re.search(r'\b\d+\s+(lowest|smallest)\b', q_clean):
                target_col = self._resolve_target_column(q_clean, constraints.tables, tables_meta, "min")
                constraints.aggregations.append({"func": "MIN", "column": target_col or "*"})
            elif re.search(r'\b(maximum|max|highest|largest|greatest)\b', q_clean) and not re.search(r'\b\d+\s+(highest|largest)\b', q_clean):
                target_col = self._resolve_target_column(q_clean, constraints.tables, tables_meta, "max")
                constraints.aggregations.append({"func": "MAX", "column": target_col or "*"})

        # 4. Detect Filter Constraints (Exact word-boundary literal matching)
        for col_name, vals in sample_values.items():
            matched_col_val = False
            for val in vals:
                val_low = str(val).lower()
                if re.search(rf'\b{re.escape(val_low)}\b', q_clean):
                    tbl = all_cols_map.get(col_name.lower())
                    constraints.filters.append(FilterConstraint(
                        column=col_name.lower(),
                        table=tbl,
                        operator="=",
                        value=val
                    ))
                    matched_col_val = True
                    if tbl:
                        constraints.tables.add(tbl)

            # Check status domain synonyms if not directly matched
            if not matched_col_val and col_name.lower() == "status":
                tbl = all_cols_map.get("status", "orders")
                if re.search(r'\b(completed|delivered|finished)\b', q_clean):
                    constraints.filters.append(FilterConstraint(column="status", table=tbl, operator="=", value="delivered"))
                    constraints.tables.add(tbl)
                elif re.search(r'\b(cancelled|canceled)\b', q_clean):
                    constraints.filters.append(FilterConstraint(column="status", table=tbl, operator="=", value="cancelled"))
                    constraints.tables.add(tbl)
                elif re.search(r'\b(processing|in\s+process|pending)\b', q_clean):
                    constraints.filters.append(FilterConstraint(column="status", table=tbl, operator="=", value="processing"))
                    constraints.tables.add(tbl)
                elif re.search(r'\b(shipped|dispatched)\b', q_clean):
                    constraints.filters.append(FilterConstraint(column="status", table=tbl, operator="=", value="shipped"))
                    constraints.tables.add(tbl)

        # Check for named entity filters (e.g. "Alice", "Bob")
        name_match = re.search(r'\b(?:placed\s+by|for|by)\s+([A-Z][a-z]+)\b', question)
        if name_match:
            name_val = name_match.group(1)
            if name_val.lower() not in ("orders", "customers", "products", "items", "amount", "city", "status", "category"):
                tbl = all_cols_map.get("name", "customers")
                constraints.filters.append(FilterConstraint(column="name", table=tbl, operator="=", value=name_val))
                constraints.tables.add(tbl)

        # Detect aggregate threshold patterns (e.g. "total spending greater than 1000", "spending > 1000", "total amount exceeding 500")
        if re.search(r'\b(?:total\s+spending|total\s+amount|sum\s+of\s+amount|total\s+revenue|expenditure|spending)\s+(?:greater\s+than|more\s+than|>|above|over|exceeding|less\s+than|<|below|under)\s+\d+', q_clean) or re.search(r'\b(?:greater\s+than|more\s+than|>|above|over|exceeding)\s+\d+\s+(?:in\s+total\s+spending|in\s+spending|in\s+total\s+amount)\b', q_clean):
            constraints.has_subquery = True
            constraints.unresolved_facets.append("aggregate_threshold_having")

        # Numeric and Date filters: First extract explicitly column-bound numeric filters
        bound_filters: List[FilterConstraint] = []
        for m in re.finditer(r'\b([a-zA-Z_]+)\s*(?:is\s*)?(under|below|less\s+than|<|smaller\s+than)\s*(\d+(?:\.\d+)?)\b', q_clean):
            c_name = m.group(1).lower()
            if c_name in all_cols_map:
                bound_filters.append(FilterConstraint(column=c_name, table=all_cols_map[c_name], operator="<", value=float(m.group(3))))
        for m in re.finditer(r'\b([a-zA-Z_]+)\s*(?:is\s*)?(over|above|greater\s+than|>|more\s+than|exceeding)\s*(\d+(?:\.\d+)?)\b', q_clean):
            c_name = m.group(1).lower()
            if c_name in all_cols_map:
                bound_filters.append(FilterConstraint(column=c_name, table=all_cols_map[c_name], operator=">", value=float(m.group(3))))

        if bound_filters:
            for bf in bound_filters:
                constraints.filters.append(bf)
                if bf.table:
                    constraints.tables.add(bf.table)
        elif "aggregate_threshold_having" not in constraints.unresolved_facets:
            having_count_match = re.search(r'\b(greater\s+than|more\s+than|above|>)\s+(\d+)\s+(?:orders?|items?|products?|purchases?|records?)\b', q_clean)
            if having_count_match:
                constraints.has_subquery = True
                constraints.unresolved_facets.append("having_clause")
            else:
                num_filter_match = re.search(r'\b(greater\s+than|more\s+than|above|>)\s+(\d+(?:\.\d+)?)\b', q_clean)
                if num_filter_match:
                    val_num = float(num_filter_match.group(2))
                    constraints.filters.append(FilterConstraint(column="*", operator=">", value=val_num))

                num_less_match = re.search(r'\b(less\s+than|under|below|<)\s+(\d+(?:\.\d+)?)\b', q_clean)
                if num_less_match:
                    val_num = float(num_less_match.group(2))
                    constraints.filters.append(FilterConstraint(column="*", operator="<", value=val_num))

        date_filter_match = re.search(r'\b(after|since|from)\s+([a-zA-Z]+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})\b', q_clean)
        if date_filter_match:
            constraints.filters.append(FilterConstraint(column="*", operator=">", value=date_filter_match.group(2)))

        # 5. Detect Grouping Intent ("in each", "for each", "by each", "per", "for every", "by every", "grouped by", "breakdown by")
        # Exclude passive relationship phrasing like "placed by", "ordered by", "purchased by", "bought by"
        q_no_passive = re.sub(r'\b(placed\s+by|ordered\s+by|purchased\s+by|bought\s+by)\b', '', q_clean)
        grp_match = re.search(r'\b(?:for\s+each|in\s+each|by\s+each|for\s+every|by\s+every|per|grouped\s+by|breakdown\s+by)\s+([a-zA-Z_]+)\b', q_no_passive)
        if not grp_match:
            # Match "by <optional-modifier> <dimension>" — capture the LAST known dimension word
            grp_match = re.search(r'\bby\s+(?:[a-zA-Z_]+\s+)?(city|category|status|customer_id|product_name|name|customer|customers|product|products)\b', q_no_passive)
            if not grp_match:
                grp_match = re.search(r'\bby\s+(city|category|status|customer|customers|product|products|customer_id|product_name|name)\b', q_no_passive)

        if grp_match and not re.search(r'\bwithout\s+breaking\s+(?:it\s+)?down\b', q_clean):
            dim_word = grp_match.group(grp_match.lastindex).lower() if grp_match.lastindex else grp_match.group(1).lower()
            grp_col = None
            if dim_word in all_cols_map:
                grp_col = dim_word
            elif dim_word in ("customer", "customers", "user", "users"):
                grp_col = "customer_id" if "customer_id" in all_cols_map else "name"
            elif dim_word in ("product", "products", "item", "items"):
                grp_col = "product_name" if "product_name" in all_cols_map else "category"
            elif dim_word == "city":
                grp_col = "city"
            elif dim_word == "category":
                grp_col = "category"
            elif dim_word == "status":
                grp_col = "status"

            if grp_col:
                constraints.group_by = GroupByConstraint(columns=[grp_col])
                tbl = all_cols_map.get(grp_col)
                if tbl:
                    constraints.tables.add(tbl)

        # 6. Detect Ranking & Limit Intent
        limit_match = re.search(r'\b(top|bottom|first|last|\d+\s+(?:lowest|highest|cheapest|most|least))\s*(\d+)?\b', q_clean)
        if limit_match and not constraints.order_by:
            num = 1
            if limit_match.group(2):
                num = int(limit_match.group(2))
            else:
                d_match = re.search(r'\b(\d+)\b', limit_match.group(0))
                if d_match:
                    num = int(d_match.group(1))

            direction = "DESC"
            if re.search(r'\b(lowest|cheapest|least|bottom|first)\b', q_clean):
                direction = "ASC"

            constraints.limit = num
            constraints.order_by.append(OrderByConstraint(column="*", direction=direction))
        elif re.search(r'\b(most\s+recent|latest|newest|most\s+recent)\b', q_clean) and not constraints.order_by:
            # Temporal superlative → ORDER BY date/time column DESC LIMIT 1
            constraints.limit = 1
            constraints.order_by.append(OrderByConstraint(column="*", direction="DESC"))
        elif re.search(r'\b(oldest|earliest)\b', q_clean) and not constraints.order_by:
            constraints.limit = 1
            constraints.order_by.append(OrderByConstraint(column="*", direction="ASC"))
        elif re.search(r'\b(cheapest|most\s+expensive|highest|lowest)\b', q_clean) and not constraints.aggregations and not constraints.order_by:
            direction = "ASC" if "cheapest" in q_clean or "lowest" in q_clean else "DESC"
            constraints.limit = 1
            constraints.order_by.append(OrderByConstraint(column="*", direction=direction))

        # 7. Multi-Table Join Intent
        if len(constraints.tables) >= 2:
            tbl_list = sorted(list(constraints.tables))
            constraints.joins.append(JoinConstraint(
                left_table=tbl_list[0],
                right_table=tbl_list[1],
                join_type="LEFT" if "include" in q_clean or "all " in q_clean else "INNER"
            ))

        return constraints

    def _parse_schema_metadata(self, schema_context: str) -> Tuple[Dict[str, Dict[str, str]], Dict[str, List[str]]]:
        """Extract table column lists with types and sample allowed values from schema DDL comments."""
        tables_meta: Dict[str, Dict[str, str]] = {}
        sample_values: Dict[str, List[str]] = {}

        table_blocks = re.findall(
            r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:["\w]+\.)?"?([a-zA-Z0-9_]+)"?[^;]*?\((.*?)\);',
            schema_context,
            re.IGNORECASE | re.DOTALL,
        )
        for tbl_name, body in table_blocks:
            cols: Dict[str, str] = {}
            for line in body.split("\n"):
                line = line.strip()
                col_match = re.search(r'"?([a-zA-Z0-9_]+)"?\s+([A-Z0-9_ ]+)', line, re.IGNORECASE)
                if col_match and not line.startswith(("PRIMARY", "FOREIGN", "KEY", "CONSTRAINT", "INDEX")):
                    c_name = col_match.group(1).lower()
                    c_type = col_match.group(2).strip().upper()
                    cols[c_name] = c_type

                # Sample values comment: -- Allowed/Sample Values: ['val1', 'val2']
                val_match = re.search(r'--\s*(?:Allowed/Sample Values|Sample Values):\s*(\[.*?\])', line, re.IGNORECASE)
                if val_match and col_match:
                    try:
                        import ast
                        parsed_vals = ast.literal_eval(val_match.group(1))
                        if isinstance(parsed_vals, list):
                            sample_values[col_match.group(1).lower()] = [str(v) for v in parsed_vals]
                    except Exception:
                        pass

            tables_meta[tbl_name.lower()] = cols

        return tables_meta, sample_values

    def _resolve_target_column(
        self,
        q_clean: str,
        detected_tables: Set[str],
        tables_meta: Dict[str, Dict[str, str]],
        agg_type: str
    ) -> Optional[str]:
        """Map target numeric measure column from query question."""
        numeric_keywords = ("INT", "NUMERIC", "DECIMAL", "FLOAT", "REAL", "DOUBLE", "BIGINT", "MONEY", "NUMBER")

        if not detected_tables and tables_meta:
            detected_tables = set(tables_meta.keys())

        # 1. Semantic measure keywords mapping to known measure columns
        measure_intent = re.search(r'\b(spending|spend|revenue|sales|monetary|ticket\s+size|amount|price|cost|quantity|units|val|value)\b', q_clean)
        
        # 2. Check for exact numeric column mentions in question
        for tbl in detected_tables:
            cols = tables_meta.get(tbl, {})
            for c, c_type in cols.items():
                is_num = any(k in c_type for k in numeric_keywords) or c in ("amount", "price", "cost", "quantity", "unit_price")
                if is_num and not c.endswith(("_id", "_key", "_pk", "_fk")) and c != "id":
                    if re.search(rf'\b{re.escape(c)}\b', q_clean):
                        return c

        # 3. Resolve from semantic keyword (e.g. spending -> amount, price -> price)
        if measure_intent:
            m_word = measure_intent.group(1).lower()
            search_tables = list(detected_tables) + [t for t in tables_meta.keys() if t not in detected_tables]
            for tbl in search_tables:
                cols = tables_meta.get(tbl, {})
                for c, c_type in cols.items():
                    is_num = any(k in c_type for k in numeric_keywords) or c in ("amount", "price", "cost", "quantity", "unit_price")
                    if is_num and not c.endswith(("_id", "_key", "_pk", "_fk")) and c != "id":
                        if m_word in ("spending", "spend", "revenue", "sales", "amount", "monetary") and c in ("amount", "total_amount", "revenue"):
                            detected_tables.add(tbl)
                            return c
                        elif m_word in ("price", "cost") and "price" in c:
                            detected_tables.add(tbl)
                            return c
                        elif m_word in ("quantity", "units") and "quantity" in c:
                            detected_tables.add(tbl)
                            return c

        # 4. Fallback to any single numeric measure in detected tables ONLY if measure intent is compatible
        if not measure_intent or measure_intent.group(1).lower() not in ("spending", "spend", "revenue", "sales"):
            for tbl in detected_tables:
                cols = tables_meta.get(tbl, {})
                num_cols = [c for c, c_type in cols.items() if (any(k in c_type for k in numeric_keywords) or c in ("amount", "price", "cost", "quantity")) and not c.endswith(("_id", "_key")) and c != "id"]
                if len(num_cols) == 1:
                    return num_cols[0]

        return None


constraint_extraction_service = ConstraintExtractionService()
