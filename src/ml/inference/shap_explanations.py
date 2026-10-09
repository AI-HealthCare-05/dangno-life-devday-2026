"""Versioned research Shapley explanations, independent of public approval."""

from math import comb

import numpy as np
import pandas as pd

from src.ml.inference.model_explanations import DISPLAY_NAMES, MODIFIABLE


def has_displayable_selection(explanation):
    """A missing opposite sign is valid; empty or invalid attributions are not."""
    items = explanation.get("items")
    if explanation.get("selection_status") not in {"complete", "insufficient_directional_factors"}:
        return False
    if not isinstance(items, list) or not 1 <= len(items) <= 3:
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        value = item.get("contribution")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
            return False
        if abs(value) <= 1e-10 or item.get("direction") != ("increase" if value > 0 else "decrease"):
            return False
    return True


def select_factors(items, *, elevated):
    """Select up to three real attributions; never manufacture the other sign."""
    if type(elevated) is not bool:
        raise ValueError("A validated binary/elevated result is required")
    groups = {}
    for direction in ("increase", "decrease"):
        groups[direction] = sorted(
            (
                item
                for item in items
                if item["direction"] == direction
                and np.isfinite(item["contribution"])
                and abs(item["contribution"]) > 1e-10
            ),
            key=lambda item: (-abs(item["contribution"]), item["feature"]),
        )
    first, second = ("increase", "decrease") if elevated else ("decrease", "increase")
    return groups[first][:2] + groups[second][:1]


def _result(values, *, reference, score, method, baseline, model_version, elevated):
    if not np.isfinite([reference, score, *values.values()]).all():
        raise ValueError("Nonfinite SHAP explanation")
    if not np.isclose(reference + sum(values.values()), score, atol=1e-8, rtol=0):
        raise ValueError("SHAP additivity failed")
    # Serializes deterministically despite last-bit parallel RF reduction jitter.
    values = {feature: round(float(value), 12) for feature, value in values.items()}
    reference, score = round(float(reference), 12), round(float(score), 12)
    items = []
    for feature, value in values.items():
        direction = "increase" if value > 0 else "decrease" if value < 0 else "neutral"
        items.append(
            {
                "feature": feature,
                "display_name": DISPLAY_NAMES.get(feature, feature),
                "direction": direction,
                "display_group": "caution" if value > 0 else "positive" if value < 0 else "neutral",
                "contribution": float(value),
                "absolute_contribution": abs(float(value)),
                "modifiable": feature in MODIFIABLE,
                "message": "입력 정보가 비교 기준 대비 모델 점수를 "
                + ("높이는" if value > 0 else "낮추는" if value < 0 else "바꾸지 않는")
                + " 방향으로 반영되었습니다.",
            }
        )
    selected = select_factors(items, elevated=elevated)
    return {
        "status": "research_only",
        "display_allowed": False,
        "method": method,
        "explanation_version": "three-factor-shap-v1",
        "model_version": model_version,
        "output_space": "risk_score",
        "reference_value": float(reference),
        "score": float(score),
        "baseline_definition": baseline,
        "additive_to_score": True,
        "additivity_verified": True,
        "shap_claimed": True,
        "selection_policy": "elevated-2-caution-1-positive-otherwise-2-positive-1-caution-v1",
        "selection_status": "complete" if len(selected) == 3 else "insufficient_directional_factors",
        "items": selected,
        "all_items": items,
        "other_contribution": round(sum(values.values()) - sum(i["contribution"] for i in selected), 12),
        "limitations": [
            "not causal",
            "not a diagnosis",
            "correlated features affect attribution",
            "selected items alone do not sum to the score",
        ],
    }


def _today_groups(frame):
    dependent_groups = {
        "body_measurements": ("height_cm", "weight_kg", "waist_cm", "bmi"),
        "blood_pressure": ("systolic_bp", "diastolic_bp"),
        "family_history": ("diabetes_family_history", "hypertension_family_history"),
    }
    grouped_features = {feature for features in dependent_groups.values() for feature in features}
    groups = {c: [c] for c in frame if c not in grouped_features}
    for group_name, features in dependent_groups.items():
        present = [feature for feature in features if feature in frame]
        if present:
            groups[group_name] = present
    return groups


def _validate_today_reference(frame, background):
    if list(background.columns) != list(frame.columns) or not 1 <= len(background) <= 256:
        raise ValueError("Invalid Train reference shape")
    if np.isinf(background.to_numpy(dtype=float)).any() or background.isna().all(axis=1).any():
        raise ValueError("Invalid Train reference values")


