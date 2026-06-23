import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import v_measure_score, normalized_mutual_info_score

from ml.vectorizer import fit_transform


def get_k(ground_truth: dict) -> int:
    """k = number of distinct root causes across all scenarios."""
    return len({gt["root_cause"] for gt in ground_truth.values()})


def cluster(messages: list[str], k: int, max_features: int = 500):
    """
    Fit TF-IDF → K-Means on log messages.

    Returns:
        labels     — cluster assignment per message (int array)
        vectorizer — fitted TfidfVectorizer
        model      — fitted KMeans
    """
    vectorizer, matrix = fit_transform(messages, max_features)
    model = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = model.fit_predict(matrix)
    return labels, vectorizer, model


def evaluate_clustering(
    true_labels: list[str],
    pred_labels: list[int],
) -> dict:
    """
    Compute V-Measure and NMI between predicted clusters and true root-cause labels.

    true_labels — root_cause service name for each log
    pred_labels — cluster id assigned by K-Means
    """
    vm = v_measure_score(true_labels, pred_labels)
    nmi = normalized_mutual_info_score(true_labels, pred_labels)
    return {"v_measure": round(vm, 4), "nmi": round(nmi, 4)}
