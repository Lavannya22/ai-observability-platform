"""
HDBSCAN clustering on Sentence Transformer embeddings.

Pipeline: log messages → embeddings → HDBSCAN → labels
"""
from __future__ import annotations

import numpy as np
import hdbscan
from sklearn.metrics import v_measure_score, normalized_mutual_info_score

from ml.embeddings import embed


def cluster(
    messages: list[str],
    min_cluster_size: int = 5,
    min_samples: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Embed messages and cluster with HDBSCAN.

    Returns:
        labels     — cluster assignment per message (-1 = noise)
        embeddings — the embedding matrix (for reuse if needed)
    """
    embeddings = embed(messages)
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    labels = clusterer.fit_predict(embeddings)
    return labels, embeddings


def cluster_logs(logs: list[dict], min_cluster_size: int = 3, min_samples: int = 2) -> list[dict]:
    """
    Production cluster_logs() using HDBSCAN + Sentence Transformer embeddings.

    Drop-in replacement for rca.clustering.cluster_logs().
    Uses smaller min_cluster_size defaults than the evaluation version
    to handle the smaller per-incident log volumes seen in streaming.
    """
    error_logs = [log for log in logs if log.get("level") == "ERROR"]
    if not error_logs:
        return []

    messages = [log["message"] for log in error_logs]
    labels, _ = cluster(messages, min_cluster_size=min_cluster_size, min_samples=min_samples)

    clusters: dict[int, list] = {}
    for log, label in zip(error_logs, labels.tolist()):
        clusters.setdefault(label, []).append(log)

    result = []
    for cid, members in sorted(clusters.items()):
        services = list({m["service"] for m in members})
        result.append({
            "cluster_id": cid,
            "size": len(members),
            "services": services,
            "logs": members,
            "summary": members[0]["message"],
        })

    return result


def evaluate_hdbscan(
    true_labels: list[str],
    pred_labels: np.ndarray,
) -> dict:
    """
    Compute V-Measure, NMI, cluster count, and noise reduction for HDBSCAN output.

    Noise points (label == -1) are excluded from V-Measure / NMI because
    they are explicitly not assigned to any cluster.  Noise reduction is
    reported separately: a high noise rate means the model is conservative;
    a low noise rate means it found dense structure.
    """
    pred_list = pred_labels.tolist() if hasattr(pred_labels, "tolist") else list(pred_labels)

    noise_mask = [p == -1 for p in pred_list]
    noise_count = sum(noise_mask)
    total = len(pred_list)
    noise_reduction = round(noise_count / total, 4) if total > 0 else 0.0

    # Filter noise for metric computation
    filtered_true = [t for t, n in zip(true_labels, noise_mask) if not n]
    filtered_pred = [p for p, n in zip(pred_list, noise_mask) if not n]

    if len(set(filtered_pred)) < 2 or len(filtered_true) == 0:
        return {
            "v_measure": 0.0,
            "nmi": 0.0,
            "num_clusters": len(set(p for p in pred_list if p != -1)),
            "noise_points": noise_count,
            "noise_rate": noise_reduction,
        }

    vm = v_measure_score(filtered_true, filtered_pred)
    nmi = normalized_mutual_info_score(filtered_true, filtered_pred)
    num_clusters = len(set(p for p in pred_list if p != -1))

    return {
        "v_measure": round(vm, 4),
        "nmi": round(nmi, 4),
        "num_clusters": num_clusters,
        "noise_points": noise_count,
        "noise_rate": noise_reduction,
    }
