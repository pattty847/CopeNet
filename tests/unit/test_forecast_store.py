"""Synthetic forecast ownership, publication and retention contracts."""
from copy import deepcopy

import pytest

from test_chart_workspace import scene
from copenet.core.market.forecasts.models import validate_submission
from copenet.core.market.forecasts.store import ForecastStore


def admitted(scene, paired=False):
    chart, document, _, observation, _ = scene
    store = ForecastStore(chart)
    request = {'requestId': 'forecast-test', 'documentId': document['documentId'],
               'observationId': observation['observationId'], 'sessionKey': 'session-test',
               'instrument': observation['instrument'], 'provider': 'synthetic', 'model': 'synthetic',
               'paired': paired}
    store.admit(request)
    store.bind_lane('forecast-test', 'ta', 'session-test', 'run-test', observation['observationId'])
    return store, request


def setup_result(scene):
    return {'kind': 'setup', 'direction': 'long', 'thesis': 'Synthetic setup',
            'entry': {'kind': 'limit', 'price': 100}, 'stop': 90,
            'targets': [{'price': 110, 'fraction': 0.5}, {'price': 120, 'fraction': 0.5}],
            'evidence': [{'observationId': scene[3]['observationId'], 'resourceKey': 'candles:D'}]}


def published(scene):
    store, request = admitted(scene)
    store.submit(request['requestId'], 'ta', 'session-test', 'run-test', setup_result(scene))
    store.publish(request['requestId'], published_at='2026-01-03T12:00:00+00:00', reference_close=99,
                  provenance={'basis': 'split_adjusted', 'calendar': 'XNYS', 'splits': [], 'splitFingerprint': 'synthetic'})
    return store, request


@pytest.mark.parametrize('patch', [
    {'stop': 100}, {'stop': 105}, {'stop': float('nan')}, {'stop': float('inf')}, {'stop': -1}, {'stop': True},
    {'targets': [{'price': 99, 'fraction': 1}]},
    {'targets': [{'price': 110, 'fraction': 0.5}]},
    {'targets': [{'price': 120, 'fraction': 0.5}, {'price': 110, 'fraction': 0.5}]},
    {'zones': [{'label': 'zone', 'lower': 1, 'upper': 1}]},
    {'provider': 'model cannot set provider'},
])
def test_invalid_setup_never_enters_ledger(scene, patch):
    with pytest.raises(ValueError):
        validate_submission({**setup_result(scene), **patch}, 'ta')


def test_long_short_contract_and_lane_result_separation(scene):
    result = setup_result(scene)
    assert validate_submission(result, 'ta')['entry']['price'] == 100
    result.update(direction='short', stop=110, targets=[{'price': 90, 'fraction': 1}])
    assert validate_submission(result, 'ta')['direction'] == 'short'
    with pytest.raises(ValueError, match='lane'):
        validate_submission(result, 'directional')
    assert validate_submission({'kind': 'no_setup', 'thesis': 'No edge'}, 'ta')['kind'] == 'no_setup'


def test_request_idempotency_scope_and_active_session(scene):
    store, request = admitted(scene)
    assert store.admit(request) == store.get(request['requestId'])
    with pytest.raises(ValueError, match='different'):
        store.admit({**request, 'paired': True})
    with pytest.raises(ValueError, match='active'):
        store.admit({**request, 'requestId': 'another'})
    with pytest.raises(ValueError, match='scope'):
        store.get(request['requestId'], 'wrong-session')
    with pytest.raises(ValueError, match='admitted run'):
        store.submit(request['requestId'], 'ta', 'wrong-session', 'run-test', setup_result(scene))
    with pytest.raises(ValueError, match='admitted run'):
        store.submit(request['requestId'], 'ta', 'session-test', 'wrong-run', setup_result(scene))
    foreign_evidence = setup_result(scene)
    foreign_evidence['evidence'][0]['observationId'] = 'another-observation'
    with pytest.raises(ValueError, match='admitted observation'):
        store.submit(request['requestId'], 'ta', 'session-test', 'run-test', foreign_evidence)
    assert store.find_lane('session-test')[1] == 'ta'


