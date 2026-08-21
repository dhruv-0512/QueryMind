import logging
from typing import Dict, Any, List, Set, Optional
from collections import deque
from app.services.relationship_inference_service import relationship_inference_service

logger = logging.getLogger(__name__)


class RelationshipService:
    def infer_csv_relationships(
        self,
        schema_info: Dict[str, Any],
        sample_data: Optional[Dict[str, Dict[str, List[Any]]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Delegate candidate relationship discovery to RelationshipInferenceService.
        """
        candidates = relationship_inference_service.detect_candidate_relationships(schema_info, sample_data)
        inferred = []
        for cand in candidates:
            inferred.append({
                "table": cand["source_table"],
                "column": cand["source_column"],
                "foreign_table": cand["target_table"],
                "foreign_column": cand["target_column"],
                "source_table": cand["source_table"],
                "source_column": cand["source_column"],
                "target_table": cand["target_table"],
                "target_column": cand["target_column"],
                "score": cand["score"],
                "confidence_level": cand["confidence_level"],
                "cardinality": cand["cardinality"],
                "signals": cand["signals"],
                "inferred": True
            })
        return inferred

    def build_fk_graph(
        self,
        schema_info: Dict[str, Any],
        confirmed_relationships: Optional[List[Dict[str, str]]] = None,
        sample_data: Optional[Dict[str, Dict[str, List[Any]]]] = None
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Build adjacency list from explicit database FKs + confirmed relationships + inferred candidates.
        Returns {table_name: [{to_table, from_col, to_col, source_type}, ...]}
        Includes both directions (forward and reverse).
        """
        graph: Dict[str, List[Dict[str, str]]] = {}
        tables_dict = schema_info.get("tables", {})

        # Initialize graph nodes
        for t_name in tables_dict.keys():
            if t_name not in graph:
                graph[t_name] = []

        # 1. Explicit database Foreign Keys
        for table_name, meta in tables_dict.items():
            fks = meta.get("foreign_keys", []) if isinstance(meta, dict) else []
            for fk in fks:
                ft = fk.get("foreign_table", "")
                fc = fk.get("column", "")
                frc = fk.get("foreign_column", "")
                if not ft:
                    continue
                graph[table_name].append({
                    "to_table": ft,
                    "from_col": fc,
                    "to_col": frc,
                    "direction": "forward",
                    "source_type": "database_fk"
                })
                if ft not in graph:
                    graph[ft] = []
                graph[ft].append({
                    "to_table": table_name,
                    "from_col": frc,
                    "to_col": fc,
                    "direction": "reverse",
                    "source_type": "database_fk"
                })

        # 2. Confirmed relationships passed explicitly
        user_confirmed = confirmed_relationships or schema_info.get("confirmed_relationships", [])
        for rel in user_confirmed:
            t = rel.get("source_table") or rel.get("table")
            fc = rel.get("source_column") or rel.get("column")
            ft = rel.get("target_table") or rel.get("foreign_table")
            frc = rel.get("target_column") or rel.get("foreign_column")

            if t and ft and fc and frc:
                if t not in graph:
                    graph[t] = []
                if ft not in graph:
                    graph[ft] = []

                if not any(e["to_table"].lower() == ft.lower() and e["from_col"].lower() == fc.lower() for e in graph[t]):
                    graph[t].append({"to_table": ft, "from_col": fc, "to_col": frc, "direction": "forward", "source_type": "user_confirmed"})
                if not any(e["to_table"].lower() == t.lower() and e["from_col"].lower() == frc.lower() for e in graph[ft]):
                    graph[ft].append({"to_table": t, "from_col": frc, "to_col": fc, "direction": "reverse", "source_type": "user_confirmed"})

        # 3. Candidate relationships inferred deterministically
        inferred_fks = self.infer_csv_relationships(schema_info, sample_data)
        for fk in inferred_fks:
            t = fk["table"]
            ft = fk["foreign_table"]
            fc = fk["column"]
            frc = fk["foreign_column"]
            if t not in graph:
                graph[t] = []
            if ft not in graph:
                graph[ft] = []

            if not any(e["to_table"].lower() == ft.lower() and e["from_col"].lower() == fc.lower() for e in graph[t]):
                graph[t].append({"to_table": ft, "from_col": fc, "to_col": frc, "direction": "forward", "source_type": "inferred"})
            if not any(e["to_table"].lower() == t.lower() and e["from_col"].lower() == frc.lower() for e in graph[ft]):
                graph[ft].append({"to_table": t, "from_col": frc, "to_col": fc, "direction": "reverse", "source_type": "inferred"})

        return graph

    def get_connected_tables(
        self,
        seed_tables: List[str],
        graph: Dict[str, List[Dict[str, str]]],
        max_hops: int = 3
    ) -> Set[str]:
        """
        BFS from seed tables up to max_hops away through relationship graph.
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

    def format_relationship_map(
        self,
        schema_info: Dict[str, Any],
        confirmed_relationships: Optional[List[Dict[str, str]]] = None,
        sample_data: Optional[Dict[str, Dict[str, List[Any]]]] = None
    ) -> str:
        """
        Format relationship map for LLM prompt context.
        Shows explicit database FKs, user-confirmed links, and high-confidence inferred links.
        """
        lines = []
        seen = set()
        tables_dict = schema_info.get("tables", {})

        # 1. Explicit Database Foreign Keys
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

        # 2. Confirmed relationships
        user_confirmed = confirmed_relationships or schema_info.get("confirmed_relationships", [])
        for rel in user_confirmed:
            t = rel.get("source_table") or rel.get("table")
            fc = rel.get("source_column") or rel.get("column")
            ft = rel.get("target_table") or rel.get("foreign_table")
            frc = rel.get("target_column") or rel.get("foreign_column")
            if t and ft and fc and frc:
                line = f'  {t}.{fc} -> {ft}.{frc} (Confirmed Link)'
                if line not in seen:
                    seen.add(line)
                    lines.append(line)

        # 3. Inferred Candidate Relationships
        inferred = self.infer_csv_relationships(schema_info, sample_data)
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
