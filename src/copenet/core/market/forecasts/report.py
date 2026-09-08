"""Separate direction, paired experiment and trade-planning scorecards."""
from __future__ import annotations

from collections import Counter

from .evaluator import POLICY_VERSION


def forecast_report(forecasts: list[dict]) -> dict:
    """All admitted attempts remain in coverage; unresolved trades never become zero-R wins."""
    states = Counter()
    health = Counter()
    scores = []
    holdings = []
    activated = 0
    direction = {}
    paired = {}
    for forecast in forecasts:
        evaluation = forecast.get('evaluation') or {}
        state = evaluation.get('state') or forecast['status']
        states[state] += 1
        health[evaluation.get('health', 'unevaluated')] += 1
        activated += evaluation.get('entryPrice') is not None
        score = evaluation.get('plannedRiskR')
        if score is not None and evaluation.get('health') != 'revision_review':
            scores.append(score)
            if evaluation.get('holdingSessions') is not None:
                holdings.append(evaluation['holdingSessions'])
    for horizon in ('4w', '8w'):
        ta_counts = Counter()
        pair_counts = Counter()
        eligible = []
        for forecast in forecasts:
            evaluation = forecast.get('evaluation') or {}
            snapshot = evaluation.get('horizons', {}).get(horizon, {})
            members = snapshot.get('members', {})
            outcome = members.get('ta', {}).get('outcome', 'missing' if forecast.get('publishedAt') else forecast['status'])
            if evaluation.get('health') == 'revision_review':
                outcome = 'revision_review'
            ta_counts[outcome] += 1
            if not forecast.get('paired'):
                continue
            plain = members.get('directional', {}).get('outcome', 'missing')
            if outcome in {'correct', 'incorrect'} and plain in {'correct', 'incorrect'}:
                key = 'bothCorrect' if outcome == plain == 'correct' else 'bothIncorrect' if outcome == plain == 'incorrect' else 'taOnlyCorrect' if outcome == 'correct' else 'plainOnlyCorrect'
                pair_counts[key] += 1
                eligible.append(forecast)
            else:
                pair_counts['excluded'] += 1
                if plain == 'missing':
                    pair_counts['missing'] += 1
                elif outcome == 'abstain' or plain == 'abstain':
                    pair_counts['abstained'] += 1
                elif outcome == 'push' or plain == 'push':
                    pair_counts['push'] += 1
                else:
                    pair_counts['pendingOrReview'] += 1
        resolved = ta_counts['correct'] + ta_counts['incorrect']
        direction[horizon] = {'counts': dict(ta_counts), 'scoredCount': resolved,
                              'accuracy': ta_counts['correct'] / resolved if resolved else None}
        paired[horizon] = {'counts': dict(pair_counts), 'pairedCount': len(eligible),
                           'correctnessDelta': (pair_counts['taOnlyCorrect'] - pair_counts['plainOnlyCorrect']) / len(eligible) if eligible else None,
                           'distinctTickers': len({row['instrument']['symbol'] for row in eligible}),
                           'distinctPublicationDates': len({row['publishedAt'][:10] for row in eligible})}
    setups = sum((forecast.get('members', {}).get('ta', {}).get('result') or {}).get('kind') == 'setup' for forecast in forecasts)
    return {'policyVersion': POLICY_VERSION, 'attemptCount': len(forecasts), 'setupCount': setups,
            'states': dict(states), 'health': dict(health), 'direction': direction, 'paired': paired,
            'trade': {'activatedCount': activated, 'activationRate': activated / setups if setups else None,
                      'scoredCount': len(scores), 'meanPlannedRiskR': sum(scores) / len(scores) if scores else None,
                      'positiveCount': sum(score > 0 for score in scores), 'negativeCount': sum(score < 0 for score in scores),
                      'meanHoldingSessions': sum(holdings) / len(holdings) if holdings else None},
            'methodology': 'Gross simulated price returns; fees, spread, borrow and dividend cash flows excluded. Historical ledger calls retain their original cohort and endpoint rules.'}
