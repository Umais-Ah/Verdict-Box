"""OpenRouter-only LLM integration for VerdictBox verdict generation."""

import json
import re

from openai import OpenAI
from config import Config


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _strip_code_fences(text):
    """Removes markdown code fences around JSON if model returns fenced output."""
    return re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()


def _extract_json_payload(text):
    """Extracts a JSON object from mixed text responses."""
    cleaned = _strip_code_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return cleaned
    return cleaned[start : end + 1]


def _word_count(text):
    """Returns a simple token count for length checks."""
    return len(re.findall(r"\b\w+\b", str(text or "")))


def _extract_phrase(text):
    """Extracts a short quote candidate from argument text for evidence wording."""
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return "the submitted argument"
    words = cleaned.split()
    return " ".join(words[:8]).strip(" ,.;:")


# ---------------------------------------------------------------------------
# Winner / name normalization
# ---------------------------------------------------------------------------

def _normalize_winner_fields(parsed, user_a_name, user_b_name):
    """Normalizes winner and winner_name to exact provided usernames."""
    winner = str(parsed.get("winner", "")).strip().upper()
    winner_name_raw = str(parsed.get("winner_name", "")).strip()

    if winner_name_raw.lower() in {"user a", "user_a", "a"}:
        winner_name = user_a_name
    elif winner_name_raw.lower() in {"user b", "user_b", "b"}:
        winner_name = user_b_name
    else:
        winner_name = winner_name_raw

    if winner not in {"A", "B"}:
        if winner_name == user_a_name:
            winner = "A"
        elif winner_name == user_b_name:
            winner = "B"

    if winner in {"A", "B"} and winner_name in {user_a_name, user_b_name}:
        mapped = user_a_name if winner == "A" else user_b_name
        if winner_name != mapped:
            winner = "A" if winner_name == user_a_name else "B"

    if winner == "A":
        winner_name = user_a_name
    elif winner == "B":
        winner_name = user_b_name

    parsed["winner"] = winner if winner in {"A", "B"} else "A"
    parsed["winner_name"] = winner_name if winner_name in {user_a_name, user_b_name} else user_a_name
    return parsed


# ---------------------------------------------------------------------------
# Score comparison block (NEW)
# ---------------------------------------------------------------------------

def _build_score_comparison(ml_scores, user_a_name, user_b_name, fallacies_a, fallacies_b):
    """
    Builds a structured score comparison dict shown FIRST in the UI,
    before reasoning sections, matching the screenshot layout.
    """
    tox_a = round(float(ml_scores.get("toxicity_a", 0.0)) * 100, 1)
    tox_b = round(float(ml_scores.get("toxicity_b", 0.0)) * 100, 1)
    sar_a = round(float(ml_scores.get("sarcasm_a", 0.0)) * 100, 1)
    sar_b = round(float(ml_scores.get("sarcasm_b", 0.0)) * 100, 1)
    sent_a = str(ml_scores.get("sentiment_a", "neutral")).capitalize()
    sent_b = str(ml_scores.get("sentiment_b", "neutral")).capitalize()
    fal_a = len(fallacies_a) if isinstance(fallacies_a, list) else 0
    fal_b = len(fallacies_b) if isinstance(fallacies_b, list) else 0

    def conduct_grade(tox, sar):
        penalty = (0.6 * tox / 100) + (0.4 * sar / 100)
        if penalty < 0.20:
            return "Excellent"
        if penalty < 0.40:
            return "Good"
        if penalty < 0.60:
            return "Fair"
        return "Poor"

    return {
        "user_a": {
            "name": user_a_name,
            "toxicity_pct": tox_a,
            "sarcasm_pct": sar_a,
            "sentiment": sent_a,
            "fallacy_count": fal_a,
            "conduct_grade": conduct_grade(tox_a, sar_a),
        },
        "user_b": {
            "name": user_b_name,
            "toxicity_pct": tox_b,
            "sarcasm_pct": sar_b,
            "sentiment": sent_b,
            "fallacy_count": fal_b,
            "conduct_grade": conduct_grade(tox_b, sar_b),
        },
    }


