import networkx as nx
import yaml


def build_graph(config_path: str = "configs/settings.yaml") -> nx.DiGraph:
    """
    Build the service dependency graph from settings.

    Edge direction: dependent → dependency  (A→B means A depends on B)
    Failures propagate in reverse: if B fails, A fails too.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    graph = nx.DiGraph()
    services = config["pipeline"]["services"]
    graph.add_nodes_from(services)

    for dependent, dependency in config["pipeline"]["dependencies"].items():
        graph.add_edge(dependent, dependency)

    return graph


def get_downstream_services(graph: nx.DiGraph, service: str) -> list[str]:
    """Services that depend on `service` (will fail if `service` fails)."""
    return list(nx.ancestors(graph, service))
