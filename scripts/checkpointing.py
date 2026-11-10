"""Checkpoints por arquivo e retomada explícita, sem credenciais ou rede."""
from contextlib import AbstractContextManager
import json
import os
from pathlib import Path
import uuid

VERSION = 'file-v1'


def atomic_text(path, text):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
        stream.flush()
    os.replace(temporary, path)


def write_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, default=str))


class RunLock(AbstractContextManager):
    """O sistema operacional libera o lock mesmo após encerramento abrupto."""
    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.stream = self.path.open('a+b')
        self.stream.seek(0, 2)
        if self.stream.tell() == 0:
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.stream.close()
            raise RuntimeError('Já existe uma execução usando esta pasta') from error
        return self

    def __exit__(self, *args):
        self.stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        self.stream.close()


class FileStore:
    def __init__(self, directory, files):
        self.directory = Path(directory)
        self.files = {row['File']: row for row in files}
        self.folder = self.directory / 'checkpoints'
        self.folder.mkdir(exist_ok=True)
        self.marker = self.directory / 'inflight.json'
        self._paths = None

    def path(self, rel):
        # Preserve old filenames; identify records by their relative source path.
        if self._paths is None:
            self.records()
        if rel in self._paths:
            return self._paths[rel]
        index = sorted(self.files).index(rel) + 1
        return self.folder / f'file-{index:08d}.json'

    def records(self):
        records, paths = {}, {}
        for path in sorted(self.folder.glob('*.json')):
            saved = json.loads(path.read_text(encoding='utf-8'))
            if saved.get('version') != VERSION:
                raise RuntimeError('Versão de checkpoint desconhecida')
            record = saved['record']
            rel = record['file']
            if rel not in self.files:
                raise RuntimeError('Checkpoint não corresponde à seleção congelada')
            if rel in records:
                raise RuntimeError('Checkpoint duplicado ou com identidade incorreta')
            records[rel] = record
            paths[rel] = path
        self._paths = paths
        return records

    def start(self, item):
        if self.marker.exists():
            raise RuntimeError('Arquivo interrompido ainda não foi reconhecido')
        write_json(self.marker, dict(file=item['File'], id=uuid.uuid4().hex))

    def commit(self, record):
        rel = record['file']
        path = self.path(rel)
        write_json(path, dict(version=VERSION, record=record))
        self._paths[rel] = path
        if self.marker.exists():
            self.marker.unlink()

    def recover(self, allow_uncertain=False):
        records = self.records()
        if self.marker.exists():
            marker = json.loads(self.marker.read_text(encoding='utf-8'))
            rel = marker['file']
            if rel not in self.files:
                raise RuntimeError('Marcador de interrupção não corresponde à seleção')
            if rel not in records:
                if not allow_uncertain:
                    raise RuntimeError('Há arquivo interrompido com possível cobrança. '
                                       'Use --resume PASTA --retry-interrupted para autorizá-lo explicitamente.')
                path = self.directory / 'interruption_events.json'
                events = json.loads(path.read_text()) if path.exists() else []
                if not any(event['id'] == marker['id'] for event in events):
                    events.append(dict(marker, cost_unknown=True))
                    write_json(path, events)
            self.marker.unlink()
        return records

    def uncertainty(self):
        path = self.directory / 'interruption_events.json'
        return json.loads(path.read_text()) if path.exists() else []


def verify_resume(output, snapshots, files, models, prompts, architecture, parameters=None):
    output = Path(output)
    config = json.loads((output / 'config.json').read_text(encoding='utf-8'))
    if config.get('checkpoint_version') != VERSION:
        raise RuntimeError('Esta rodada antiga não possui checkpoints retomáveis; não será sobrescrita')
    if config['architecture'] != architecture or list(config['models']) != models or config['prompt_types'] != prompts:
        raise RuntimeError('Condições da execução mudaram; retomada bloqueada')
    keys = ('max_tokens', 'max_retry_tokens', 'response_retries', 'max_retries', 'timeout',
            'concurrency', 'sequential', 'generation_profile', 'generation_seed', 'temperature',
            'reasoning', 'provider', 'provider_for', 'response_format', 'json_normalization',
            'max_lines', 'max_file_kb', 'no_evaluate', 'output_layout')
    if parameters is not None and any(config['parameters'].get(k) != parameters.get(k) for k in keys):
        raise RuntimeError('Parâmetros mudaram; retomada bloqueada')
    if parameters and parameters.get('generation_config'):
        generation = json.loads((output / 'generation_protocol.json').read_text())
        fields = ('profile', 'model', 'provider', 'reasoning', 'temperature', 'seed',
                  'response_format', 'json_normalization', 'strict', 'require_parameters')
        for name, current in parameters['generation_config'].items():
            if name not in generation or any(generation[name].get(k) != current.get(k) for k in fields):
                raise RuntimeError('Parâmetros efetivos do provedor mudaram')
    saved = json.loads((output / 'sample.json').read_text(encoding='utf-8'))['files']
    if sorted(row['File'] for row in saved) != sorted(row['File'] for row in files):
        raise RuntimeError('Seleção mudou; retomada bloqueada')
    return config