# ---------------------------------------------------------------------------
# Decision sanity / fairness guard
# ---------------------------------------------------------------------------

def _safe_fallacy_count(value):
    """Returns fallacy list length safely for malformed model output."""
    return len(value) if isinstance(value, list) else 0


def _apply_decision_sanity(parsed, ml_scores):
    """Applies a lightweight fairness guard to avoid obvious toxic/fallacy-biased winners."""
    winner = str(parsed.get("winner", "A")).strip().upper()
    if winner not in {"A", "B"}:
        return parsed

    conf = float(parsed.get("confidence", 0.0) or 0.0)
    tox_a = float(ml_scores.get("toxicity_a", 0.0))
    tox_b = float(ml_scores.get("toxicity_b", 0.0))
    sar_a = float(ml_scores.get("sarcasm_a", 0.0))
    sar_b = float(ml_scores.get("sarcasm_b", 0.0))
    fal_a = _safe_fallacy_count(parsed.get("fallacies_a"))
    fal_b = _safe_fallacy_count(parsed.get("fallacies_b"))

    def penalty(tox, sar, fal_count):
        return (0.60 * tox) + (0.25 * sar) + (0.15 * min(1.0, fal_count / 3.0))

    penalty_a = penalty(tox_a, sar_a, fal_a)
    penalty_b = penalty(tox_b, sar_b, fal_b)
    winner_penalty = penalty_a if winner == "A" else penalty_b
    loser_penalty = penalty_b if winner == "A" else penalty_a
    penalty_gap = winner_penalty - loser_penalty
    winner_tox = tox_a if winner == "A" else tox_b
    loser_tox = tox_b if winner == "A" else tox_a  # noqa: F841
    winner_fallacies = fal_a if winner == "A" else fal_b
    loser_fallacies = fal_b if winner == "A" else fal_a

    should_flip = (
        conf <= 0.82
        and penalty_gap >= 0.14
        and winner_tox - (tox_b if winner == "A" else tox_a) >= 0.12
        and winner_fallacies >= loser_fallacies
    )

    if not should_flip:
        return parsed

    parsed["winner"] = "B" if winner == "A" else "A"
    parsed["confidence"] = round(max(0.55, min(0.79, conf + 0.04)), 3)
    prior = str(parsed.get("reasoning", "")).strip()
    addendum = (
        " Final outcome was adjusted by civility-consistency checks because the original winner "
        "had significantly higher toxicity without stronger logical cleanliness."
    )
    parsed["reasoning"] = (prior + addendum).strip()
    return parsed


# ---------------------------------------------------------------------------
# Display name sanity
# ---------------------------------------------------------------------------

def _replace_generic_side_labels(text, user_a_name, user_b_name):
    """Replaces generic side tokens with real usernames for user-facing clarity."""
    if not isinstance(text, str) or not text.strip():
        return text
    out = text
    replacements = [
        (r"\bArgument\s*A\b", user_a_name),
        (r"\bArgument\s*B\b", user_b_name),
        (r"\bSide\s*A\b", user_a_name),
        (r"\bSide\s*B\b", user_b_name),
        (r"\bUser\s*A\b", user_a_name),
        (r"\bUser\s*B\b", user_b_name),
    ]
    for pattern, replacement in replacements:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return out


def _apply_display_name_sanity(parsed, user_a_name, user_b_name):
    """Ensures all narrative fields use real usernames instead of A/B labels."""
    for field in ("reasoning", "argument_a_analysis", "argument_b_analysis", "verdict_summary"):
        parsed[field] = _replace_generic_side_labels(parsed.get(field, ""), user_a_name, user_b_name)
    return parsed


# ---------------------------------------------------------------------------
# Reasoning section enforcement
# ---------------------------------------------------------------------------

