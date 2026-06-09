"""Train interpretable ML models using real datasets for toxicity, sarcasm, and sentiment."""

from pathlib import Path
import json
import joblib
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix


RANDOM_STATE = 42


def build_pipeline():
    """Returns the required sklearn pipeline configuration."""

    return Pipeline([
        ("tfidf", TfidfVectorizer(
            max_features=10000,
            ngram_range=(1, 2),
            stop_words="english",
            min_df=2,
        )),
        ("clf", LogisticRegression(
            C=1.0,
            max_iter=1000,
            class_weight="balanced",
            random_state=RANDOM_STATE,
        )),
    ])


def _read_text_file(path):
    """Reads plain text file content using utf-8 with fallback error handling."""

    return path.read_text(encoding="utf-8", errors="ignore").strip()


def load_imdb_sentiment(imdb_root):
    """Loads IMDb polarity data from aclImdb/train/pos and aclImdb/train/neg."""

    pos_dir = imdb_root / "train" / "pos"
    neg_dir = imdb_root / "train" / "neg"
    if not pos_dir.exists() or not neg_dir.exists():
        raise FileNotFoundError("IMDb dataset not found. Expected aclImdb/train/pos and aclImdb/train/neg.")

    texts = []
    labels = []

    for txt_file in pos_dir.glob("*.txt"):
        texts.append(_read_text_file(txt_file))
        labels.append("positive")

    for txt_file in neg_dir.glob("*.txt"):
        texts.append(_read_text_file(txt_file))
        labels.append("negative")

    return texts, labels


def load_sentiment140(csv_path):
    """Loads Sentiment140 CSV and maps labels to positive/negative."""

    if not csv_path.exists():
        raise FileNotFoundError("Sentiment140 CSV not found.")

    # Sentiment140 format has no header in many downloads.
    col_names = ["target", "ids", "date", "flag", "user", "text"]
    df = pd.read_csv(csv_path, encoding="latin-1", names=col_names, header=None)
    df = df[df["target"].isin([0, 4])].copy()
    df["label"] = df["target"].map({0: "negative", 4: "positive"})
    df = df.dropna(subset=["text", "label"])

    return df["text"].astype(str).tolist(), df["label"].astype(str).tolist()


def load_sarcasm_headlines(json_paths):
    """Loads sarcasm headlines dataset from one or more JSONL files."""

    rows = []
    for path in json_paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if "headline" in row and "is_sarcastic" in row:
                    rows.append((str(row["headline"]), int(row["is_sarcastic"])))

    if not rows:
        raise FileNotFoundError("Sarcasm dataset not found. Expected Sarcasm_Headlines_Dataset*.json.")

    texts = [r[0] for r in rows]
    labels = [r[1] for r in rows]
    return texts, labels


def load_hate_speech(csv_path):
    """Loads Davidson-style hate speech dataset and maps to binary toxicity."""

    if not csv_path.exists():
        raise FileNotFoundError("Hate speech dataset CSV not found.")

    df = pd.read_csv(csv_path)

    # Davidson dataset commonly uses columns: tweet, class (0=hate,1=offensive,2=neither).
    text_col = "tweet" if "tweet" in df.columns else "text"
    if text_col not in df.columns:
        raise ValueError("Hate speech dataset must include tweet or text column.")

    if "class" in df.columns:
        # Toxic class is hate speech or offensive language.
        df["label"] = df["class"].apply(lambda x: 1 if int(x) in [0, 1] else 0)
    elif all(col in df.columns for col in ["hate_speech", "offensive_language", "neither"]):
        df["label"] = ((df["hate_speech"] + df["offensive_language"]) > df["neither"]).astype(int)
    elif "label" in df.columns:
        # Generic fallback when dataset already has binary label.
        df["label"] = df["label"].astype(int)
    else:
        raise ValueError("Unsupported hate speech dataset format.")

    df = df.dropna(subset=[text_col, "label"])
    return df[text_col].astype(str).tolist(), df["label"].astype(int).tolist()


def train_and_save(name, texts, labels, output_path):
    """Fits model, prints metrics, and saves to joblib file."""

    X_train, X_test, y_train, y_test = train_test_split(
        texts,
        labels,
        test_size=0.2,
        random_state=RANDOM_STATE,
        stratify=labels,
    )

    model = build_pipeline()
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    print(f"\n=== {name.upper()} CLASSIFICATION REPORT ===")
    print(classification_report(y_test, preds))
    print("Confusion Matrix:")
    print(confusion_matrix(y_test, preds))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_path)
    print(f"Saved: {output_path}")


def main():
    """Train all three models from real datasets and persist them under ml_models/."""

    base_dir = Path(__file__).resolve().parents[1]
    model_dir = base_dir / "ml_models"

    # Put datasets under verdictbox/datasets/ with these names:
    # - datasets/aclImdb/...
    # - datasets/training.1600000.processed.noemoticon.csv (optional fallback for sentiment)
    # - datasets/Sarcasm_Headlines_Dataset.json and/or Sarcasm_Headlines_Dataset_v2.json
    # - datasets/labeled_data.csv
    datasets_dir = base_dir / "datasets"

    imdb_dir = datasets_dir / "aclImdb"
    sent140_csv = datasets_dir / "training.1600000.processed.noemoticon.csv"
    sarcasm_candidates = [
        datasets_dir / "Sarcasm_Headlines_Dataset.json",
        datasets_dir / "Sarcasm_Headlines_Dataset_v2.json",
    ]
    hate_csv = datasets_dir / "labeled_data.csv"

    if imdb_dir.exists():
        sen_texts, sen_labels = load_imdb_sentiment(imdb_dir)
        print("Loaded sentiment dataset: IMDb")
    elif sent140_csv.exists():
        sen_texts, sen_labels = load_sentiment140(sent140_csv)
        print("Loaded sentiment dataset: Sentiment140")
    else:
        raise FileNotFoundError(
            "No sentiment dataset found. Add IMDb (datasets/aclImdb) or Sentiment140 CSV."
        )

    sar_texts, sar_labels = load_sarcasm_headlines(sarcasm_candidates)
    print("Loaded sarcasm dataset: News Headlines for Sarcasm Detection")

    tox_texts, tox_labels = load_hate_speech(hate_csv)
    print("Loaded toxicity dataset: Hate Speech and Offensive Language")

    train_and_save("toxicity", tox_texts, tox_labels, model_dir / "toxicity_model.pkl")
    train_and_save("sarcasm", sar_texts, sar_labels, model_dir / "sarcasm_model.pkl")
    train_and_save("sentiment", sen_texts, sen_labels, model_dir / "sentiment_model.pkl")


if __name__ == "__main__":
    main()
