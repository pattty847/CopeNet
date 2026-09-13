"""A second browser recovers output generated with no connected clients."""
import asyncio
import threading

from fastapi.testclient import TestClient

from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.host.api import create_app
from copenet.providers import ProviderEvent
from test_ws_rpc import FakeProvider, _open_rpc


def test_reopen_during_run_recovers_missing_text_and_resumes_events(tmp_path, monkeypatch):
    monkeypatch.setenv('COPNET_TOKEN', 'test-token')
    monkeypatch.setenv('COPNET_WORKDIR', str(tmp_path))
    away = threading.Event()
    resume = threading.Event()
    produced = threading.Event()

    class GatedProvider(FakeProvider):
        async def run(self, **kwargs):
            yield ProviderEvent(kind='delta', text='Before close. ')
            while not away.is_set():
                await asyncio.sleep(0.005)
            yield ProviderEvent(kind='delta', text='While away. ')
            produced.set()
            while not resume.is_set():
                await asyncio.sleep(0.005)
            yield ProviderEvent(kind='delta', text='After return.')
            yield ProviderEvent(kind='final')

    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / 'index.json'),
        transcript_store=TranscriptStore(root_dir=tmp_path / 'transcripts'),
        sessions_dir=tmp_path, providers={'fake': GatedProvider()},
    )
    with TestClient(create_app(orchestrator=orchestrator)) as client:
        try:
            with _open_rpc(client) as first:
                request = first.request('chat.send', {'sessionKey': 'reopen', 'provider': 'fake', 'message': 'Test recovery'})
                run_id = first.recv_response(request)['payload']['runId']
                first._next_matching(lambda frame: frame.get('event') == 'chat' and frame['payload']['state'] == 'delta')
            away.set()
            assert produced.wait(3), 'Run did not continue with all browsers closed'
            with _open_rpc(client) as second:
                history = second.recv_response(second.request('chat.history', {'sessionKey': 'reopen'}))['payload']
                assert [message['role'] for message in history['messages']] == ['user']
                assert history['activeRun']['runId'] == run_id
                assert history['activeRun']['message']['content'] == 'Before close. While away. '
                seq = history['activeRun']['seq']
                resume.set()
                events = second.recv_chat_until_terminal(run_id=run_id)
                assert all(event['payload']['seq'] > seq for event in events)
                assert events[-1]['payload']['message']['content'] == 'Before close. While away. After return.'
            with _open_rpc(client) as third:
                history = third.recv_response(third.request('chat.history', {'sessionKey': 'reopen'}))['payload']
                assert history['activeRun'] is None
                assert [message['role'] for message in history['messages']] == ['user', 'assistant']
                assert history['messages'][-1]['content'] == 'Before close. While away. After return.'
        finally:
            away.set()
            resume.set()