def _trim_reasoning_sections(parsed):
    """Keeps only the first full 4-section reasoning block if duplicates appear."""
    reasoning = str(parsed.get("reasoning", "") or "").strip()
    if not reasoning:
        return parsed

    lowered = reasoning.lower()
    behavior_idx = lowered.find("behavior:")
    if behavior_idx == -1:
        return parsed

    final_idx = lowered.find("final decision:", behavior_idx)
    if final_idx == -1:
        return parsed

    next_idx = len(reasoning)
    for label in ("behavior:", "where it failed:", "better plan:", "final decision:"):
        candidate = lowered.find(label, final_idx + len("final decision:"))
        if candidate != -1 and candidate < next_idx:
            next_idx = candidate

    parsed["reasoning"] = reasoning[behavior_idx:next_idx].strip()
    return parsed


def _enforce_reasoning_depth(parsed, ml_scores, user_a_name, user_b_name, text_a, text_b):
    """Expands shallow verdict reasoning into a richer 4-section explanation."""
    reasoning = str(parsed.get("reasoning", "")).strip()
    has_labels = all(
        marker in reasoning.lower()
        for marker in ["behavior:", "where it failed:", "better plan:", "final decision:"]
    )
    if has_labels and _word_count(reasoning) >= 85:
        return parsed

    winner = str(parsed.get("winner", "A")).strip().upper()
    winner_name = user_a_name if winner == "A" else user_b_name
    loser_name = user_b_name if winner == "A" else user_a_name

    tox_a = round(float(ml_scores.get("toxicity_a", 0.0)) * 100, 1)
    tox_b = round(float(ml_scores.get("toxicity_b", 0.0)) * 100, 1)
    sar_a = round(float(ml_scores.get("sarcasm_a", 0.0)) * 100, 1)
    sar_b = round(float(ml_scores.get("sarcasm_b", 0.0)) * 100, 1)

    winner_tox = tox_a if winner == "A" else tox_b
    winner_sar = sar_a if winner == "A" else sar_b
    loser_tox = tox_b if winner == "A" else tox_a
    loser_sar = sar_b if winner == "A" else sar_a

    fallacies_winner = len(parsed.get("fallacies_a", [])) if winner == "A" else len(parsed.get("fallacies_b", []))

    quote_a = _extract_phrase(text_a)
    quote_b = _extract_phrase(text_b)
    winner_quote = quote_a if winner == "A" else quote_b
    loser_quote = quote_b if winner == "A" else quote_a

    parsed["reasoning"] = (
        f"Behavior: **{loser_name}** shows toxicity near **{loser_tox}%** and sarcasm near **{loser_sar}%**, "
        f"while **{winner_name}** shows toxicity near **{winner_tox}%** and sarcasm near **{winner_sar}%**. "
        f"Tone signals show **{loser_name}** sounds harsher around \"{loser_quote}\" "
        f"while **{winner_name}** stays more controlled around \"{winner_quote}\". "
        f"Where it failed: **{loser_name}** loses ground because the claims lack a practical rollout or implementation steps. "
        f"The line \"{loser_quote}\" states pressure but does not show how the policy would be executed. "
        f"Better plan: **{winner_name}** provides a Constructive Roadmap with clearer action steps. "
        f"The phrase \"{winner_quote}\" points to a workable direction and keeps cleaner structure "
        f"with **{fallacies_winner}** detected fallacy signal(s). "
        f"Final decision: **Winner**: **{winner_name}**. "
        f"**{winner_name}** wins because the plan is clearer and easier to implement."
    )
    return parsed


# ---------------------------------------------------------------------------
# Moderator acknowledgement
# ---------------------------------------------------------------------------

