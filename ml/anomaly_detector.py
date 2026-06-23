import numpy as np
from sklearn.ensemble import IsolationForest


def train_and_predict(
    X: list[list[float]],
    contamination: float = 0.2,
    random_state: int = 42,
) -> list[int]:
    """
    Fit Isolation Forest on feature matrix and return predictions.

    Returns list of 1 (normal) or -1 (anomaly) per row.
    contamination: expected proportion of anomalous rows in X.
    """
    clf = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=100,
    )
    return clf.fit_predict(X).tolist()


def evaluate_anomaly_detection(
    predictions: list[int],
    ground_truth_labels: list[str],
) -> dict:
    """
    Compute Precision, Recall, and False Positive Rate.

    predictions         — Isolation Forest output: -1 (anomaly) or 1 (normal)
    ground_truth_labels — 'anomaly' or 'normal' per row
    """
    tp = fp = fn = tn = 0

    for pred, true in zip(predictions, ground_truth_labels):
        predicted_anomaly = pred == -1
        actual_anomaly = true == "anomaly"

        if predicted_anomaly and actual_anomaly:
            tp += 1
        elif predicted_anomaly and not actual_anomaly:
            fp += 1
        elif not predicted_anomaly and actual_anomaly:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "false_positive_rate": round(fpr, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }
