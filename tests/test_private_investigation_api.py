"""Authored subprocesses exercise the actual API and private inquiry boundary."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from eidos.api import EidosAPI, thread_payload
from eidos.private_investigation import PrivateInvestigationWorker
from eidos.trace import TraceStore
from eidos.view import render_index_html, render_thread_html

spec = importlib.util.spec_from_file_location('private_demo', Path(__file__).parents[1] / 'scripts/private_native_evidence_demo.py')
assert spec and spec.loader
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def totals(path):
    values = {}
    for private_path in Path(str(path) + '.private').glob('*/evidence.sqlite'):
        trace = TraceStore(private_path, role='private-control')
        try:
            values[private_path.parent.name] = [(r.seq, r.raw_text) for r in trace.records()]
        finally:
            trace.close()
    return values


def test_private_fixture_reopens_exactly_and_public_surfaces_exclude_control_canaries(tmp_path):
    path = tmp_path / 'work.db'
    marker = demo.seed(path)
    private_before = totals(path)
    assert len(private_before) == 4
    assert any('PRIVATE_LOGIN_CANARY' in raw for records in private_before.values() for _, raw in records)
    assert any('PRIVATE_LATE_CANARY' in raw for records in private_before.values() for _, raw in records)
    assert demo.reopen(path) == marker
    trace = TraceStore(path)
    api = EidosAPI(trace)
    try:
        public = [render_index_html(trace), '\n'.join(trace.db.iterdump())]
        for thread in trace.threads():
            public.extend([json.dumps(thread_payload(trace, thread['thread_id'])), render_thread_html(trace, thread['thread_id'])])
        for mode, identifier in marker['investigations'].items():
            value = demo.call(api, '/' + identifier, method='GET')
            public.append(json.dumps(value))
            public.append(json.dumps(demo.call(api, '/' + identifier + '/context-lineage', method='GET')))
            for context in value['contexts']:
                public.append(json.dumps(demo.call(api, '/' + identifier + '/contexts/' + context['id'] + '/manifest', method='GET')))
            artifact = value.get('nativeArtifact') or value.get('artifact')
            if artifact:
                public.append(json.dumps(demo.call(api, '/' + identifier + '/artifacts/' + artifact['id'] + '/source', method='GET')))
                seq = artifact['outputSeqs'][0]
                payload = thread_payload(trace, trace.get(seq).thread_id, around_seq=seq)
                item = next(item for turn in payload['turns'] for item in turn['items'] if item['recordSeqs'] == [seq])
                assert item['type'] == 'privateResultPublication'
                assert item['id'] == f'publication@{seq}'
                assert item['text'] == artifact['text']
                assert item['provenance']['capsuleId'] == artifact['outputEvidence']['capsuleId']
                assert item['complete'] is True
                record = trace.get(seq)
                assert record.method == '$capsule/result' and record.direction == 'internal'
                assert record.item_id is None
                assert 'Published result' in render_thread_html(trace, record.thread_id)
        assert 'PRIVATE_' not in '\n'.join(public)
    finally:
        api.close()
        trace.close()
    assert totals(path) == private_before


def test_private_result_reuse_keeps_publication_provenance_and_frozen_context(tmp_path):
    path = tmp_path / 'work.db'
    marker = demo.seed(path)
    trace = TraceStore(path)
    api = EidosAPI(trace)
    try:
        source = demo.call(api, '/' + marker['investigations']['conclusion'], method='GET')
        artifact = source['artifact']
        created = demo.call(api, body={'requestId': 'reuse-private-result', 'title': 'Grounded reuse',
            'question': 'Which claims need another source?', 'selections': [],
            'artifactInputs': [{'investigationId': source['id'], 'artifactId': artifact['id'], 'rationale': 'Review this published claim'}]})
        frozen = created['contexts'][0]['artifactInputs'][0]
        assert frozen['artifact'] == artifact
        assert frozen['artifact']['outputEvidence']['kind'] == 'private-capsule-publication'
        assert 'PRIVATE_' not in json.dumps(created)
        assert created['attempt'] is None
    finally:
        api.close()
        trace.close()


def test_private_inquiry_refusal_and_restart_keep_scoped_cause_without_native_resend(tmp_path):
    path = tmp_path / 'work.db'
    marker = demo.seed(path)
    private_before = totals(path)
    trace = TraceStore(path)
    api = EidosAPI(trace)
    identifier = marker['investigations']['inquiry']
    try:
        pending = demo.call(api, '/' + identifier, method='GET')
        continuation = pending['continuation']
        cause = continuation['cause']
        assert cause['schemaVersion'] == 2
        assert cause['nativeEvent']['evidence']['capsuleId'] == pending['nativeArtifact']['outputEvidence']['capsuleId']
        demo.call(api, '/' + identifier + '/inquiries/' + continuation['inquiry']['id'] + '/responses',
                  {'requestId': 'refuse-private', 'decision': 'refuse', 'note': 'No further disclosure in this fixture.'})
        answered = demo.call(api, '/' + identifier + '/resume', {})
        assert answered['continuation']['inquiry']['status'] == 'refused'
        assert answered['continuation']['cause'] == cause
        assert answered['continuation']['nativeNext']['status'] == 'awaiting-admission'
    finally:
        api.close()
        trace.close()
    reopened = TraceStore(path)
    restarted = EidosAPI(reopened)
    try:
        recovered = demo.call(restarted, '/' + identifier, method='GET')
        assert recovered == answered
        assert 'PRIVATE_' not in json.dumps(recovered)
    finally:
        restarted.close()
        reopened.close()
    assert totals(path) == private_before


def one_fixture(tmp_path, mode='conclusion'):
    path = tmp_path / 'one.db'
    trace = TraceStore(path)
    api = EidosAPI(trace)
    api.investigation_worker.close()
    api.investigation_worker.close_evidence()
    api.investigation_worker = PrivateInvestigationWorker(trace, [sys.executable, str(demo.FIXTURE), mode], execution_evidence='synthetic')
    seq = trace.append(source='authored-input', direction='internal', message={
        'method': '$history/item', 'params': {'threadId': 'public-input', 'item': {'id': 'public', 'type': 'agentMessage', 'text': 'Incomplete source.'}}}).seq
    value = demo.call(api, body={'requestId': 'one', 'title': 'One private result', 'question': 'What is supported?',
                               'selections': [{'threadId': 'public-input', 'startSeq': seq, 'endSeq': seq}]})
    return path, trace, api, value


def test_lost_completion_after_publication_recovers_one_artifact_without_resend(tmp_path, monkeypatch):
    path, trace, api, value = one_fixture(tmp_path)
    identifier = value['id']
    def lost(*args, **kwargs):
        raise RuntimeError('PRIVATE_COMPLETION_ERROR_CANARY')
    monkeypatch.setattr(api.investigations, 'complete', lost)
    demo.call(api, '/' + identifier + '/dispatch', {'contextId': value['currentContextId']})
    stopped = demo.wait(api, identifier)
    assert stopped['status'] == 'unknown' and stopped['artifact'] is None
    assert 'PRIVATE_' not in json.dumps(stopped)
    assert len([r for r in trace.records() if r.method == '$capsule/result']) == 1
    api.close()
    trace.close()
    private_before = totals(path)
    reopened = TraceStore(path)
    restarted = EidosAPI(reopened)
    try:
        recovered = demo.call(restarted, '/' + identifier, method='GET')
        assert recovered['status'] == 'completed'
        assert len([r for r in reopened.records() if r.method == '$capsule/result']) == 1
        assert demo.call(restarted, '/' + identifier + '/recover', {}) == recovered
    finally:
        restarted.close()
        reopened.close()
    assert totals(path) == private_before


def test_missing_private_proof_preserves_publication_but_cannot_admit_new_inquiry(tmp_path, monkeypatch):
    path, trace, api, value = one_fixture(tmp_path, 'inquiry')
    identifier = value['id']
    monkeypatch.setattr(api, '_admit_native_inquiry', lambda ident: api.investigations.get(ident))
    demo.call(api, '/' + identifier + '/dispatch', {'contextId': value['currentContextId']})
    saved = demo.wait(api, identifier)
    assert saved['artifact']['kind'] == 'native-needs-evidence' and not saved.get('continuation')
    api.close()
    trace.close()
    for private_path in Path(str(path) + '.private').glob('*/evidence.sqlite'):
        private_path.unlink()  # Only this test's known temporary fixture evidence.
    reopened = TraceStore(path)
    restarted = EidosAPI(reopened)
    try:
        recovered = demo.call(restarted, '/' + identifier, method='GET')
        assert recovered['artifact'] == saved['artifact']
        assert recovered.get('continuation') is None
        assert recovered['inquiryAdmissionError'] == 'Private inquiry evidence is unavailable or invalid.'
    finally:
        restarted.close()
        reopened.close()