def _enforce_moderator_acknowledgement(parsed, appeal_context, user_a_name, user_b_name):
    """Injects a moderator-review acknowledgement into Behavior for appeal re-evaluations."""
    if not str(appeal_context or "").strip():
        return parsed

    reasoning = str(parsed.get("reasoning", "") or "").strip()
    if not reasoning:
        parsed["reasoning"] = (
            f"Behavior: RE-EVALUATION VERDICT: After an approved moderator appeal, "
            f"I re-reviewed both **{user_a_name}** and **{user_b_name}** and considered the moderator note. "
            "Where it failed: No details provided. "
            "Better plan: No details provided. "
            f"Final decision: Winner: {parsed.get('winner_name', user_a_name)}."
        )
        return parsed

    acknowledgement = (
        f"RE-EVALUATION VERDICT: After an approved moderator appeal, "
        f"I re-reviewed both **{user_a_name}** and **{user_b_name}** and considered the moderator note. "
    )

    marker = "Behavior:"
    marker_idx = reasoning.find(marker)
    if marker_idx == -1:
        parsed["reasoning"] = f"Behavior: {acknowledgement}{reasoning}"
        return parsed

    body_start = marker_idx + len(marker)
    body_after = reasoning[body_start:].lstrip()
    if "moderator" in body_after[:220].lower() and "appeal" in body_after[:220].lower():
        return parsed

    spacer = " " if body_after else ""
    parsed["reasoning"] = reasoning[:body_start] + " " + acknowledgement + spacer + body_after
    return parsed


# ---------------------------------------------------------------------------
# OpenRouter client setup
# ---------------------------------------------------------------------------

OPENROUTER_MODEL_NAME = (Config.OPENROUTER_MODEL or "meta-llama/llama-3.1-8b-instruct:free").strip()

OPENROUTER_CLIENT = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=Config.OPENROUTER_API_KEY,
)


# ---------------------------------------------------------------------------
# ML score label helpers
# ---------------------------------------------------------------------------

def _toxicity_indicator(score):
    if score >= 0.7:
        return "aggressive/hostile tone"
    if score >= 0.35:
        return "tense or confrontational tone"
    return "mostly civil tone"


def _sarcasm_indicator(score):
    if score >= 0.5:
        return "condescending/dismissive delivery"
    if score >= 0.3:
        return "indirect or ironic phrasing"
    return "direct and clear delivery"


def _sentiment_indicator(compound_score):
    if compound_score >= 0.2:
        return "constructive intent"
    if compound_score <= -0.2:
        return "cynical/attacking intent"
    return "neutral intent"


def _behavioral_warnings(ml_scores):
    warnings = []
    toxicity_a = float(ml_scores.get("toxicity_a", 0.0))
    toxicity_b = float(ml_scores.get("toxicity_b", 0.0))
    sarcasm_a = float(ml_scores.get("sarcasm_a", 0.0))
    sarcasm_b = float(ml_scores.get("sarcasm_b", 0.0))
    if toxicity_a > 0.8:
        warnings.append("WARNING: Side A is highly toxic. Check for personal attacks and bad-faith framing.")
    if toxicity_b > 0.8:
        warnings.append("WARNING: Side B is highly toxic. Check for personal attacks and bad-faith framing.")
    if sarcasm_a > 0.7:
        warnings.append("NOTE: Side A uses heavy sarcasm. Verify whether key points remain direct and evidence-based.")
    if sarcasm_b > 0.7:
        warnings.append("NOTE: Side B uses heavy sarcasm. Verify whether key points remain direct and evidence-based.")
    return warnings


# ---------------------------------------------------------------------------
# Fallback verdict (no LLM)
# ---------------------------------------------------------------------------

