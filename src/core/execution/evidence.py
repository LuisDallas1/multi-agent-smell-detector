"""Journal de evidencias por tentativa, independente do checkpoint de arquivo."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import time
import uuid

VERSION = 'evidence-v1'
_ACTIVE = ContextVar('experiment_evidence_attempt', default=None)


class EvidenceWriteError(BaseException):
    """Fail-stop: SDKs nao devem transformar falha de disco em retry de API."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


class EvidenceStore:
    """Eventos atomicos, com hash e cadeia por sessao; nunca contem credenciais."""

    def __init__(self, directory):
        self.root = Path(directory) / 'evidence'
        self.root.mkdir(parents=True, exist_ok=True)
        self.verify(directory)  # Do not hide a missing/corrupt previous session by creating a new one.
        self.session = uuid.uuid4().hex
        self.folder = self.root / self.session
        self.folder.mkdir()
        registry = self.root / 'sessions.json'
        temporary = self.root / f'sessions-{self.session}.tmp'
        try:
            with temporary.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(json.dumps(dict(version=VERSION,
                    sessions=sorted(p.name for p in self.root.iterdir() if p.is_dir()))))
                stream.flush()
            os.replace(temporary, registry)
        except Exception as error:
            raise EvidenceWriteError('Nao foi possivel registrar sessao de evidencias; envio bloqueado') from error
        self.sequence, self.previous = 0, None
        self.failed = False
        self.failure_error = None
        self.secrets = []
        self.file_context = {}
        self.http_usage = {}

    def register_secret(self, value):
        if hasattr(value, 'get_secret_value'):
            value = value.get_secret_value()
        if isinstance(value, str) and value:
            self.secrets.append(value)

    def clean(self, value):
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, '[REDACTED]')
            return value
        if isinstance(value, dict):
            return {str(k): self.clean(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [self.clean(v) for v in value]
        if hasattr(value, 'model_dump'):
            return self.clean(value.model_dump(mode='json'))
        return value

    def emit(self, stage, payload, *, attempt_id=None):
        if self.failed:
            raise EvidenceWriteError('Gravacao de evidencias falhou; novas chamadas bloqueadas') from self.failure_error
        active = _ACTIVE.get()
        attempt_id = attempt_id or (active[1] if active and active[0] is self else None)
        event = self.clean(dict(version=VERSION, session=self.session, sequence=self.sequence + 1,
            previous_sha256=self.previous, timestamp_utc=datetime.now(timezone.utc).isoformat(),
            stage=stage, attempt_id=attempt_id, file_context=dict(self.file_context), payload=payload))
        try:
            data = json.dumps(event, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')
            checksum = digest(data)
            envelope = json.dumps(dict(event=event, sha256=checksum), ensure_ascii=False,
                                  indent=2, default=str)
            destination = self.folder / f'{self.sequence + 1:08d}.json'
            temporary = destination.with_suffix('.tmp')
            with temporary.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(envelope)
                stream.flush()
            if destination.exists():
                raise OSError('Evento ja existe; nao sobrescrever')
            self._replace(temporary, destination)
            # The index detects removal of a confirmed tail, not just gaps in the chain.
            head = self.folder / 'head.json'
            head_temp = self.folder / 'head.tmp'
            with head_temp.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(json.dumps(dict(sequence=self.sequence + 1, sha256=checksum)))
                stream.flush()
            self._replace(head_temp, head)
        except Exception as error:
            self.failed = True
            self.failure_error = error
            raise EvidenceWriteError('Nao foi possivel confirmar evidencias em disco; coleta interrompida') from error
        self.sequence += 1
        self.previous = checksum
        return destination

    @staticmethod
    def _replace(source, destination):
        """Windows pode bloquear rename enquanto um leitor segura o destino.

        Repetir apenas a operação de disco, sem reemitir evento ou chamada LLM.
        Falha persistente continua interrompendo a coleta com a causa original.
        """
        for attempt in range(8):
            try:
                os.replace(source, destination)
                return
            except PermissionError as error:
                if os.name != 'nt' or getattr(error, 'winerror', None) not in {5, 32, 33} or attempt == 7:
                    raise
                time.sleep(min(.1, .01 * 2 ** attempt))

    def start_file(self, rel, source, code):
        self.file_context = dict(file=rel, source_sha256=digest(source), execution_id=uuid.uuid4().hex)
        # Base64 retains BOM/newlines/encoding bytes; code is the exact text passed to the engine.
        self.emit('file_started', dict(source_base64=base64.b64encode(source).decode('ascii'),
                                       source_bytes=len(source), inference_code=code))

    @contextmanager
    def attempt(self, agent, number, budget):
        identifier = uuid.uuid4().hex
        token = _ACTIVE.set((self, identifier))
        started = time.monotonic()
        try:
            self.emit('attempt_started', dict(agent=agent, number=number, max_tokens=budget))
            yield identifier
        except BaseException as error:
            if not self.failed:
                self.emit('attempt_interrupted', dict(exception_type=type(error).__name__))
            raise
        finally:
            try:
                if not self.failed:
                    self.emit('attempt_closed', dict(elapsed_seconds=time.monotonic() - started))
            finally:
                _ACTIVE.reset(token)

    def body(self, data):
        text = data.decode('utf-8', errors='replace')
        cleaned = self.clean(text)
        redacted = cleaned != text
        # Do not retain an unredacted copy in base64 if a known key was echoed.
        retained = cleaned.encode('utf-8') if redacted else data
        return dict(text=cleaned, base64=base64.b64encode(retained).decode('ascii'),
                    sha256=digest(retained), bytes=len(retained), credential_redacted=redacted)

    @staticmethod
    def public_headers(headers):
        allowed = {'content-type', 'content-length', 'date', 'retry-after', 'x-request-id',
                   'request-id', 'cf-ray', 'openrouter-generation-id', 'content-encoding'}
        return {key: value for key, value in headers.items()
                if key.lower() in allowed or key.lower().startswith('x-ratelimit-')}

    async def on_request(self, request):
        active = _ACTIVE.get()
        if not active or active[0] is not self:
            raise EvidenceWriteError('Pedido sem identidade de tentativa; envio bloqueado')
        data = await request.aread()
        self.emit('http_request', dict(method=request.method,
            url=str(request.url.copy_with(username=None, password=None, query=None, fragment=None)),
            headers=self.public_headers(request.headers), body=self.body(data)))

    async def on_response(self, response):
        # Reading here captures even choices=null, invalid JSON, and HTTP failures before SDK parsing.
        import httpx
        store = self
        original = response.stream

        class LoggedStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                async for chunk in original:
                    store.emit('http_response_chunk', dict(body=store.body(chunk)))
                    yield chunk

            async def aclose(self):
                await original.aclose()

        self.emit('http_response_headers', dict(status_code=response.status_code,
            headers=self.public_headers(response.headers)))
        if not response.is_stream_consumed:
            response.stream = LoggedStream()
        try:
            data = await response.aread()
        except BaseException as error:
            if not self.failed:
                self.emit('http_response_incomplete', dict(status_code=response.status_code,
                                                         exception_type=type(error).__name__))
            raise
        self.emit('http_response', dict(status_code=response.status_code,
            headers=self.public_headers(response.headers), body=self.body(data)))
        active = _ACTIVE.get()
        if active and active[0] is self:
            try:
                payload = json.loads(data)
                if isinstance(payload.get('usage'), dict):
                    self.http_usage[active[1]] = payload['usage']
            except (ValueError, AttributeError):
                pass

    def current_usage(self):
        active = _ACTIVE.get()
        return self.http_usage.get(active[1]) if active and active[0] is self else None

    def hooks(self):
        return dict(request=[self.on_request], response=[self.on_response])

    @classmethod
    def iter_events(cls, directory):
        root = Path(directory) / 'evidence'
        if (root / 'sessions.json').exists():
            registry = json.loads((root / 'sessions.json').read_text(encoding='utf-8'))
            folders = {p.name for p in root.iterdir() if p.is_dir()}
            if registry['version'] != VERSION or not set(registry['sessions']) <= folders:
                raise RuntimeError('Sessao registrada de evidencias esta ausente')
        for folder in sorted(root.iterdir()) if root.exists() else []:
            if not folder.is_dir():
                continue
            previous = None
            session_checksums = []
            # Ler o índice antes de listar eventos evita confrontar uma lista
            # antiga com um head mais novo durante uma leitura concorrente.
            head = json.loads((folder / 'head.json').read_text(encoding='utf-8')) if (folder / 'head.json').exists() else None
            for sequence, path in enumerate(sorted(folder.glob('[0-9]*.json')), 1):
                envelope = json.loads(path.read_text(encoding='utf-8'))
                event = envelope['event']
                checksum = digest(json.dumps(event, ensure_ascii=False, sort_keys=True,
                                             default=str).encode('utf-8'))
                if (checksum != envelope['sha256'] or event['version'] != VERSION
                        or event['session'] != folder.name or event['sequence'] != sequence
                        or path.name != f'{sequence:08d}.json' or event['previous_sha256'] != previous):
                    raise RuntimeError('Journal de evidencias alterado, incompleto ou corrompido')
                session_checksums.append(checksum)
                previous = checksum
                yield event
            if head is not None:
                count = head['sequence']
                if (not isinstance(count, int) or count < 1 or count > len(session_checksums)
                        or session_checksums[count - 1] != head['sha256']):
                    raise RuntimeError('Cauda confirmada do journal ausente ou corrompida')

    @classmethod
    def events(cls, directory):
        return list(cls.iter_events(directory))

    @classmethod
    def verify(cls, directory):
        return sum(1 for _ in cls.iter_events(directory))

    @classmethod
    def summarize(cls, directory):
        committed = set()
        event_count = 0
        calls = {}
        for event in cls.iter_events(directory):
            event_count += 1
            if event['stage'] == 'file_committed':
                committed.add(event['file_context'].get('execution_id'))
            identifier = event['attempt_id']
            if not identifier:
                continue
            item = calls.setdefault(identifier, dict(attempt_id=identifier,
                file_context=event['file_context'], http_requests=0, http_responses=0,
                completed=False, interrupted=False, cost_usd=None, token_usage=None))
            payload = event['payload']
            if event['stage'] == 'http_request':
                item['http_requests'] += 1
            if event['stage'] == 'http_response':
                item['http_responses'] += 1
                try:
                    usage = json.loads(payload['body']['text']).get('usage') or {}
                    value = usage.get('cost')
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
                        item['cost_usd'] = value
                    item['token_usage'] = usage
                except (ValueError, AttributeError):
                    pass
            if event['stage'] == 'attempt_completed':
                item['completed'] = True
                item['error'] = payload['metrics'].get('error')
                if payload['metrics'].get('cost_usd') is not None:
                    item['cost_usd'] = payload['metrics']['cost_usd']
            if event['stage'] == 'attempt_interrupted':
                item['interrupted'] = True
        for item in calls.values():
            item['file_committed'] = item['file_context'].get('execution_id') in committed
        temporary = [dict(path=str(p.relative_to(Path(directory))), bytes=p.stat().st_size,
                          sha256=digest(p.read_bytes())) for p in (Path(directory)/'evidence').rglob('*.tmp')]
        return dict(version=VERSION, event_count=event_count, attempts=list(calls.values()),
            uncommitted_temporary_files=temporary,
            known_cost_usd=sum(c['cost_usd'] or 0 for c in calls.values()),
            uncommitted_known_cost_usd=sum(c['cost_usd'] or 0 for c in calls.values() if not c['file_committed']),
            note='Journal retains interrupted work too. Do not add its full cost to checkpoint costs: overlap exists. '
                 'No response or missing usage means unknown billing, never assumed zero.')
