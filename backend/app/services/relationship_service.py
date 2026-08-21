import logging
from typing import Dict, Any, List, Set
from collections import deque

logger = logging.getLogger(__name__)


class RelationshipService:
    def build_fk_graph(self, schema_info: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
        """
        Build adjacency list from FK metadata.
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
                # Forward edge: table -> foreign_table
                graph[table_name].append({
                    "to_table": ft,
                    "from_col": fk.get("column", ""),
                    "to_col": fk.get("foreign_column", ""),
                    "direction": "forward"
                })
                # Reverse edge: foreign_table -> table
                if ft not in graph:
                    graph[ft] = []
                graph[ft].append({
                    "to_table": table_name,
                    "from_col": fk.get("foreign_column", ""),
                    "to_col": fk.get("column", ""),
                    "direction": "reverse"
                })

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
        # normalize graph keys
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
        Format FK relationships as human-readable text for the LLM prompt.
        Example output:
          Relationships (Foreign Keys):
            orders.customer_id -> customers.id
            order_items.order_id -> orders.id
        """
        lines = []
        tables_dict = schema_info.get("tables", {})
        for table_name, meta in tables_dict.items():
            fks = meta.get("foreign_keys", []) if isinstance(meta, dict) else []
            for fk in fks:
                ft = fk.get("foreign_table", "")
                fc = fk.get("column", "")
                frc = fk.get("foreign_column", "")
                if ft and fc and frc:
                    lines.append(f'  {table_name}.{fc} -> {ft}.{frc}')
        if not lines:
            return ""
        return "Relationships (Foreign Keys):\n" + "\n".join(lines)

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

        # BFS: state = (current_table, path_so_far)
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