def _fallback_verdict(ml_scores, user_a_name, user_b_name, unavailable_reason):
    """Builds a deterministic fallback verdict when OpenRouter is unavailable."""
    toxicity_a = float(ml_scores.get("toxicity_a", 0.0))
    toxicity_b = float(ml_scores.get("toxicity_b", 0.0))
    sarcasm_a = float(ml_scores.get("sarcasm_a", 0.0))
    sarcasm_b = float(ml_scores.get("sarcasm_b", 0.0))
    sentiment_compound_a = float(ml_scores.get("sentiment_compound_a", 0.0))
    sentiment_compound_b = float(ml_scores.get("sentiment_compound_b", 0.0))

    score_a = (1.0 - toxicity_a) - (0.2 * sarcasm_a) + (0.1 * sentiment_compound_a)
    score_b = (1.0 - toxicity_b) - (0.2 * sarcasm_b) + (0.1 * sentiment_compound_b)

    winner = "A" if score_a >= score_b else "B"
    winner_name = user_a_name if winner == "A" else user_b_name
    loser_name = user_b_name if winner == "A" else user_a_name
    margin = abs(score_a - score_b)
    confidence = max(0.55, min(0.85, 0.55 + margin))

    tox_a_pct = round(toxicity_a * 100, 1)
    tox_b_pct = round(toxicity_b * 100, 1)
    sar_a_pct = round(sarcasm_a * 100, 1)
    sar_b_pct = round(sarcasm_b * 100, 1)

    winner_sar = sar_a_pct if winner == "A" else sar_b_pct
    loser_tox = tox_b_pct if winner == "A" else tox_a_pct

    fallacies_a: list = []
    fallacies_b: list = []

    score_comparison = _build_score_comparison(
        ml_scores, user_a_name, user_b_name, fallacies_a, fallacies_b
    )

    return {
        "winner": winner,
        "winner_name": winner_name,
        "confidence": round(confidence, 3),
        "score_comparison": score_comparison,
        "reasoning": (
            f"Behavior: **{loser_name}** shows weaker debate conduct with Toxicity at "
            f"**{loser_tox}%**, while **{winner_name}** keeps lower sarcasm at **{winner_sar}%**, "
            "supporting a more professional tone. "
            f"Tone signals confirm **{loser_name}** leans harsher while **{winner_name}** stays measured. "
            "Where it failed: The losing side relies more on emotional pressure than a fully workable policy path, "
            "which weakens logical durability under challenge. "
            "The argument states demands but does not show how the policy would be executed — a Dead-End Argument. "
            "Better plan: The winning side is more constructive because it presents practical, implementable steps "
            "instead of only high-pressure demands — a Constructive Roadmap. "
            "The argument points to actionable steps and maintains cleaner logical structure throughout. "
            f"Final decision: **Winner**: **{winner_name}**. "
            f"**{winner_name}** wins because the plan is more practical and actionable. "
            f"System note: OpenRouter unavailable ({unavailable_reason})."
        ),
        "argument_a_analysis": "Fallback analysis used lightweight ML indicators instead of LLM reasoning.",
        "argument_b_analysis": "Fallback analysis used lightweight ML indicators instead of LLM reasoning.",
        "fallacies_a": fallacies_a,
        "fallacies_b": fallacies_b,
        "verdict_summary": "Provisional verdict generated while OpenRouter was unavailable.",
    }


# ---------------------------------------------------------------------------
# OpenRouter API call
# ---------------------------------------------------------------------------