def test_submission_publication_cancel_and_amendments_preserve_original(scene):
    store, request = published(scene)
    original = deepcopy(store.get(request['requestId']))
    assert store.submit(request['requestId'], 'ta', 'session-test', 'run-test', setup_result(scene)) == original
    assert store.cancel(request['requestId']) == original
    assert store.publish(request['requestId'], published_at='2027-01-01T00:00:00+00:00',
                         reference_close=50, provenance={}) == original
    with pytest.raises(ValueError, match='immutable'):
        store.submit(request['requestId'], 'ta', 'session-test', 'run-test', {**setup_result(scene), 'stop': 95})
    updated = store.amend(request['requestId'], 'amendment-one', {'stop': 95}, 'Reduce proposed risk', {'kind': 'operator'})
    assert updated['members'] == original['members']
    assert updated['amendments'][0]['changes'] == {'stop': 95}
    assert store.amend(request['requestId'], 'amendment-one', {'stop': 95}, 'Reduce proposed risk', {'kind': 'operator'}) == updated
    with pytest.raises(ValueError, match='another amendment'):
        store.amend(request['requestId'], 'amendment-one', {'stop': 97}, 'Changed', {'kind': 'operator'})
    receipt = {'viewId': 'phone', 'revision': updated['revision'], 'status': 'hidden', 'reason': 'comparison chart'}
    painted = store.rendered(request['requestId'], receipt)
    assert painted['revision'] == updated['revision']
    assert painted['members'] == original['members']
    assert painted['renderStatus'] == [receipt]
    assert store.find_lane('session-test') is None


def test_cancelled_attempt_never_resumes_or_submits(scene):
    store, request = admitted(scene)
    store.cancel(request['requestId'])
    assert store.admit(request)['status'] == 'cancelled'
    with pytest.raises(ValueError, match='no longer'):
        store.submit(request['requestId'], 'ta', 'session-test', 'run-test', setup_result(scene))


def test_resource_retention_and_reopen_preserve_forecast(scene):
    store, request = published(scene)
    chart = scene[0]
    with chart.connect() as db:
        db.execute('UPDATE observations SET bound=0,created_at=0')
    chart.cleanup_orphans(now=200000)
    assert chart.observation(request['observationId'], 'session-test')
    from copenet.core.market.chart_workspace import ChartStore
    reopened = ForecastStore(ChartStore(chart.path))
    assert reopened.get(request['requestId']) == store.get(request['requestId'])
    assert len(reopened.list()) == 1
    assert reopened.list(symbol='OTHER') == []


def test_evaluation_event_identity_exact_evidence_and_atomic_capacity(scene):
    store, request = published(scene)
    evidence = {'bars': [{'date': '2026-01-05', 'o': 100, 'h': 108, 'l': 99, 'c': 105}], 'source': 'synthetic'}
    event = {'eventId': 'entry-test', 'type': 'entry', 'date': '2026-01-05', 'price': 100}
    evaluation = {'state': 'active', 'events': [event]}
    record = store.update_evaluation(request['requestId'], evaluation, evidence, expected_revision=store.get(request['requestId'])['revision'])
    assert store.evidence(request['requestId'], record['events'][0]['evidenceId']) == evidence
    assert store.update_evaluation(request['requestId'], evaluation, evidence, expected_revision=store.get(request['requestId'])['revision']) == record
    with pytest.raises(ValueError, match='identity'):
        store.update_evaluation(request['requestId'], {'state': 'active', 'events': [{**event, 'price': 80}]}, evidence, expected_revision=record['revision'])
    assert store.get(request['requestId']) == record
    with scene[0].connect() as db:
        scene[0].capacity_bytes = scene[0]._used_bytes(db) + 10
    with pytest.raises(ValueError, match='capacity'):
        store.update_evaluation(request['requestId'], {'state': 'stopped', 'events': [event]}, {'bars': ['more'] * 1000}, expected_revision=record['revision'])
    assert store.get(request['requestId']) == record
    with scene[0].connect() as db:
        assert db.execute('SELECT COUNT(*) FROM forecast_snapshots').fetchone()[0] == 1


def test_pair_partial_failure_and_server_run_binding(scene):
    store, request = admitted(scene, paired=True)
    chart, _, capture, _, _ = scene
    other = chart.capture('paired-session', 'paired-capture', capture)
    store.bind_lane(request['requestId'], 'directional', 'paired-session', None, other['observationId'])
    store.bind_lane(request['requestId'], 'directional', 'paired-session', 'plain-run', other['observationId'])
    with pytest.raises(ValueError, match='another run'):
        store.bind_lane(request['requestId'], 'directional', 'paired-session', 'replacement-run', other['observationId'])
    store.submit(request['requestId'], 'ta', 'session-test', 'run-test', setup_result(scene))
    with pytest.raises(ValueError, match='complete'):
        store.publish(request['requestId'], published_at='2026-01-03T12:00:00Z', reference_close=100, provenance={})
    store.lane_failed(request['requestId'], 'directional', 'Provider unavailable')
    record = store.publish(request['requestId'], published_at='2026-01-03T12:00:00Z', reference_close=100, provenance={})
    assert record['status'] == 'published'
    assert record['pairComplete'] is False
    assert record['members']['directional']['status'] == 'failed'