def _today_reference_scores(frame, score_batch, background, groups, names):
    n = len(names)
    # Each masked group is replaced by the same real reference person's group.
    # Chunk coalitions to bound memory; keep the complete frozen model intact.
    averages = []
    reference_values = background.to_numpy(dtype=float)
    input_values = frame.to_numpy(dtype=float)[0]
    positions = {name: [frame.columns.get_loc(c) for c in columns] for name, columns in groups.items()}
    for start in range(0, 1 << n, 32):
        batches = []
        for mask in range(start, min(start + 32, 1 << n)):
            candidates = reference_values.copy()
            for j, name in enumerate(names):
                if mask & (1 << j):
                    candidates[:, positions[name]] = input_values[positions[name]]
            batches.append(candidates)
        batch_frame = pd.DataFrame(np.concatenate(batches, axis=0), columns=frame.columns)
        batch_scores = np.asarray(score_batch(batch_frame), dtype=float)
        if batch_scores.shape != (len(batches) * len(background),):
            raise ValueError("Invalid reference coalition scores")
        averages.extend(batch_scores.reshape(len(batches), len(background)).mean(axis=1))
    return np.asarray(averages, dtype=float)


def explain_today(frame, score_batch, *, model_version, elevated, background=None):
    """Exact grouped Shapley values over all input-group coalitions.

    Production uses a fixed Train-only empirical reference. Omitting background
    retains the legacy all-missing reference for research comparisons only.
    Related measurements form one player. Every coalition passes through the
    complete frozen pipeline without refitting preprocessing or models.
    """
    if len(frame) != 1 or len(frame.columns) > 14:
        raise ValueError("Today requires one row with at most fourteen features")
    groups = _today_groups(frame)
    names = list(groups)
    n = len(names)
    if n > 10:
        raise ValueError("Today grouped SHAP requires at most ten independent input groups")
    if background is not None:
        _validate_today_reference(frame, background)
    rows = []
    for mask in range(1 << n):
        rows.append(
            {
                c: frame.iloc[0][c]
                if any(mask & (1 << j) and c in groups[name] for j, name in enumerate(names))
                else np.nan
                for c in frame
            }
        )
    if background is None:
        scores = np.asarray(score_batch(pd.DataFrame(rows, columns=frame.columns)), dtype=float)
    else:
        scores = _today_reference_scores(frame, score_batch, background, groups, names)
    if scores.shape != (1 << n,) or not np.isfinite(scores).all():
        raise ValueError("Invalid coalition scores")
    values = {}
    for j, name in enumerate(names):
        values[name] = sum(
            (scores[mask | (1 << j)] - scores[mask]) / (n * comb(n - 1, mask.bit_count()))
            for mask in range(1 << n)
            if not mask & (1 << j)
        )
    result = _result(
        values,
        reference=scores[0],
        score=scores[-1],
        method="exact_grouped_shap_train_reference_v2"
        if background is not None
        else "exact_grouped_shap_missing_reference_v1",
        baseline="mean model output over the fixed Train-only representative reference; grouped replacements"
        if background is not None
        else "all input groups missing; frozen Train-fitted preprocessing; not population average",
        model_version=model_version,
        elevated=elevated,
    )
    if background is not None:
        result["explanation_version"] = "grouped-train-reference-shap-v2"
        result["background_size"] = len(background)
    return result


def explain_tomorrow(frame, pipeline, *, model_version, elevated):
    """Positive-class RF TreeSHAP with one-hot/indicator aggregation."""
    import shap

    if len(frame) != 1:
        raise ValueError("TreeSHAP requires exactly one row")
    preprocessing = pipeline.named_steps["preprocessing"]
    classifier = pipeline.named_steps["classifier"]
    positive = list(classifier.classes_).index(1)
    transformed = preprocessing.transform(frame)
    explanation = shap.TreeExplainer(classifier, feature_perturbation="tree_path_dependent")(transformed)
    raw = explanation.values[0, :, positive]
    grouped = dict.fromkeys(frame.columns, 0.0)
    for name, value in zip(preprocessing.get_feature_names_out(), raw, strict=True):
        name = name.split("__", 1)[-1].removeprefix("missingindicator_")
        matches = [feature for feature in frame if name == feature or name.startswith(feature + "_")]
        if not matches:
            raise ValueError("Unmapped transformed feature")
        grouped[max(matches, key=len)] += float(value)
    result = _result(
        grouped,
        reference=explanation.base_values[0, positive],
        score=pipeline.predict_proba(frame)[0, positive],
        method="treeshap_tree_path_dependent_v1",
        baseline="training path counts in frozen RF trees",
        model_version=model_version,
        elevated=elevated,
    )
    result["explainer_library_version"] = shap.__version__
    return result


def safe_explanation(explain, *args, **kwargs):
    """XAI failure must not discard a successful prediction or expose internals."""
    try:
        return explain(*args, **kwargs)
    except Exception:
        return {
            "status": "unavailable",
            "display_allowed": False,
            "shap_claimed": False,
            "items": [],
            "model_version": kwargs.get("model_version"),
            "message": "주요 요인 설명을 제공할 수 없습니다.",
        }
