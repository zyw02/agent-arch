"""Observe three native DeepSeek protocols without translating tools or messages.

The real API key stays on the controller. Each run has its own server and disk
directory. Preserve original and effective bodies and timestamped upstream SSE.
Client disconnection does not discard already-billed upstream usage.
"""
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

from accounting import merge_counters, normalize_usage, summarize_requests

ROUTES = {
    '/anthropic/v1/messages': ('messages', '/anthropic/v1/messages'),
    '/v1/messages': ('messages', '/anthropic/v1/messages'),
    '/v1/chat/completions': ('chat', '/chat/completions'),
    '/v1/responses': ('responses', '/responses'),
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('fixed-origin relay refuses redirects')


def effective_request(api, original, limit):
    body = dict(original)
    if body.get('model') != 'deepseek-flash':
        raise ValueError('undeclared model')
    # Native server-side retrieval would evade the no-web task condition.
    for tool in body.get('tools', []):
        kind = tool.get('type', '')
        if kind.startswith(('web_search', 'web_fetch', 'tool_search')):
            raise ValueError('server-side retrieval is outside this task condition')
    if api == 'messages':
        body['thinking'] = dict(type='enabled')
        body['output_config'] = {**body.get('output_config', {}), 'effort': 'high'}
        body['max_tokens'] = limit
    elif api == 'chat':
        body['thinking'] = dict(type='enabled')
        body['reasoning_effort'] = 'high'
        body['max_tokens'] = limit
        body.pop('max_completion_tokens', None)
        if body.get('stream'):
            body['stream_options'] = {**body.get('stream_options', {}), 'include_usage': True}
    elif api == 'responses':
        body['reasoning'] = {**body.get('reasoning', {}), 'effort': 'high'}
        body['max_output_tokens'] = limit
    return body


class Observation:
    def __init__(self, api, row):
        self.api, self.row = api, row
        self.usage = {}
        self.tools = {}

    def event(self, data, now):
        if not isinstance(data, dict):
            return
        row = self.row
        typ = data.get('type')
        response = data.get('response', {}) if self.api == 'responses' else data
        message = data.get('message', {}) if typ == 'message_start' else response
        for key in ('id', 'model'):
            if message.get(key):
                row['response_' + key] = message[key]
        usage = message.get('usage')
        if isinstance(usage, dict):
            self.usage = merge_counters(self.usage, usage)
            row.setdefault('usage_events', []).append(dict(monotonic_ns=now, usage=usage))
        if typ == 'message_stop' or typ in ('response.completed', 'response.incomplete', 'response.failed'):
            row['terminal'] = True
            row['terminal_kind'] = typ
        meaningful = typ in ('content_block_delta', 'response.output_text.delta',
                             'response.reasoning_text.delta', 'response.function_call_arguments.delta',
                             'response.custom_tool_call_input.delta')
        if typ == 'content_block_start':
            block = data.get('content_block', {})
            if block.get('type') == 'tool_use':
                self.tools[str(data.get('index'))] = dict(id=block.get('id'), name=block.get('name'))
                meaningful = True
        if typ == 'response.output_item.done':
            item = data.get('item', {})
            if item.get('type') in ('function_call', 'custom_tool_call'):
                self.tools[item.get('call_id', item.get('id', 'unknown'))] = dict(id=item.get('call_id'), name=item.get('name'))
        for choice in data.get('choices', []):
            delta = choice.get('delta', choice.get('message', {}))
            if delta.get('content') or delta.get('reasoning_content') or delta.get('tool_calls'):
                meaningful = True
            if choice.get('finish_reason') is not None:
                row['finish_reason'] = choice['finish_reason']
            for tool in delta.get('tool_calls', []):
                index = str(tool.get('index', tool.get('id', 'unknown')))
                previous = self.tools.setdefault(index, {})
                if tool.get('id'):
                    previous['id'] = tool['id']
                if tool.get('function', {}).get('name'):
                    previous['name'] = tool['function']['name']
        if meaningful and row.get('first_meaningful_event_ns') is None:
            row['first_meaningful_event_ns'] = now

    def finish(self):
        self.row['raw_usage'] = self.usage or None
        self.row['normalized_usage'] = normalize_usage(self.api, self.usage or None)
        self.row['model_emitted_tool_calls'] = list(self.tools.values())


class Relay:
    def __init__(self, key, bind, output, run_id, maximum_attempts=64, output_limit=16384):
        self.key = key
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.records = []
        self.lock = threading.Lock()
        self.maximum_attempts, self.output_limit = maximum_attempts, output_limit
        self.opener = urllib.request.build_opener(NoRedirect())
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'

            def log_message(self, *args):
                pass

            def send_json(self, status, obj):
                raw = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path in ('/v1/models', '/anthropic/v1/models', '/models'):
                    self.send_json(200, dict(object='list', data=[dict(id='deepseek-flash', object='model')]))
                else:
                    self.send_json(404, dict(error=dict(message='unexposed endpoint')))

            def do_POST(self):
                started = time.monotonic_ns()
                with owner.lock:
                    index = len(owner.records)
                    row = dict(run_id=owner.run_id, request_index=index, path=self.path,
                               started_ns=started, started_utc=datetime.now(timezone.utc).isoformat(),
                               forwarded=False, settled=False, terminal=False,
                               response_bytes=0, raw_usage=None, user_agent=self.headers.get('User-Agent'))
                    owner.records.append(row)
                directory = owner.output / f'{index:04d}'
                directory.mkdir()
                observation = None
                try:
                    route = ROUTES.get(self.path)
                    if route is None:
                        row['blocked_reason'] = 'endpoint_not_admitted'
                        return self.send_json(404, dict(error=dict(message='endpoint not admitted')))
                    api, upstream_path = route
                    row['api'] = api
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= 16 * 1024**2:
                        raise ValueError('request body size')
                    raw = self.rfile.read(size)
                    if len(raw) != size:
                        raise ValueError('incomplete local body')
                    body = json.loads(raw)
                    (directory / 'request.original.json').write_bytes(raw)
                    body = effective_request(api, body, owner.output_limit)
                    forwarded = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode()
                    (directory / 'request.effective.json').write_bytes(forwarded)
                    with owner.lock:
                        attempts = sum(r['forwarded'] for r in owner.records)
                        if attempts >= owner.maximum_attempts:
                            row['blocked_reason'] = 'declared_request_limit'
                        else:
                            row['forwarded'] = True
                    if not row['forwarded']:
                        return self.send_json(429, dict(error=dict(message='declared request limit')))
                    row.update(original_request_bytes=len(raw), upstream_request_bytes=len(forwarded),
                               original_sha256=hashlib.sha256(raw).hexdigest(),
                               effective_sha256=hashlib.sha256(forwarded).hexdigest(),
                               requested_model=body['model'], stream=bool(body.get('stream')))
                    headers = {'Authorization': 'Bearer ' + owner.key, 'Content-Type': 'application/json'}
                    if api == 'messages':
                        headers['x-api-key'] = owner.key
                        headers['anthropic-version'] = self.headers.get('anthropic-version', '2023-06-01')
                        if self.headers.get('anthropic-beta'):
                            headers['anthropic-beta'] = self.headers['anthropic-beta']
                    if self.headers.get('User-Agent'):
                        headers['User-Agent'] = self.headers['User-Agent']
                    req = urllib.request.Request('https://api.deepseek.com' + upstream_path,
                                                 data=forwarded, headers=headers)
                    observation = Observation(api, row)
                    owner.flush()
                    with owner.opener.open(req, timeout=180) as response:
                        row.update(http_status=response.status, headers_ns=time.monotonic_ns(),
                                   upstream_request_id=response.headers.get('x-request-id'),
                                   response_content_type=response.headers.get('Content-Type'))
                        self.send_response(response.status)
                        self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                        self.end_headers()
                        disconnected = False
                        with (directory / 'response.raw').open('wb') as saved, (directory / 'events.jsonl').open('w') as events:
                            if body.get('stream'):
                                for line in response:
                                    now = time.monotonic_ns()
                                    saved.write(line)
                                    row['response_bytes'] += len(line)
                                    if row.get('first_byte_ns') is None:
                                        row['first_byte_ns'] = now
                                    if row['response_bytes'] > 32 * 1024**2:
                                        raise ValueError('response exceeds trace bound')
                                    if not disconnected:
                                        try:
                                            self.wfile.write(line)
                                            self.wfile.flush()
                                        except OSError:
                                            disconnected = True
                                            row['client_disconnected'] = True
                                    if line.startswith(b'data:'):
                                        data = line[5:].strip()
                                        if data == b'[DONE]':
                                            row['terminal'] = True
                                            row['terminal_kind'] = 'done'
                                        elif data:
                                            try:
                                                obj = json.loads(data)
                                            except ValueError:
                                                row['event_parse_error'] = True
                                            else:
                                                events.write(json.dumps(dict(monotonic_ns=now, event=obj), ensure_ascii=False) + '\n')
                                                events.flush()
                                                observation.event(obj, now)
                            else:
                                data = response.read(32 * 1024**2 + 1)
                                saved.write(data)
                                row['response_bytes'] = len(data)
                                if len(data) > 32 * 1024**2:
                                    raise ValueError('response exceeds trace bound')
                                observation.event(json.loads(data), time.monotonic_ns())
                                row['terminal'] = True
                                row['terminal_kind'] = 'json_response'
                                try:
                                    self.wfile.write(data)
                                except OSError:
                                    row['client_disconnected'] = True
                except urllib.error.HTTPError as exc:
                    row.update(http_status=exc.code, error_type='upstream_http')
                    # Error bodies may be useful for protocol diagnosis, but sanitize
                    # the credential explicitly before writing or forwarding them.
                    raw = exc.read(65536).replace(owner.key.encode(), b'[REDACTED]')
                    (directory / 'upstream-error.txt').write_bytes(raw)
                    try:
                        self.send_json(exc.code, dict(error=dict(message=raw.decode(errors='replace'))))
                    except OSError:
                        pass
                except Exception as exc:
                    row.update(error_type=type(exc).__name__, error_message=str(exc).replace(owner.key, '[REDACTED]')[:300])
                    try:
                        self.send_json(502, dict(error=dict(message='benchmark relay request failed')))
                    except OSError:
                        pass
                finally:
                    if observation is not None:
                        observation.finish()
                    row.update(ended_ns=time.monotonic_ns(), settled=True)
                    owner.flush()

        self.server = ThreadingHTTPServer((bind, 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self):
        return f'http://{self.server.server_address[0]}:{self.server.server_port}'

    def flush(self):
        with self.lock:
            records = json.loads(json.dumps(self.records))
            payload = dict(run_id=self.run_id, records=records, summary=summarize_requests(records),
                           credentials_retained=False, protocol_translation=False)
            target = self.output / 'ledger.json'
            temporary = self.output / 'ledger.json.tmp'
            temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
            temporary.replace(target)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.flush()
