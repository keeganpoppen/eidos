"""Seed/reopen a synthetic private-recording investigation fixture for UI checks."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys
import time

from eidos.api import EidosAPI
from eidos.private_investigation import PrivateInvestigationWorker
from eidos.serve import serve
from eidos.trace import TraceStore

MARKER = 'synthetic-private-native-evidence/v1'
FIXTURE = Path(__file__).resolve().parents[1] / 'tests/fixtures/private_investigation_server.py'


class Request:
    def __init__(self, body=None):
        raw = json.dumps(body or {}).encode()
        self.headers = {'Content-Length': str(len(raw)), 'Content-Type': 'application/json'}
        self.rfile = io.BytesIO(raw)


def call(api, path='', body=None, method='POST'):
    status, result = api.dispatch(Request(body), method, '/api/investigations' + path, {})
    if status >= 400:
        raise AssertionError((status, result))
    return result


def wait(api, identifier, inquiry=False):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        value = api.investigations.get(identifier)
        runner = api._investigation_threads.get(identifier)
        if runner is not None and not runner.is_alive():
            if inquiry:
                assert value.get('continuation', {}).get('inquiry'), value
            return value
        time.sleep(.01)
    raise AssertionError('Authored fixture did not stop')


def inspect(api, marker):
    main = '\n'.join(record.raw_text for record in api.store.records())
    assert 'PRIVATE_' not in main
    results = {}
    for mode, identifier in marker['investigations'].items():
        value = call(api, '/' + identifier, method='GET')
        assert 'PRIVATE_' not in json.dumps(value)
        if mode in {'conclusion', 'inquiry'}:
            artifact = value.get('nativeArtifact') or value['artifact']
            assert artifact['outputEvidence']['kind'] == 'private-capsule-publication'
            assert artifact['executionEvidence'] == 'synthetic'
            assert len(artifact['outputSeqs']) == 1
            record = api.store.get(artifact['outputSeqs'][0])
            assert record.direction == 'internal' and record.method == '$capsule/result'
            if mode == 'inquiry':
                cause = value['continuation']['cause']
                assert cause['schemaVersion'] == 2 and 'requestSeq' not in cause
                assert cause['nativeEvent']['evidence']['kind'] == 'private-capsule-record'
            results[mode] = {'artifactId': artifact['id'], 'contextId': artifact['contextId'],
                             'attemptId': artifact['attemptId'], 'outputSeqs': artifact['outputSeqs'],
                             'threadId': value['attempt']['threadId']}
        else:
            assert value['status'] in {'unknown', 'failed'} and value['artifact'] is None
            assert 'PRIVATE_' not in value['attempt']['error']
        lineage = call(api, '/' + identifier + '/context-lineage', method='GET')
        assert 'PRIVATE_' not in json.dumps(lineage)
    assert not any(record.method == 'turn/start' for record in api.store.records())
    return {**marker, 'results': results, 'publicCanariesAbsent': True,
            'realNativeOrModelCalls': 0, 'classification': 'authored-subprocess-fixture'}


def seed(path: Path):
    if path.exists() or Path(str(path) + '.private').exists():
        raise ValueError('Use a new fixture database or --resume this marked fixture.')
    trace = TraceStore(path)
    api = EidosAPI(trace)
    try:
        for i in range(6):
            trace.append(source=MARKER, direction='internal', message={'method': '$fixture/setup', 'params': {'index': i}})
        selections = []
        for name, text in [('decision', 'Keep raw control evidence separate from published conclusions.'),
                           ('experiment', 'A published result must retain its frozen input and recovery identity.')]:
            record = trace.append(source=MARKER, direction='internal', message={
                'method': '$history/item', 'params': {'threadId': name, 'turnId': name + '-turn',
                'item': {'id': name + '-message', 'type': 'agentMessage', 'phase': 'final',
                         'text': text, 'futureFixtureField': {'preserve': True}}}})
            selections.append({'threadId': name, 'startSeq': record.seq, 'endSeq': record.seq, 'rationale': 'Synthetic source support'})
        identifiers = {}
        for mode in ['conclusion', 'inquiry', 'error', 'malformed']:
            api.investigation_worker.close()
            api.investigation_worker.close_evidence()
            api.investigation_worker = PrivateInvestigationWorker(trace, [sys.executable, str(FIXTURE), mode], execution_evidence='synthetic')
            value = call(api, body={'requestId': MARKER + '/' + mode, 'title': 'Private evidence · ' + mode,
                                   'question': 'Which retained evidence supports this result?', 'selections': selections})
            call(api, '/' + value['id'] + '/dispatch', {'contextId': value['currentContextId']})
            wait(api, value['id'], inquiry=mode == 'inquiry')
            identifiers[mode] = value['id']
        marker = {'schemaVersion': MARKER, 'investigations': identifiers}
        trace.append(source=MARKER, direction='internal', message={'method': '$private-evidence/demo', 'params': marker})
        return inspect(api, marker)
    finally:
        api.close()
        trace.close()


def reopen(path: Path):
    trace = TraceStore(path)
    api = None
    try:
        records = [r for r in trace.records() if r.source == MARKER and r.method == '$private-evidence/demo']
        if len(records) != 1:
            raise ValueError('Not a unique marked private-evidence fixture.')
        api = EidosAPI(trace)
        return inspect(api, records[0].message['params'])
    finally:
        if api is not None: api.close()
        trace.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    result = reopen(args.db) if args.resume else seed(args.db)
    if args.output: args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if args.serve:
        # A trusted local fixture command; the production native gate remains closed.
        fake = Path(__file__).resolve().parents[1] / 'tests/fixtures/investigation_appserver.py'
        serve(args.db, port=args.port, codex=str(fake))


if __name__ == '__main__': main()
