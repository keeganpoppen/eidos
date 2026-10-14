"""Explicitly authored files for offline history-import acceptance; no native calls."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from eidos.serve import serve

SCHEMA = 'synthetic-history-import/v1'


def create_files(directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    messages = [
        {'method': 'item/completed', 'params': {'threadId': 'import-fixture-design', 'turnId': 'design-turn', 'item': {
            'id': 'decision', 'type': 'agentMessage', 'text': 'Persist the reviewed file and receipt in one atomic commit.',
            'futureField': {'retained': ['UNKNOWN_IMPORT_CANARY', 17]}}}, 'futureEnvelope': {'literal': '<script>not executable</script>'}},
        {'futureUnknownRecord': {'retained': True, 'text': 'UNKNOWN_ONLY_IMPORT_CANARY'}},
        {'method': 'item/completed', 'params': {'threadId': 'import-fixture-counterexample', 'turnId': 'counter-turn', 'item': {
            'id': 'counterexample', 'type': 'agentMessage', 'text': 'A lost import reply must not duplicate the recorded history.'}}},
        {'method': 'item/agentMessage/delta', 'params': {'threadId': 'import-fixture-design', 'turnId': 'repeat-turn',
            'itemId': 'repeated-delta', 'delta': 'echo '}},
        {'method': 'item/agentMessage/delta', 'params': {'threadId': 'import-fixture-design', 'turnId': 'repeat-turn',
            'itemId': 'repeated-delta', 'delta': 'echo '}},
        {'method': 'item/agentMessage/delta', 'params': {'threadId': 'import-fixture-design', 'turnId': 'split-turn',
            'itemId': 'split-answer', 'delta': 'A copper '}},
        {'method': 'item/completed', 'params': {'threadId': 'import-fixture-design', 'turnId': 'split-turn', 'item': {
            'id': 'interleaved', 'type': 'agentMessage', 'text': 'Unrelated interleaved record must remain outside split support.'}}},
        {'method': 'item/agentMessage/delta', 'params': {'threadId': 'import-fixture-design', 'turnId': 'split-turn',
            'itemId': 'split-answer', 'delta': 'bridge keeps exact source membership.'}},
    ]
    lines = [json.dumps(m, ensure_ascii=False, separators=(',', ':')).encode() for m in messages]
    # Intentionally preserve blank lines, CRLF/LF and an unterminated final line.
    data = b'\r\n' + lines[0] + b'\r\n' + lines[1] + b'\n\t \r\n' + b'\r\n'.join(lines[2:])
    files = {'valid': data, 'malformed': data+b'\r\n{broken',
             'unsupported': b'{"unrecognizedExport":{"text":"retained only"}}\r\n',
             'different': data.replace(b'copper bridge', b'silver bridge') if b'copper bridge' in data else data.replace(b'A copper ', b'A silver ')}
    result = {}
    for name, raw in files.items():
        path=directory/(name+'.jsonl')
        if path.exists() and path.read_bytes()!=raw:
            raise ValueError('Refusing to overwrite a different fixture file: '+str(path))
        path.write_bytes(raw)
        result[name]={'path':str(path.resolve()),'sha256':hashlib.sha256(raw).hexdigest(),'byteLength':len(raw)}
    return {'schemaVersion':SCHEMA,'classification':'authored-public-jsonl','nativeOrModelCalls':0,
        'files':result,'recordCount':len(messages),'threads':['import-fixture-design','import-fixture-counterexample'],
        'queries':{'decision':'reviewed file and receipt','counterexample':'lost import reply','split':'copper bridge','repeated':'echo echo'},
        'source':'authored-history-import','direction':'appserver_to_client'}


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--db',type=Path)
    parser.add_argument('--serve',action='store_true')
    parser.add_argument('--port',type=int,default=8767)
    args=parser.parse_args()
    marker=create_files(args.directory)
    (args.directory/'marker.json').write_text(json.dumps(marker,indent=2)+'\n')
    print(json.dumps(marker,indent=2),flush=True)
    if args.serve:
        if args.db is None: parser.error('--serve requires --db')
        # This reusable fixture helper must never recover an unrelated database.
        # Exclusive creation is an accidental-use guard, not authentication.
        database=args.db.expanduser().resolve()
        database.parent.mkdir(parents=True,exist_ok=True)
        if any(Path(str(database)+suffix).exists() for suffix in ('-wal','-shm','-journal')):
            raise ValueError('Fixture serving requires a fresh database without sidecars')
        with database.open('xb'):
            pass
        serve(database,port=args.port)


if __name__=='__main__': main()