def test_clone_shares_exact_evidence_without_live_drawing_revision(scene):
    store, request = admitted(scene, paired=True)
    chart, document, _, observation, _ = scene
    with chart.connect() as db:
        db.execute('UPDATE documents SET revision=99 WHERE id=?', (document['documentId'],))
    clone = store.clone_observation(request['requestId'], 'directional', 'isolated-lane')
    assert clone['capturedAt'] == observation['capturedAt']
    assert clone['resources'] == observation['resources']
    assert clone['documentRevision'] == observation['documentRevision']
    assert clone['observationId'] != observation['observationId']
    assert store.clone_observation(request['requestId'], 'directional', 'isolated-lane') == clone
    store.bind_lane(request['requestId'], 'directional', 'isolated-lane', 'isolated-run', clone['observationId'])
    with chart.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM resources').fetchone()[0] == len(observation['resources'])
    with pytest.raises(ValueError, match='session'):
        chart.observation(clone['observationId'], 'session-test')


def test_lane_rejects_changed_evidence_and_schema_repairs_are_audited(scene):
    store, request = admitted(scene, paired=True)
    chart, _, capture, _, _ = scene
    altered = deepcopy(capture)
    altered['resources'][0]['rows'][0]['c'] = 900
    other = chart.capture('other-session', 'altered', altered)
    with pytest.raises(ValueError, match='differs'):
        store.bind_lane(request['requestId'], 'directional', 'other-session', 'other-run', other['observationId'])
    with pytest.raises(ValueError, match='Protective stop'):
        store.submit(request['requestId'], 'ta', 'session-test', 'run-test', {**setup_result(scene), 'stop': 110})
    record = store.get(request['requestId'])
    assert len(record['members']['ta']['errors']) == 1
    assert record['members']['ta']['status'] == 'generating'
    store.submit(request['requestId'], 'ta', 'session-test', 'run-test', setup_result(scene))
    assert len(store.get(request['requestId'])['members']['ta']['errors']) == 1


def test_admission_capacity_rolls_back_request_and_pin(scene):
    chart, document, _, observation, _ = scene
    store = ForecastStore(chart)
    with chart.connect() as db:
        chart.capacity_bytes = chart._used_bytes(db)
    request = {'requestId': 'overflow', 'documentId': document['documentId'], 'observationId': observation['observationId'],
               'sessionKey': 'session-test', 'instrument': observation['instrument'], 'provider': 'synthetic', 'model': 'synthetic'}
    with pytest.raises(ValueError, match='capacity'):
        store.admit(request)
    with chart.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM forecast_requests').fetchone()[0] == 0
        assert db.execute('SELECT bound FROM observations WHERE id=?', (observation['observationId'],)).fetchone()[0] == 0


def test_amendment_revision_conflict_preserves_original_and_allows_exact_retry(scene):
    store, request = published(scene)
    original = store.get(request['requestId'])
    amended = store.amend(request['requestId'], 'revision-one', {'stop': 95}, 'Synthetic rationale',
                          {'kind': 'operator'}, expected_revision=original['revision'])
    assert store.amend(request['requestId'], 'revision-one', {'stop': 95}, 'Synthetic rationale',
                       {'kind': 'operator'}, expected_revision=original['revision']) == amended
    with pytest.raises(ValueError, match='changed before'):
        store.amend(request['requestId'], 'revision-two', {'stop': 96}, 'Synthetic rationale',
                    {'kind': 'operator'}, expected_revision=original['revision'])
    assert store.get(request['requestId']) == amended


def test_forecast_chart_evidence_inspection_requires_exact_published_reference(scene):
    store, request = admitted(scene, paired=True)
    chart = scene[0]
    clone = store.clone_observation(request['requestId'], 'directional', 'plain-session')
    store.bind_lane(request['requestId'], 'directional', 'plain-session', 'plain-run', clone['observationId'])
    # A reference to a cloned lane observation is published independently of drawings.
    source = setup_result(scene)
    store.submit(request['requestId'], 'ta', 'session-test', 'run-test', source)
    with pytest.raises(ValueError, match='not referenced'):
        chart.document_evidence_observation(request['documentId'], request['observationId'], 'candles:D')
    store.lane_failed(request['requestId'], 'directional', 'No answer')
    store.publish(request['requestId'], published_at='2026-01-03T12:00:00Z', reference_close=100, provenance={})
    assert chart.document_evidence_observation(request['documentId'], request['observationId'], 'candles:D')['observationId'] == request['observationId']
    with pytest.raises(ValueError, match='not referenced'):
        chart.document_evidence_observation(request['documentId'], clone['observationId'], 'candles:D')
    with pytest.raises(ValueError, match='not referenced'):
        chart.document_evidence_observation(request['documentId'], request['observationId'], 'drawings')
    other = chart.workspace('another-workspace', scene[3]['instrument'])['document']
    with pytest.raises(ValueError, match='not referenced'):
        chart.document_evidence_observation(other['documentId'], request['observationId'], 'candles:D')
