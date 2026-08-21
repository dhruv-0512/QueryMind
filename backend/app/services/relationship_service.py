import logging
from typing import Dict, Any, List, Set
from collections import deque

logger = logging.getLogger(__name__)


class RelationshipService:
    def infer_csv_relationships(self, schema_info: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Heuristically infer Foreign Key relationships between uploaded CSV tables when
        no explicit SQL database Foreign Keys exist.

        Methods used:
        1. Naming convention matching (e.g. orders.customer_id -> customers.id or customers.customer_id)
        2. Exact column name matching for non-generic ID columns (e.g. sales.client_id -> clients.client_id)
        """
        inferred = []
        tables_dict = schema_info.get("tables", {})
        table_names = list(tables_dict.keys())
        
        # Build map of table_name_lower -> actual table name & columns_lower -> actual column name
        tables_meta = {}
        for t_name, meta in tables_dict.items():
            cols = meta.get("columns", []) if isinstance(meta, dict) else meta
            cols_dict = {c.lower(): c for c in cols}
            tables_meta[t_name.lower()] = {
                "original_name": t_name,
                "columns_map": cols_dict,
                "cols_set": set(cols_dict.keys())
            }

        seen_pairs = set()

        for t_lower, t_info in tables_meta.items():
            t_orig = t_info["original_name"]
            for col_lower, col_orig in t_info["columns_map"].items():

                # Rule 1: Column ends with _id (e.g. customer_id, product_id, department_id)
                if col_lower.endswith("_id") and len(col_lower) > 3:
                    prefix = col_lower[:-3]  # e.g., 'customer', 'product', 'department'
                    
                    # Search for target table matching prefix (e.g., 'customer' -> 'customers', 'customer_info', 'customer')
                    for target_t_lower, target_info in tables_meta.items():
                        if target_t_lower == t_lower:
                            continue
                        
                        target_orig = target_info["original_name"]
                        target_cols = target_info["columns_map"]

                        # Check if target table name matches prefix (e.g., 'customers' matches 'customer')
                        if target_t_lower == prefix or target_t_lower == prefix + "s" or target_t_lower == prefix + "es":
                            # Target column could be 'id' or 'customer_id'
                            target_col = None
                            if "id" in target_cols:
                                target_col = target_cols["id"]
                            elif col_lower in target_cols:
                                target_col = target_cols[col_lower]
                            
                            if target_col:
                                pair_key = (t_orig, col_orig, target_orig, target_col)
                                if pair_key not in seen_pairs:
                                    seen_pairs.add(pair_key)
                                    inferred.append({
                                        "table": t_orig,
                                        "column": col_orig,
                                        "foreign_table": target_orig,
                                        "foreign_column": target_col,
                                        "inferred": True
                                    })
                                    break

                # Rule 2: Shared exact column name matching (e.g. client_id in sales and clients)
                if col_lower != "id" and col_lower.endswith("_id"):
                    for target_t_lower, target_info in tables_meta.items():
                        if target_t_lower == t_lower:
                            continue
                        target_orig = target_info["original_name"]
                        target_cols = target_info["columns_map"]

                        if col_lower in target_cols:
                            target_col = target_cols[col_lower]
                            pair_key = tuple(sorted([f"{t_orig}.{col_orig}", f"{target_orig}.{target_col}"]))
                            if pair_key not in seen_pairs:
                                seen_pairs.add(pair_key)
                                inferred.append({
                                    "table": t_orig,
                                    "column": col_orig,
                                    "foreign_table": target_orig,
                                    "foreign_column": target_col,
                                    "inferred": True
                                })

        return inferred

    def build_fk_graph(self, schema_info: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
        """
        Build adjacency list from explicit FK metadata + inferred CSV relationships.
        Returns {table_name: [{to_table, from_col, to_col}, ...]}
        Includes both directions (FK from and FK to).
        """
        graph: Dict[str, List[Dict[str, str]]] = {}
        tables_dict = schema_info.get("tables", {})

        for table_name, meta in tables_dict.items():
            if table_name not in graph:
                graph[table_name] = []
            
            fks = meta.get("foreign_keys", []) if isinstance(meta, dict) else []
            for fk in fks:
                ft = fk.get("foreign_table", "")
                if not ft:
                    continue
                graph[table_name].append({
                    "to_table": ft,
                    "from_col": fk.get("column", ""),
                    "to_col": fk.get("foreign_column", ""),
                    "direction": "forward"
                })
                if ft not in graph:
                    graph[ft] = []
                graph[ft].append({
                    "to_table": table_name,
                    "from_col": fk.get("foreign_column", ""),
                    "to_col": fk.get("column", ""),
                    "direction": "reverse"
                })

        # Add heuristically inferred relationships for CSV files
        inferred_fks = self.infer_csv_relationships(schema_info)
        for fk in inferred_fks:
            t = fk["table"]
            ft = fk["foreign_table"]
            fc = fk["column"]
            frc = fk["foreign_column"]
            if t not in graph:
                graph[t] = []
            if ft not in graph:
                graph[ft] = []
            
            # Avoid duplicate edges
            if not any(e["to_table"].lower() == ft.lower() and e["from_col"].lower() == fc.lower() for e in graph[t]):
                graph[t].append({"to_table": ft, "from_col": fc, "to_col": frc, "direction": "forward"})
            if not any(e["to_table"].lower() == t.lower() and e["from_col"].lower() == frc.lower() for e in graph[ft]):
                graph[ft].append({"to_table": t, "from_col": frc, "to_col": fc, "direction": "reverse"})

        return graph

    def get_connected_tables(
        self,
        seed_tables: List[str],
        graph: Dict[str, List[Dict[str, str]]],
        max_hops: int = 3
    ) -> Set[str]:
        """
        BFS from seed tables up to max_hops away through FK graph.
        Returns all connected table names including seeds.
        """
        visited: Set[str] = set()
        queue = deque([(t.lower(), 0) for t in seed_tables])
        norm_graph = {k.lower(): v for k, v in graph.items()}

        while queue:
            current, hops = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            if hops >= max_hops:
                continue
            for edge in norm_graph.get(current, []):
                neighbor = edge["to_table"].lower()
                if neighbor not in visited:
                    queue.append((neighbor, hops + 1))

        return visited

    def format_relationship_map(self, schema_info: Dict[str, Any]) -> str:
        """
        Format FK relationships (both explicit database FKs and inferred CSV relationships)
        as human-readable text for the LLM prompt.
        Example output:
          Relationships (Foreign Keys & Inferred Links):
            orders.customer_id -> customers.id
            order_items.order_id -> orders.id
        """
        lines = []
        seen = set()
        tables_dict = schema_info.get("tables", {})
        
        # 1. Explicit Foreign Keys
        for table_name, meta in tables_dict.items():
            fks = meta.get("foreign_keys", []) if isinstance(meta, dict) else []
            for fk in fks:
                ft = fk.get("foreign_table", "")
                fc = fk.get("column", "")
                frc = fk.get("foreign_column", "")
                if ft and fc and frc:
                    line = f'  {table_name}.{fc} -> {ft}.{frc}'
                    if line not in seen:
                        seen.add(line)
                        lines.append(line)

        # 2. Inferred CSV Relationships
        inferred = self.infer_csv_relationships(schema_info)
        for fk in inferred:
            line = f'  {fk["table"]}.{fk["column"]} -> {fk["foreign_table"]}.{fk["foreign_column"]} (Inferred Link)'
            if line not in seen:
                seen.add(line)
                lines.append(line)

        if not lines:
            return ""
        return "Relationships (Foreign Keys & Inferred Links):\n" + "\n".join(lines)

    def get_join_paths(
        self,
        from_table: str,
        to_table: str,
        graph: Dict[str, List[Dict[str, str]]]
    ) -> List[List[Dict[str, str]]]:
        """
        Find simple join paths between two tables (BFS, max 4 hops).
        Returns list of edge lists (each edge: from_table, to_table, from_col, to_col).
        """
        norm_graph = {k.lower(): v for k, v in graph.items()}
        from_t = from_table.lower()
        to_t = to_table.lower()

        queue = deque([(from_t, [])])
        visited_in_path: Set[str] = set()
        paths: List[List[Dict[str, str]]] = []

        while queue and len(paths) < 3:
            current, path = queue.popleft()
            if current == to_t and path:
                paths.append(path)
                continue
            if len(path) >= 4 or current in visited_in_path:
                continue
            visited_in_path.add(current)
            for edge in norm_graph.get(current, []):
                neighbor = edge["to_table"].lower()
                new_edge = {
                    "from_table": current,
                    "to_table": neighbor,
                    "from_col": edge["from_col"],
                    "to_col": edge["to_col"]
                }
                queue.append((neighbor, path + [new_edge]))

        return paths


relationship_service = RelationshipService()
