"""B11: two baselines, set up fairly.

The most-common-class baseline predicts the most common training label. The
TF-IDF baseline is a logistic regression on word n-grams. Both are trained on
the training split only and see the same cut text as the LLM. The TF-IDF
settings come only from `config/tfidf.toml`.
"""
import tomllib
from collections import Counter
from dataclasses import dataclass

CUT_AT = 4_000
TRAIN_SPLIT = "train"
REQUIRED = ("ngram_max", "min_df", "max_features", "sublinear_tf", "C", "max_iter", "seed")


class SplitError(ValueError):
    pass


def cut_text(text, limit=CUT_AT):
    """The text the LLM sees: cut at `limit` characters (B9). Returns the text and whether it was cut."""
    text = text or ""
    return (text[:limit], True) if len(text) > limit else (text, False)


def load_tfidf_config(path):
    with open(path, "rb") as f:
        config = tomllib.load(f)
    missing = [k for k in REQUIRED if k not in config]
    if missing:
        raise KeyError(f"the TF-IDF config is missing {', '.join(missing)}")
    return {k: config[k] for k in REQUIRED}


class MostCommonBaseline:
    def fit(self, labels):
        counts = Counter(labels)
        top = max(counts.values())
        self.label = min(label for label, n in counts.items() if n == top)
        return self

    def predict(self, n):
        return [self.label] * n


@dataclass
class TfidfModel:
    vectorizer: object
    classifier: object
    settings: dict


def fit_tfidf(rows, config):
    """Fit on (complaint_id, split, text, label) rows. Every row must be from the training split."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    if any(split != TRAIN_SPLIT for _, split, _, _ in rows):
        raise SplitError("TF-IDF is fitted on the training split only")
    texts = [cut_text(text)[0] for _, _, text, _ in rows]
    labels = [label for _, _, _, label in rows]
    vectorizer = TfidfVectorizer(ngram_range=(1, config["ngram_max"]), min_df=config["min_df"],
                                 max_features=config["max_features"], sublinear_tf=config["sublinear_tf"])
    classifier = LogisticRegression(C=config["C"], max_iter=config["max_iter"], random_state=config["seed"])
    classifier.fit(vectorizer.fit_transform(texts), labels)
    return TfidfModel(vectorizer, classifier, dict(config))


def predict_tfidf(model, texts):
    """A (label, confidence) pair for every text. Confidence is the top class probability."""
    matrix = model.vectorizer.transform([cut_text(t)[0] for t in texts])
    probabilities = model.classifier.predict_proba(matrix)
    classes = list(model.classifier.classes_)
    return [(classes[row.argmax()], float(row.max())) for row in probabilities]
