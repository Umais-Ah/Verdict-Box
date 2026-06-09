"""Inference utilities for ML scoring and orchestration with OpenRouter verdict generation."""

from pathlib import Path
import joblib
from ai.openrouter_verdict import get_openrouter_verdict


DEBATE_POWER_WORDS = {
    "evidence",
    "research",
    "policy",
    "logic",
    "infrastructure",
    "analysis",
    "hybrid",
    "perspective",
}


def _clamp01(value):
    """Clamps a numeric value into the [0, 1] range."""

    return max(0.0, min(1.0, float(value)))


def apply_heuristic_corrections(text, scores):
    """Applies lightweight post-processing heuristics to reduce likely false positives."""

    text = (text or "").strip()
    adjusted_tox = float(scores.get("toxicity", 0.0))
    adjusted_sarc = float(scores.get("sarcasm", 0.0))
    sentiment = str(scores.get("sentiment", "")).strip().lower()
    applied = []

    # Formal grammar heuristic: structured sentence often signals serious debate tone.
    is_formal = bool(text) and text[0].isupper() and text.endswith(".")
    if is_formal:
        adjusted_sarc *= 0.85
        adjusted_tox *= 0.90
        applied.append("formal_grammar")

    # Sentiment-tone alignment heuristic.
    if sentiment == "positive":
        adjusted_tox *= 0.70
        applied.append("positive_sentiment_buffer")

    # Debate power-word filter for professional/analytical language.
    lower_text = text.lower()
    found_keywords = sum(1 for word in DEBATE_POWER_WORDS if word in lower_text)
    if found_keywords > 2:
        adjusted_sarc *= 0.80
        applied.append("debate_power_words")

    return {
        "toxicity": round(_clamp01(adjusted_tox), 4),
        "sarcasm": round(_clamp01(adjusted_sarc), 4),
        "applied_rules": applied,
    }


def _load_models():
    """Loads trained models and raises FileNotFoundError with a clear message if missing."""

    base_dir = Path(__file__).resolve().parents[1] / "ml_models"
    tox_path = base_dir / "toxicity_model.pkl"
    sar_path = base_dir / "sarcasm_model.pkl"
    sen_path = base_dir / "sentiment_model.pkl"

    if not tox_path.exists() or not sar_path.exists() or not sen_path.exists():
        raise FileNotFoundError("ML model files not found. Run ai/train_models.py first.")

    return joblib.load(tox_path), joblib.load(sar_path), joblib.load(sen_path)


def run_ml_analysis(text_a, text_b):
    """Scores both arguments and returns toxicity, sarcasm, sentiment, and toxicity gate flag."""

    try:
        toxicity_model, sarcasm_model, sentiment_model = _load_models()
    except FileNotFoundError as exc:
        return {
            "error": str(exc),
            "toxicity_a": 0.0,
            "toxicity_b": 0.0,
            "sarcasm_a": 0.0,
            "sarcasm_b": 0.0,
            "sentiment_a": "negative",
            "sentiment_b": "negative",
            "sentiment_compound_a": 0.0,
            "sentiment_compound_b": 0.0,
            "is_toxic": False,
        }

    tox_proba_a = float(toxicity_model.predict_proba([text_a])[0][1])
    tox_proba_b = float(toxicity_model.predict_proba([text_b])[0][1])

    sar_proba_a = float(sarcasm_model.predict_proba([text_a])[0][1])
    sar_proba_b = float(sarcasm_model.predict_proba([text_b])[0][1])

    sentiment_classes = list(sentiment_model.classes_)
    sen_pred_a = sentiment_model.predict([text_a])[0]
    sen_pred_b = sentiment_model.predict([text_b])[0]

    # Keep API stable: return positive/negative strings even if class labels are numeric.
    if isinstance(sen_pred_a, (int, float)):
        sen_a = "positive" if int(sen_pred_a) == 1 else "negative"
    else:
        sen_a = str(sen_pred_a)
    if isinstance(sen_pred_b, (int, float)):
        sen_b = "positive" if int(sen_pred_b) == 1 else "negative"
    else:
        sen_b = str(sen_pred_b)

    sen_proba_a = sentiment_model.predict_proba([text_a])[0]
    sen_proba_b = sentiment_model.predict_proba([text_b])[0]
    if "positive" in sentiment_classes:
        pos_idx = sentiment_classes.index("positive")
    elif 1 in sentiment_classes:
        pos_idx = sentiment_classes.index(1)
    else:
        pos_idx = 0

    pos_proba_a = float(sen_proba_a[pos_idx])
    pos_proba_b = float(sen_proba_b[pos_idx])
    # Compound score in [-1, 1].
    sentiment_compound_a = (2.0 * pos_proba_a) - 1.0
    sentiment_compound_b = (2.0 * pos_proba_b) - 1.0

    raw_tox_proba_a = tox_proba_a
    raw_tox_proba_b = tox_proba_b
    raw_sar_proba_a = sar_proba_a
    raw_sar_proba_b = sar_proba_b

    adjusted_a = apply_heuristic_corrections(
        text_a,
        {"toxicity": tox_proba_a, "sarcasm": sar_proba_a, "sentiment": sen_a},
    )
    adjusted_b = apply_heuristic_corrections(
        text_b,
        {"toxicity": tox_proba_b, "sarcasm": sar_proba_b, "sentiment": sen_b},
    )

    tox_proba_a = adjusted_a["toxicity"]
    tox_proba_b = adjusted_b["toxicity"]
    sar_proba_a = adjusted_a["sarcasm"]
    sar_proba_b = adjusted_b["sarcasm"]

    return {
        "toxicity_a": tox_proba_a,
        "toxicity_b": tox_proba_b,
        "sarcasm_a": sar_proba_a,
        "sarcasm_b": sar_proba_b,
        "raw_toxicity_a": raw_tox_proba_a,
        "raw_toxicity_b": raw_tox_proba_b,
        "raw_sarcasm_a": raw_sar_proba_a,
        "raw_sarcasm_b": raw_sar_proba_b,
        "heuristic_rules_a": adjusted_a["applied_rules"],
        "heuristic_rules_b": adjusted_b["applied_rules"],
        "sentiment_a": sen_a,
        "sentiment_b": sen_b,
        "sentiment_compound_a": sentiment_compound_a,
        "sentiment_compound_b": sentiment_compound_b,
        "is_toxic": tox_proba_a > 0.8 or tox_proba_b > 0.8,
    }


def run_full_pipeline(dispute_id, text_a, text_b, user_a_name, user_b_name, appeal_context=None, prior_verdict_context=None):
    """Runs ML scoring, toxicity gatekeeping, OpenRouter call, and final payload shaping."""

    ml_scores = run_ml_analysis(text_a, text_b)

    if ml_scores.get("error"):
        return {
            "status": "error",
            "dispute_id": dispute_id,
            "message": ml_scores["error"],
            "ml_scores": ml_scores,
        }

    if ml_scores["is_toxic"]:
        return {
            "status": "flagged",
            "dispute_id": dispute_id,
            "message": "Toxicity threshold exceeded; dispute flagged and LLM skipped.",
            "ml_scores": ml_scores,
            "verdict": None,
        }

    verdict = get_openrouter_verdict(
        text_a,
        text_b,
        ml_scores,
        user_a_name,
        user_b_name,
        appeal_context=appeal_context,
        prior_verdict_context=prior_verdict_context,
    )
    return {
        "status": "resolved",
        "dispute_id": dispute_id,
        "ml_scores": ml_scores,
        "verdict": verdict,
    }
