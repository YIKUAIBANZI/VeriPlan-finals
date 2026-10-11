"""Pure, mode-isolated calibration. No model or I/O is used here."""
from collections import defaultdict
from decimal import Decimal
from math import isfinite
from statistics import fmean

from app.schemas import Assumption, DecisionSnapshot, InvalidInput


APPROVED = {'accepted', 'revised', 'deferred'}


def error_pct(predicted: float, actual: float) -> float | None:
    if predicted == 0:
        return None
    result = float((Decimal(str(actual)) - Decimal(str(predicted))) / abs(Decimal(str(predicted))) * 100)
    return result if isfinite(result) else None


def calculate_actuals(assumptions: list[Assumption], actuals) -> list[dict]:
    known = {item.id: item for item in assumptions}
    ids = [item.assumption_id for item in actuals]
    if len(ids) != len(set(ids)) or set(ids) - known.keys():
        raise InvalidInput('Actuals must reference unique existing assumption IDs')
    result = []
    for item in actuals:
        predicted = known[item.assumption_id].value
        error = error_pct(predicted, item.actual_value)
        row = item.model_dump() | {'error_pct': round(error, 2) if error is not None else None}
        if error is None:
            row['calculation_note'] = '不可计算：预测值为 0' if predicted == 0 else '不可计算：超出数值范围'
        result.append(row)
    return result


def calibration_profile(decisions: list[DecisionSnapshot], *, mode: str) -> dict:
    samples = []
    grouped = defaultdict(list)
    for decision in decisions:
        if decision.mode != mode or decision.status.value not in APPROVED | {'retrospective'}:
            continue
        known = {item.id: item for item in decision.assumptions}
        # A repeated checkpoint updates history, not independent calibration evidence.
        latest = {}
        for outcome in sorted(decision.outcomes, key=lambda o: o['recorded_at']):
            for actual in outcome['actuals']:
                latest[actual['assumption_id']] = (outcome, actual)
        for assumption_id, (outcome, actual) in latest.items():
            assumption = known.get(assumption_id)
            if assumption is None:
                continue
            error = error_pct(assumption.value, actual['actual_value'])
            sample = {
                'decision_id': decision.id, 'assumption_id': assumption_id,
                'category': assumption.category, 'predicted_value': assumption.value,
                'actual_value': actual['actual_value'], 'confidence': assumption.confidence,
                'error_pct': round(error, 2) if error is not None else None,
                'source': 'retrospective' if decision.is_retrospective else decision.mode,
                'mode': decision.mode, 'checkpoint': outcome['checkpoint'],
                'recorded_at': outcome['recorded_at'],
                'is_synthetic': bool(decision.outputs.get('retrospective', {}).get('is_synthetic', False)),
            }
            if error is None:
                sample['calculation_note'] = actual.get('calculation_note', '不可计算')
            else:
                grouped[assumption.category].append((error, assumption.confidence))
            samples.append(sample)
    categories = []
    for category, values in sorted(grouped.items()):
        hit = sum(abs(error) <= 20 for error, _ in values) / len(values)
        confidence = fmean(confidence for _, confidence in values)
        categories.append(dict(category=category, n=len(values),
            mean_bias_pct=float(sum(Decimal(str(error)) for error, _ in values) / len(values)), hit_rate=hit,
            mean_confidence=confidence, overconfidence_gap=confidence - hit * 100))
    return {'mode': mode, 'categories': categories, 'samples': samples}


def calibration_warnings(profile: dict, assumptions: list[Assumption]) -> list[dict]:
    warnings = []
    labels = {'revenue': '收入', 'cost': '成本', 'volume': '销量', 'time': '耗时', 'conversion': '转化', 'other': '其他'}
    for row in profile['categories']:
        category, bias = row['category'], row['mean_bias_pct']
        relevant = [item for item in assumptions if item.category == category]
        if row['n'] < 2 or abs(bias) < 20 or not relevant:
            continue
        references = {item.id: round(item.value * (1 + bias / 100), 2) for item in relevant}
        if not all(isfinite(value) for value in references.values()):
            continue
        if category in {'cost', 'time'} and bias > 0:
            direction = f'低估了{labels[category]}'
        else:
            direction = '高估' if bias < 0 else '低估'
        warnings.append(dict(category=category, bias_pct=round(bias, 2), sample_size=row['n'],
            assumption_ids=[item.id for item in relevant], adjusted_reference=references,
            message=f"你过去 {row['n']} 次{labels[category]}类预测平均{direction} {abs(bias):.1f}%；按你历史偏差修正的参考值，不是预测。"))
    return warnings
