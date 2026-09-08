"""Transactional admission, immutable publication and exact forecast evidence retention."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from ..chart_workspace.codec import digest, encode, new_id
from .models import ForecastRequest, validate_submission


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ForecastRevisionConflict(ValueError):
    """A concurrent write advanced the forecast while candles were being evaluated."""


class ForecastStore:
    def __init__(self, chart_store):
        self.chart_store = chart_store

    @staticmethod
    def _get(db, request_id):
        row = db.execute('SELECT body FROM forecast_requests WHERE id=?', (request_id,)).fetchone()
        if not row:
            raise ValueError('Forecast request is unavailable')
        return json.loads(row['body'])

    def _save(self, db, record):
        record['revision'] += 1
        db.execute('UPDATE forecast_requests SET status=?,body=? WHERE id=?',
                   (record['status'], encode(record), record['requestId']))
        self._capacity(db)
        return record

    def _capacity(self, db):
        if self.chart_store._used_bytes(db) > self.chart_store.capacity_bytes:
            raise ValueError('Chart evidence capacity reached; forecast changes were not saved')

    @staticmethod
    def _pin(db, request_id, observation_id, session_key):
        row = db.execute('SELECT body FROM observations WHERE id=? AND session_key=?',
                         (observation_id, session_key)).fetchone()
        if not row:
            raise ValueError('Forecast observation is unavailable for this session')
        observation = json.loads(row['body'])
        if observation['settings'].get('includeAccountContext'):
            raise ValueError('Forecast evidence must exclude account context')
        db.execute('UPDATE observations SET bound=1 WHERE id=?', (observation_id,))
        db.execute('INSERT OR IGNORE INTO forecast_resources SELECT ?,resource_id FROM observation_resources '
                   'WHERE observation_id=?', (request_id, observation_id))
        return observation

    def admit(self, request: dict) -> dict:
        request = ForecastRequest.model_validate(request).model_dump()
        fingerprint = digest(request)
        with self.chart_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT fingerprint,body FROM forecast_requests WHERE id=?', (request['requestId'],)).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise ValueError('requestId already belongs to a different forecast admission')
                return json.loads(old['body'])
            if db.execute("SELECT 1 FROM forecast_requests WHERE session_key=? AND status IN ('requested','generating')",
                          (request['sessionKey'],)).fetchone():
                raise ValueError('This chart session already has an active forecast request')
            observation = self.chart_store.observation(request['observationId'], request['sessionKey'])
            if observation['documentId'] != request['documentId'] or observation['instrument'] != request['instrument']:
                raise ValueError('Forecast instrument/document differs from captured evidence')
            record = {**request, 'forecastId': request['requestId'], 'status': 'requested', 'revision': 0,
                      'requestedAt': utc_now(), 'capturedAt': observation['capturedAt'], 'publishedAt': None,
                      'timeframe': observation['timeframe'], 'members': {}, 'evaluation': None,
                      'events': [], 'amendments': [], 'renderStatus': []}
            db.execute('INSERT INTO forecast_requests VALUES (?,?,?,?,?,?,?)',
                       (request['requestId'], request['sessionKey'], request['documentId'], request['observationId'],
                        fingerprint, record['status'], encode(record)))
            self._pin(db, request['requestId'], request['observationId'], request['sessionKey'])
            self._capacity(db)
            return record

    def clone_observation(self, request_id, lane, session_key):
        """Share exact admitted resources through a new session authorization envelope."""
        with self.chart_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._get(db, request_id)
            if record['status'] not in ('requested', 'generating') or lane not in ('ta', 'directional') or (lane == 'directional' and not record['paired']):
                raise ValueError('Forecast lane was not admitted or is already complete')
            capture_id = f'forecast:{request_id}:{lane}'
            old = db.execute('SELECT body FROM observations WHERE session_key=? AND capture_id=?', (session_key, capture_id)).fetchone()
            if old:
                return json.loads(old['body'])
            source = db.execute('SELECT * FROM observations WHERE id=?', (record['observationId'],)).fetchone()
            observation = json.loads(source['body'])
            observation.update(observationId=new_id('observation'), sessionKey=session_key)
            db.execute('INSERT INTO observations VALUES (?,?,?,?,?,?,?,1)',
                       (observation['observationId'], session_key, capture_id, source['fingerprint'],
                        record['documentId'], encode(observation), source['created_at']))
            db.execute('INSERT INTO observation_resources SELECT ?,resource_key,resource_id FROM observation_resources WHERE observation_id=?',
                       (observation['observationId'], record['observationId']))
            self._capacity(db)
            return observation

    def bind_lane(self, request_id, lane, session_key, run_id, observation_id, attribution=None):
        with self.chart_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._get(db, request_id)
            if record['status'] not in ('requested', 'generating'):
                raise ValueError('Forecast admission is no longer accepting runs')
            if lane not in ('ta', 'directional') or (lane == 'directional' and not record['paired']):
                raise ValueError('Forecast lane was not admitted')
            previous = record['members'].get(lane)
            if previous:
                if previous['sessionKey'] != session_key or previous['observationId'] != observation_id or previous['runId'] not in (None, run_id):
                    raise ValueError('Forecast lane is already bound to another run')
                if previous['runId'] == run_id:
                    return record
            observation = self._pin(db, request_id, observation_id, session_key)
            admitted = json.loads(db.execute('SELECT body FROM observations WHERE id=?', (record['observationId'],)).fetchone()['body'])
            semantic = lambda value: {k: v for k, v in value.items() if k not in ('observationId', 'sessionKey', 'capturedAt')}
            if semantic(observation) != semantic(admitted):
                raise ValueError('Lane evidence differs from the frozen admitted capture')
            if db.execute('SELECT 1 FROM forecast_lanes WHERE request_id=? AND lane!=? AND session_key=?',
                          (request_id, lane, session_key)).fetchone():
                raise ValueError('Paired lanes require isolated sessions')
            if observation['documentId'] != record['documentId'] or observation['instrument'] != record['instrument']:
                raise ValueError('Lane evidence belongs to another forecast chart')
            member = previous or {'sessionKey': session_key, 'observationId': observation_id,
                                  'status': 'generating', 'errors': [], 'attribution': attribution or {}}
            member['runId'] = run_id
            record['members'][lane] = member
            record['status'] = 'generating'
            db.execute('INSERT INTO forecast_lanes VALUES (?,?,?,?,?,?) ON CONFLICT(request_id,lane) '
                       'DO UPDATE SET run_id=excluded.run_id,body=excluded.body',
                       (request_id, lane, session_key, run_id, observation_id, encode(member)))
            return self._save(db, record)

    def find_lane(self, session_key):
        with self.chart_store.connect() as db:
            row = db.execute("SELECT l.request_id,l.lane FROM forecast_lanes l JOIN forecast_requests r "
                             "ON r.id=l.request_id WHERE l.session_key=? AND r.status IN ('requested','generating')",
                             (session_key,)).fetchone()
            return (self._get(db, row['request_id']), row['lane']) if row else None

    def submit(self, request_id, lane, session_key, run_id, result):
        try:
            result = validate_submission(result, lane)
        except ValueError as exc:
            self.record_rejection(request_id, lane, session_key, run_id, str(exc))
            raise
        with self.chart_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._get(db, request_id)
            member = record['members'].get(lane)
            if not member or member['sessionKey'] != session_key or not run_id or member['runId'] != run_id:
                raise ValueError('Forecast submission is outside the admitted run')
            if member.get('result') is not None:
                if member['result'] != result:
                    raise ValueError('This forecast lane already submitted its immutable result')
                return record
            if record['status'] != 'generating' or member['status'] != 'generating':
                raise ValueError('Forecast request is no longer accepting submissions')
            for ref in result.get('evidence', []):
                if ref['observationId'] != member['observationId']:
                    raise ValueError('Forecast evidence must refer to the admitted observation')
                resource = db.execute('SELECT r.body FROM resources r JOIN observation_resources o ON r.id=o.resource_id '
                                      'WHERE o.observation_id=? AND o.resource_key=?',
                                      (ref['observationId'], ref['resourceKey'])).fetchone()
                if not resource or json.loads(resource['body'])['metadata'].get('accountContext'):
                    raise ValueError('Forecast evidence resource is outside the admitted scope')
            member.update(result=result, status='submitted', submittedAt=utc_now())
            db.execute('UPDATE forecast_lanes SET body=? WHERE request_id=? AND lane=?', (encode(member), request_id, lane))
            return self._save(db, record)

    def record_rejection(self, request_id, lane, session_key, run_id, reason):
        with self.chart_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._get(db, request_id)
            member = record['members'].get(lane)
            if not member or member['sessionKey'] != session_key or member['runId'] != run_id or not run_id:
                raise ValueError('Forecast submission is outside the admitted run')
            if record['status'] != 'generating' or member['status'] != 'generating':
                raise ValueError('Forecast request is no longer accepting submissions')
            member['errors'].append({'recordedAt': utc_now(), 'reason': str(reason)[:4000]})
            db.execute('UPDATE forecast_lanes SET body=? WHERE request_id=? AND lane=?', (encode(member), request_id, lane))
            return self._save(db, record)

    def lane_failed(self, request_id, lane, reason):
        with self.chart_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._get(db, request_id)
            if record['status'] not in ('requested', 'generating'):
                return record
            member = record['members'].get(lane)
            if not member:
                raise ValueError('Forecast lane unavailable')
            member['errors'].append({'recordedAt': utc_now(), 'reason': str(reason)[:4000]})
            if not member.get('result'):
                member['status'] = 'failed'
            db.execute('UPDATE forecast_lanes SET body=? WHERE request_id=? AND lane=?', (encode(member), request_id, lane))
            return self._save(db, record)

    def set_attribution(self, request_id, lane, attribution):
        with self.chart_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._get(db, request_id)
            if record['publishedAt']:
                raise ValueError('Published forecast attribution is immutable')
            member = record['members'].get(lane)
            if not member:
                raise ValueError('Forecast lane unavailable')
            member['attribution'] = {**member['attribution'], **attribution}
            db.execute('UPDATE forecast_lanes SET body=? WHERE request_id=? AND lane=?', (encode(member), request_id, lane))
            return self._save(db, record)

    def publish(self, request_id, *, published_at, reference_close, provenance, evidence_cutoff=None, evidence=None):
        from pydantic import TypeAdapter
        from .models import Price
        reference_close = TypeAdapter(Price).validate_python(reference_close, strict=True)
        published = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        if published.tzinfo is None:
            raise ValueError('Publication time requires an explicit timezone')
        with self.chart_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._get(db, request_id)
            if record['publishedAt']:
                return record
            if record['status'] not in ('requested', 'generating'):
                raise ValueError('Forecast admission cannot be published')
            results = {lane: member['result'] for lane, member in record['members'].items() if member.get('result')}
            if not results:
                raise ValueError('No valid forecast result is available to publish')
            if any(member['status'] == 'generating' for member in record['members'].values()):
                raise ValueError('Wait for admitted lanes to complete before publication')
            record.update(publishedAt=published.isoformat(), referenceClose=reference_close, provenance=provenance,
                          evidenceCutoff=evidence_cutoff, publicationEvidence=evidence,
                          deadlineAt=(published + timedelta(days=56)).isoformat(),
                          dueAt={'fourWeek': (published + timedelta(days=28)).isoformat(),
                                 'eightWeek': (published + timedelta(days=56)).isoformat()},
                          pairComplete=not record['paired'] or set(results) == {'ta', 'directional'},
                          status='no_setup' if results.get('ta', {}).get('kind') == 'no_setup' else 'published')
            return self._save(db, record)

    def _terminal(self, request_id, status, reason=None):
        with self.chart_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._get(db, request_id)
            if record['status'] not in ('requested', 'generating'):
                return record
            record.update(status=status, failureReason=reason, finishedAt=utc_now())
            return self._save(db, record)

    def cancel(self, request_id):
        return self._terminal(request_id, 'cancelled')

    def fail(self, request_id, reason):
        return self._terminal(request_id, 'failed', str(reason)[:4000])

    def get(self, request_id, session_key=None):
        with self.chart_store.connect() as db:
            record = self._get(db, request_id)
            if session_key is not None and not db.execute('SELECT 1 FROM forecast_lanes WHERE request_id=? AND session_key=?',
                                                         (request_id, session_key)).fetchone():
                raise ValueError('Forecast is outside this session scope')
            return record

    def list(self, document_id=None, symbol=None, limit=100, offset=0):
        if type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or offset < 0:
            raise ValueError('Use limit 1–500 and offset >= 0')
        clauses, params = [], []
        if document_id:
            clauses.append('document_id=?')
            params.append(document_id)
        if symbol:
            clauses.append("json_extract(body,'$.instrument.symbol')=?")
            params.append(symbol)
        with self.chart_store.connect() as db:
            query = 'SELECT body FROM forecast_requests' + (' WHERE ' + ' AND '.join(clauses) if clauses else '')
            return [json.loads(row['body']) for row in db.execute(query + ' ORDER BY rowid DESC LIMIT ? OFFSET ?',
                                                                 (*params, limit, offset))]

    def set_tracking(self, request_id, scan_id):
        with self.chart_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._get(db, request_id)
            if record['trackingScanId'] == scan_id:
                return record
            record['trackingScanId'] = scan_id
            return self._save(db, record)

    def update_evaluation(self, request_id, evaluation, evidence, *, expected_revision):
        snapshot_id = digest(evidence)
        with self.chart_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._get(db, request_id)
            if not record['publishedAt']:
                raise ValueError('Only published forecasts can be evaluated')
            if record['evaluation'] == evaluation:
                return record
            if record['revision'] != expected_revision:
                raise ForecastRevisionConflict('Forecast advanced during evaluation; read current state and retry')
            db.execute('INSERT OR IGNORE INTO forecast_snapshots VALUES (?,?)', (snapshot_id, encode(evidence)))
            db.execute('INSERT OR IGNORE INTO forecast_evaluations VALUES (?,?)', (request_id, snapshot_id))
            for event in evaluation.get('events', []):
                old = db.execute('SELECT request_id,body FROM forecast_events WHERE id=?', (event['eventId'],)).fetchone()
                if old:
                    previous = json.loads(old['body'])
                    if old['request_id'] != request_id or {k:v for k,v in previous.items() if k != 'evidenceId'} != event:
                        raise ValueError('Evaluation event identity already belongs to different evidence or outcome')
                else:
                    db.execute('INSERT INTO forecast_events VALUES (?,?,?,?)',
                               (event['eventId'], request_id, snapshot_id, encode({**event, 'evidenceId': snapshot_id})))
            record['evaluation'] = evaluation
            record['events'] = [json.loads(row['body']) for row in db.execute('SELECT body FROM forecast_events WHERE request_id=? ORDER BY rowid', (request_id,))]
            record['evaluationEvidenceId'] = snapshot_id
            return self._save(db, record)

    def references_chart_evidence(self, document_id, observation_id, resource_key):
        with self.chart_store.connect() as db:
            rows = db.execute("SELECT f.body FROM forecast_requests f JOIN forecast_resources p ON p.request_id=f.id "
                              "JOIN observation_resources o ON o.resource_id=p.resource_id "
                              "WHERE f.document_id=? AND o.observation_id=? AND o.resource_key=?",
                              (document_id, observation_id, resource_key))
            for row in rows:
                record = json.loads(row['body'])
                if not record['publishedAt']:
                    continue
                refs = [ref for member in record['members'].values() for ref in member.get('result', {}).get('evidence', [])]
                if record.get('publicationEvidence'):
                    refs.append(record['publicationEvidence'])
                if any(ref['observationId'] == observation_id and ref['resourceKey'] == resource_key for ref in refs):
                    return True
            return False

    def evidence(self, request_id, evidence_id, session_key=None):
        self.get(request_id, session_key)
        with self.chart_store.connect() as db:
            row = db.execute('SELECT s.body FROM forecast_snapshots s JOIN forecast_evaluations e ON e.snapshot_id=s.id '
                             'WHERE e.request_id=? AND s.id=?', (request_id, evidence_id)).fetchone()
            if not row:
                raise ValueError('Forecast evaluation evidence unavailable')
            return json.loads(row['body'])

    def amend(self, request_id, amendment_id, changes, rationale, author, *, expected_revision=None):
        if not isinstance(rationale, str) or not 0 < len(rationale) <= 4000:
            raise ValueError('A short amendment rationale is required')
        with self.chart_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._get(db, request_id)
            if not record['publishedAt']:
                raise ValueError('Only published forecasts accept amendments')
            if not changes or set(changes) - {'entry', 'stop', 'targets', 'zones', 'thesis'}:
                raise ValueError('Amendment may change setup levels, zones or thesis')
            original = record['members'].get('ta', {}).get('result', {})
            if original.get('kind') != 'setup':
                raise ValueError('Only a registered setup can be amended')
            validate_submission({**original, **changes}, 'ta')
            body = {'amendmentId': amendment_id, 'forecastId': request_id, 'changes': changes, 'rationale': rationale, 'author': author}
            old = db.execute('SELECT body FROM forecast_amendments WHERE id=?', (amendment_id,)).fetchone()
            if old:
                if {k:v for k,v in json.loads(old['body']).items() if k != 'recordedAt'} != body:
                    raise ValueError('amendmentId already belongs to another amendment')
                return record
            if expected_revision is not None and record['revision'] != expected_revision:
                raise ValueError('Forecast changed before amendment; refresh and retry')
            body['recordedAt'] = utc_now()
            db.execute('INSERT INTO forecast_amendments VALUES (?,?,?)', (amendment_id, request_id, encode(body)))
            record['amendments'].append(body)
            return self._save(db, record)

    def rendered(self, request_id, receipt):
        if receipt.get('status') not in ('rendered', 'hidden', 'failed') or not receipt.get('viewId') or type(receipt.get('revision')) is not int:
            raise ValueError('Render receipt requires viewId, revision and rendered/hidden/failed status')
        with self.chart_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._get(db, request_id)
            if not record['publishedAt'] or receipt['revision'] > record['revision'] or receipt['revision'] < 0:
                raise ValueError('Render receipt refers to an unavailable forecast revision')
            db.execute('INSERT INTO forecast_render_receipts VALUES (?,?,?,?) ON CONFLICT(request_id,view_id,revision) DO UPDATE SET body=excluded.body',
                       (request_id, receipt['viewId'], receipt['revision'], encode(receipt)))
            record['renderStatus'] = [json.loads(row['body']) for row in db.execute('SELECT body FROM forecast_render_receipts WHERE request_id=?', (request_id,))]
            # Painting does not change the revision it acknowledges or trade outcomes.
            db.execute('UPDATE forecast_requests SET body=? WHERE id=?', (encode(record), request_id))
            self._capacity(db)
            return record
