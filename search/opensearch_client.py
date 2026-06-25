from __future__ import annotations
import yaml
from pathlib import Path

from opensearchpy import OpenSearch

_DEFAULT_CONFIG = str(Path(__file__).parent.parent / "configs" / "settings.yaml")
_client: OpenSearch | None = None


def get_client(config_path: str = _DEFAULT_CONFIG) -> OpenSearch:
    global _client
    if _client is None:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)["opensearch"]
        _client = OpenSearch(
            hosts=[{"host": cfg["host"], "port": cfg["port"]}],
            use_ssl=False,
            verify_certs=False,
            http_compress=True,
        )
    return _client
