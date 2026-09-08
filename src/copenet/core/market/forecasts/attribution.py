"""Exact evidence/prompt identities and honest runtime attribution for each lane."""
from __future__ import annotations

import hashlib

from ..chart_workspace.codec import digest
from ..chart_workspace.model_tables import format_context

PROMPT_VERSION = 'chart-forecast-1'


def input_attribution(charts, record, lane, prompt):
    member = record['members'][lane]
    observation = charts.observation(member['observationId'], member['sessionKey'])
    context = charts.resolve_context(member['sessionKey'], member['runId'], {
        'observationId': observation['observationId'], 'documentId': record['documentId'],
        'viewId': observation['viewId'], 'detail': record['detail'], 'access': 'read'})
    semantic = {key: observation[key] for key in ('instrument', 'timeframe', 'range', 'viewport', 'selection', 'settings', 'capturedAt')}
    semantic['resources'] = [{key: resource[key] for key in ('key', 'resourceId')} for resource in observation['resources']]
    return {'provider': record['provider'], 'requestedModel': record['model'], 'model': record['model'],
            'modelSource': 'requested', 'detail': record['detail'], 'promptVersion': PROMPT_VERSION,
            'promptHash': hashlib.sha256(prompt.encode()).hexdigest(), 'evidenceManifestHash': digest(semantic),
            'initialPresentationHash': hashlib.sha256(format_context(charts.context_payload(context)).encode()).hexdigest(),
            'reportedUsage': None, 'usageStatus': 'unavailable', 'readCallCount': 0, 'reads': []}


def run_attribution(run):
    """Message estimates are separate from provider token usage, never substituted for it."""
    if run is None:
        return {'runStatus': 'unavailable'}
    reads = [{key: step.get(key) for key in ('callId', 'toolId', 'arguments', 'ok', 'artifactId')}
             for step in run.tool_steps if step['toolId'] in ('market.chart.context', 'market.chart.read')]
    usage = run.metadata.get('usage')
    return {'provider': run.provider, 'model': run.model, 'modelSource': 'run_record', 'runStatus': run.status,
            'reportedUsage': usage, 'usageStatus': 'reported' if usage is not None else 'unavailable',
            'readCallCount': len(reads), 'reads': reads, 'toolCallCount': len(run.tool_steps),
            'messageInputTokenEstimate': run.input_token_estimate, 'messageCount': run.message_count,
            'sourceArtifactIds': run.artifact_ids}
