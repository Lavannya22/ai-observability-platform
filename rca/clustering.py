import yaml
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def cluster_logs(logs: list[dict], config_path: str = "configs/settings.yaml") -> list[dict]:
    """
    Group ERROR logs into clusters using TF-IDF + cosine similarity.

    Uses greedy threshold-based grouping: each unassigned log either joins
    the nearest existing cluster (if similarity >= threshold) or starts a new one.

    Returns a list of cluster dicts, each containing the member logs.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    threshold = config["clustering"]["similarity_threshold"]
    max_features = config["clustering"]["max_features"]

    error_logs = [log for log in logs if log["level"] == "ERROR"]
    if not error_logs:
        return []

    messages = [log["message"] for log in error_logs]

    vectorizer = TfidfVectorizer(max_features=max_features)
    tfidf_matrix = vectorizer.fit_transform(messages)

    # Greedy single-pass clustering
    cluster_ids = [-1] * len(error_logs)
    cluster_centroids = []
    next_cluster = 0

    for i in range(len(error_logs)):
        vec = tfidf_matrix[i]

        if not cluster_centroids:
            cluster_ids[i] = next_cluster
            cluster_centroids.append(vec)
            next_cluster += 1
            continue

        centroids_matrix = np.vstack([c.toarray() for c in cluster_centroids])
        sims = cosine_similarity(vec, centroids_matrix)[0]
        best_idx = int(np.argmax(sims))

        if sims[best_idx] >= threshold:
            cluster_ids[i] = best_idx
            # Update centroid as mean of all members
            cluster_centroids[best_idx] = (cluster_centroids[best_idx] + vec) / 2
        else:
            cluster_ids[i] = next_cluster
            cluster_centroids.append(vec)
            next_cluster += 1

    # Group logs by cluster id
    clusters: dict[int, list] = {}
    for log, cid in zip(error_logs, cluster_ids):
        clusters.setdefault(cid, []).append(log)

    result = []
    for cid, members in sorted(clusters.items()):
        services = list({m["service"] for m in members})
        result.append({
            "cluster_id": cid,
            "size": len(members),
            "services": services,
            "logs": members,
            "summary": members[0]["message"],  # representative message
        })

    return result