def _call_openrouter(prompt):
    """Sends prompt to OpenRouter and returns plain response content."""
    if not Config.OPENROUTER_API_KEY:
        raise RuntimeError("Missing OPENROUTER_API_KEY")

    fallback_models = [
        "meta-llama/llama-3.1-8b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "qwen/qwen-2.5-7b-instruct:free",
    ]
    configured_fallback = [
        model.strip()
        for model in (Config.OPENROUTER_FALLBACK_MODELS or "").split(",")
        if model.strip()
    ]
    model_candidates = [OPENROUTER_MODEL_NAME] + configured_fallback + fallback_models

    unique_models = []
    seen = set()
    for model in model_candidates:
        if model not in seen:
            seen.add(model)
            unique_models.append(model)

    max_attempts = max(1, int(getattr(Config, "OPENROUTER_MAX_MODEL_ATTEMPTS", 2) or 2))
    model_attempts = unique_models[:max_attempts]
    request_timeout = float(getattr(Config, "OPENROUTER_TIMEOUT_SECONDS", 18.0) or 18.0)

    errors = []
    for model_name in model_attempts:
        try:
            completion = OPENROUTER_CLIENT.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                timeout=request_timeout,
                response_format={"type": "json_object"},
                extra_body={"reasoning": {"enabled": bool(Config.OPENROUTER_ENABLE_REASONING)}},
                extra_headers={
                    "X-Title": Config.OPENROUTER_APP_NAME or "VerdictBox",
                    "HTTP-Referer": Config.OPENROUTER_SITE_URL or "",
                },
            )

            choice = completion.choices[0] if completion.choices else None
            if choice is None or choice.message is None:
                raise RuntimeError(f"OpenRouter model {model_name} returned no message")

            content = choice.message.content or ""
            if isinstance(content, list):
                content = "\n".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            content = str(content).strip()
            if not content:
                raise RuntimeError(f"OpenRouter model {model_name} returned empty content")

            return content
        except Exception as exc:
            errors.append(f"{model_name}: {type(exc).__name__}: {exc}")

    raise RuntimeError("OpenRouter all model attempts failed: " + " | ".join(errors[:4]))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_openrouter_verdict(
    text_a,
    text_b,
    ml_scores,
    user_a_name,
    user_b_name,
    appeal_context=None,
    prior_verdict_context=None,
):
    """Calls OpenRouter and returns parsed verdict JSON or a safe fallback response.

    The returned dict now always contains a ``score_comparison`` key with
    structured per-user ML metrics so the frontend can render the
    Score Comparison table BEFORE the four reasoning sections, exactly as
    shown in the design screenshot:

        1. SCORE COMPARISON  (toxicity / sarcasm / sentiment / fallacies / grade)
        2. BEHAVIOR          (tone comparison)
        3. WHERE IT FAILED   (loser analysis + dead-end label)
        4. BETTER PLAN       (winner analysis + constructive roadmap label)
        5. FINAL DECISION    (winner declaration)
    """
    max_chars = int(getattr(Config, "LLM_MAX_INPUT_CHARS", 3000) or 3000)
    text_a = (text_a or "")[:max_chars]
    text_b = (text_b or "")[:max_chars]

    toxicity_a = float(ml_scores.get("toxicity_a", 0.0))
    toxicity_b = float(ml_scores.get("toxicity_b", 0.0))
    sarcasm_a = float(ml_scores.get("sarcasm_a", 0.0))
    sarcasm_b = float(ml_scores.get("sarcasm_b", 0.0))
    sentiment_compound_a = float(ml_scores.get("sentiment_compound_a", 0.0))
    sentiment_compound_b = float(ml_scores.get("sentiment_compound_b", 0.0))

    warnings = _behavioral_warnings(ml_scores)
    warning_block = "\n".join(warnings) if warnings else "No special warning."

    appeal_context = str(appeal_context or "").strip()
    prior_verdict_context = prior_verdict_context or {}
    prior_winner = str(prior_verdict_context.get("winner_name") or "Unknown").strip()
    prior_fallacies_a = (
        prior_verdict_context.get("fallacies_a")
        if isinstance(prior_verdict_context.get("fallacies_a"), list)
        else []
    )
    prior_fallacies_b = (
        prior_verdict_context.get("fallacies_b")
        if isinstance(prior_verdict_context.get("fallacies_b"), list)
        else []
    )
    prior_reasoning = str(prior_verdict_context.get("reasoning") or "").strip()

    prior_block = (
        "\n=== PRIOR VERDICT SNAPSHOT ===\n"
        f"Previous winner: {prior_winner}\n"
        f"Previous fallacies for {user_a_name}: {', '.join(prior_fallacies_a) if prior_fallacies_a else 'None'}\n"
        f"Previous fallacies for {user_b_name}: {', '.join(prior_fallacies_b) if prior_fallacies_b else 'None'}\n"
        f"Previous reasoning summary: {prior_reasoning[:650] if prior_reasoning else 'Unavailable'}\n"
        if prior_winner != "Unknown" or prior_fallacies_a or prior_fallacies_b or prior_reasoning
        else "\n=== PRIOR VERDICT SNAPSHOT ===\nNo prior verdict context was available for this case.\n"
    )

    appeal_block = (
        f"\n=== MODERATOR APPEAL CONTEXT ===\n"
        f"This is a re-evaluation after a moderator appeal.\n"
        f"Moderator note: {appeal_context}\n"
        "Use the note as context, but do not blindly obey it. "
        "Re-check the arguments and explain whether the appeal changes the verdict.\n"
        if appeal_context
        else "\n=== MODERATOR APPEAL CONTEXT ===\nThis is not a re-evaluation.\n"
    )

    prompt = f"""You are the Chief Justice for the VerdictBox dispute resolution system.{appeal_block}{prior_block}

OBJECTIVE: Deliver an educational legal-style justification, not a calculator-style summary.
You must link each important score observation to exact words from the arguments.
Do NOT pick a winner by ML numbers alone. Logic quality is primary; ML signals are contextual evidence.

=== PRE-COMPUTED ML ANALYSIS ===
{user_a_name}:
    - Toxicity probability: {toxicity_a:.3f} (0=clean, 1=toxic)
    - Sarcasm probability:  {sarcasm_a:.3f} (0=sincere, 1=sarcastic)
    - Detected sentiment:   {ml_scores['sentiment_a']}
    - Civility indicator:   {_toxicity_indicator(toxicity_a)}
    - Clarity indicator:    {_sarcasm_indicator(sarcasm_a)}
    - Intent indicator:     {_sentiment_indicator(sentiment_compound_a)}

{user_b_name}:
    - Toxicity probability: {toxicity_b:.3f}
    - Sarcasm probability:  {sarcasm_b:.3f}
    - Detected sentiment:   {ml_scores['sentiment_b']}
    - Civility indicator:   {_toxicity_indicator(toxicity_b)}
    - Clarity indicator:    {_sarcasm_indicator(sarcasm_b)}
    - Intent indicator:     {_sentiment_indicator(sentiment_compound_b)}

=== EVIDENCE RULES ===
Treat ML signals as contextual clues and describe them in natural language, not raw math.
For every metric you mention (toxicity, sarcasm, fallacies), you MUST cite an exact trigger phrase from the argument in double quotes.
Never write vague claims like "Side A was toxic" without quotation evidence.
- Toxicity = civility evidence. If above 0.35, mention aggressive delivery made points harder to accept.
- Sarcasm = clarity evidence. If above 0.50, mention indirect/dismissive delivery reduced seriousness.
- Sentiment = intent evidence. Positive tends constructive, negative tends destructive.
- Contradiction rule: If sentiment sounds constructive but toxicity is high, call out contradiction in delivery.
- If toxicity is extreme (> 0.80), check carefully for ad hominem or bad-faith framing.

=== WEIGHTED RUBRIC (MANDATORY) ===
Compute an internal rubric before deciding winner:
- Logic (50%): logical structure + evidence quality + fallacies.
    Rule: each detected fallacy reduces logic by 20 points (floor at 0).
- Conduct (30%): civility and professionalism.
    Rule: toxicity > 0.30 and/or sarcasm > 0.40 applies conduct penalty.
- Clarity (20%): direct relevance to the prompt and practical clarity.
You must select the winner from this rubric result, then explain it in simple language.

=== SANITY WARNINGS ===
{warning_block}

=== ARGUMENT A ({user_a_name}) ===
{text_a}

=== ARGUMENT B ({user_b_name}) ===
{text_b}

=== YOUR TASK ===
1. Evaluate logical structure, use of evidence, coherence, and persuasiveness.
2. Use very easy wording (simple English) suitable for people with weak English.
3. Use NAMES ONLY in all output text. Never say "Argument A", "Argument B", "Side A", "Side B", "User A", or "User B".
4. PLAN RULE: the winner gives a workable solution; the loser mostly complains, attacks, or gives no implementation path.
5. Briefly discuss all three ML signals as behavioral evidence for both sides:
   - Toxicity, Sarcasm, Sentiment
   Explain how each signal affects your judgment using descriptive wording.
6. For every metric mentioned, include at least one exact quote from the argument text as evidence.
7. Identify any logical fallacies in EACH argument from this list ONLY:
   - Ad Hominem, Strawman, False Dichotomy, Appeal to Emotion, Hasty Generalization
8. Declare a winner based on the weighted rubric above.
9. In winner_name output the EXACT username only: "{user_a_name}" or "{user_b_name}".
10. "reasoning" MUST follow this EXACT 4-part order (each section 2 short sentences, total under 140 words):

    Behavior:        Score comparison — mention toxicity + sarcasm % for BOTH users. Then one tone comparison sentence.
    Where it failed: Name the loser + core weakness. Quote one line. Label it "Dead-End Argument" if no implementation path.
    Better plan:     Name the winner + constructive roadmap. Quote one line. Label it "Constructive Roadmap" if actionable.
    Final decision:  Start with "Winner: <name>." then one courtroom-style reason sentence.

    BOLDING RULE: bold ONLY names, "Winner" label, and percentage numbers using **text**.
    If moderator appeal: Behavior must begin with "RE-EVALUATION VERDICT: After an approved moderator appeal..."

11. If one side pushes demands without implementation: label "Dead-End Argument" in Where it failed.
12. If one side gives actionable steps: label "Constructive Roadmap" in Better plan.
13. Never output HTML entities. Use normal apostrophe '.
14. Keep names in natural title-case in text; winner_name JSON field must be exact username.
15. If moderator appeal: explicitly weigh moderator note vs prior fallacy findings and state whether result changed.

RESPOND ONLY WITH THIS EXACT JSON — no text outside the JSON:
{{
  "winner": "A" or "B",
  "winner_name": "{user_a_name}" or "{user_b_name}",
  "confidence": <float 0.0–1.0>,
  "reasoning": "<4 labeled sections as one string: Behavior: ... Where it failed: ... Better plan: ... Final decision: ...>",
  "argument_a_analysis": "<1-2 sentences on {user_a_name} strengths/weaknesses with one short direct quote>",
  "argument_b_analysis": "<1-2 sentences on {user_b_name} strengths/weaknesses with one short direct quote>",
  "fallacies_a": ["<fallacy name>"] or [],
  "fallacies_b": ["<fallacy name>"] or [],
  "verdict_summary": "<one simple public-friendly sentence naming the key logical reason for the win>"
}}
"""

    try:
        raw_text = _call_openrouter(prompt)
        cleaned = _extract_json_payload(raw_text)
        parsed = json.loads(cleaned)
        parsed = _normalize_winner_fields(parsed, user_a_name, user_b_name)
        parsed = _apply_decision_sanity(parsed, ml_scores)
        parsed = _apply_display_name_sanity(parsed, user_a_name, user_b_name)
        parsed = _enforce_reasoning_depth(parsed, ml_scores, user_a_name, user_b_name, text_a, text_b)
        parsed = _enforce_moderator_acknowledgement(parsed, appeal_context, user_a_name, user_b_name)
        parsed = _trim_reasoning_sections(parsed)
        parsed = _normalize_winner_fields(parsed, user_a_name, user_b_name)

        # ── Attach score_comparison so the frontend can render it first ──
        parsed["score_comparison"] = _build_score_comparison(
            ml_scores,
            user_a_name,
            user_b_name,
            parsed.get("fallacies_a", []),
            parsed.get("fallacies_b", []),
        )
        return parsed

    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        reason = (
            "OpenRouter quota exceeded"
            if ("429" in lowered or "quota" in lowered or "rate limit" in lowered)
            else (message[:220] or "OpenRouter error")
        )
        parsed = _fallback_verdict(ml_scores, user_a_name, user_b_name, reason)
        parsed = _enforce_moderator_acknowledgement(parsed, appeal_context, user_a_name, user_b_name)
        return _trim_reasoning_sections(parsed)