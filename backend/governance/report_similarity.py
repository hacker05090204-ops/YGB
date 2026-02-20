"""
report_similarity.py — Semantic Similarity Filter (Phase 4)

Uses local TF-IDF embeddings to detect potential internal duplicates.
If cosine_similarity > 0.9 → mark as potential internal duplicate.

No external API calls. Internal optimization only.
"""

import os
import json
import re
import math
from collections import Counter
from typing import List, Dict, Tuple, Optional

REPORTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'reports')
SIMILARITY_LOG = os.path.join(REPORTS_DIR, 'similarity_duplicates.json')

os.makedirs(REPORTS_DIR, exist_ok=True)

SIMILARITY_THRESHOLD = 0.9


# ===================================================================
# TF-IDF Vectorizer (local, no external deps)
# ===================================================================

def tokenize(text: str) -> List[str]:
    """Simple whitespace + punctuation tokenizer."""
    return re.findall(r'\b\w+\b', text.lower())


def compute_tf(tokens: List[str]) -> Dict[str, float]:
    """Term frequency for a single document."""
    counts = Counter(tokens)
    total = len(tokens)
    return {word: count / total for word, count in counts.items()} if total > 0 else {}


def compute_idf(corpus: List[List[str]]) -> Dict[str, float]:
    """Inverse document frequency across corpus."""
    n_docs = len(corpus)
    df = Counter()
    for doc_tokens in corpus:
        unique_tokens = set(doc_tokens)
        for token in unique_tokens:
            df[token] += 1
    return {
        word: math.log((n_docs + 1) / (count + 1)) + 1
        for word, count in df.items()
    }


def compute_tfidf_vector(
    tokens: List[str],
    idf: Dict[str, float],
    vocabulary: List[str]
) -> List[float]:
    """Compute TF-IDF vector for a document given the IDF and vocabulary."""
    tf = compute_tf(tokens)
    return [tf.get(word, 0.0) * idf.get(word, 0.0) for word in vocabulary]


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ===================================================================
# Report Comparison
# ===================================================================

def check_report_similarity(
    new_report: str,
    existing_reports: List[str],
    threshold: float = SIMILARITY_THRESHOLD
) -> List[Tuple[int, float]]:
    """
    Compare a new report against existing reports using TF-IDF cosine similarity.

    Returns a list of (index, similarity_score) tuples for reports exceeding
    the threshold. These are potential internal duplicates.
    """
    if not existing_reports:
        return []

    # Tokenize all documents
    all_docs = [tokenize(r) for r in existing_reports]
    new_tokens = tokenize(new_report)
    all_docs_with_new = all_docs + [new_tokens]

    # Build vocabulary and IDF
    idf = compute_idf(all_docs_with_new)
    vocabulary = sorted(idf.keys())

    # Vectorize
    new_vec = compute_tfidf_vector(new_tokens, idf, vocabulary)
    duplicates = []

    for idx, doc_tokens in enumerate(all_docs):
        doc_vec = compute_tfidf_vector(doc_tokens, idf, vocabulary)
        sim = cosine_similarity(new_vec, doc_vec)
        if sim > threshold:
            duplicates.append((idx, sim))

    return sorted(duplicates, key=lambda x: -x[1])


def log_potential_duplicate(
    new_report_id: str,
    matched_report_id: str,
    similarity: float
):
    """Log a potential duplicate finding."""
    log = []
    if os.path.exists(SIMILARITY_LOG):
        with open(SIMILARITY_LOG, 'r') as f:
            try:
                log = json.load(f)
            except json.JSONDecodeError:
                log = []

    log.append({
        "new_report": new_report_id,
        "matched_report": matched_report_id,
        "similarity": round(similarity, 4),
        "status": "potential_duplicate",
    })

    with open(SIMILARITY_LOG, 'w') as f:
        json.dump(log, f, indent=2)
