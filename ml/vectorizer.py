import re
from sklearn.feature_extraction.text import TfidfVectorizer


_NORMALISE_PATTERNS = [
    (re.compile(r'\d+\s*ms\b'), '<LATENCY>'),
    (re.compile(r'\bds_\d+\b'), '<DATASET>'),
    (re.compile(r'\bjob_\d+\b'), '<JOB>'),
    (re.compile(r'\brpt_\d+\b'), '<REPORT>'),
    (re.compile(r'\buser_\d+\b'), '<USER>'),
    (re.compile(r'\bbatch\s+\d+\b'), 'batch <BATCH>'),
    (re.compile(r'\bstep\s+\d+\b'), 'step <STEP>'),
    (re.compile(r'\b\d+\s+retries?\b'), '<NUM> retries'),
    (re.compile(r'\b\d{3,}\b'), '<NUM>'),   # remaining long integers
]


def normalise(message: str) -> str:
    """Replace variable numeric tokens so TF-IDF focuses on vocabulary, not values."""
    for pattern, replacement in _NORMALISE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


def build_vectorizer(max_features: int = 500) -> TfidfVectorizer:
    return TfidfVectorizer(
        max_features=max_features,
        sublinear_tf=True,
        preprocessor=normalise,
    )


def fit_transform(messages: list[str], max_features: int = 500):
    """Fit TF-IDF on messages and return (vectorizer, sparse matrix)."""
    vectorizer = build_vectorizer(max_features)
    matrix = vectorizer.fit_transform(messages)
    return vectorizer, matrix


def transform(vectorizer: TfidfVectorizer, messages: list[str]):
    """Transform messages using a pre-fitted vectorizer."""
    return vectorizer.transform(messages)
