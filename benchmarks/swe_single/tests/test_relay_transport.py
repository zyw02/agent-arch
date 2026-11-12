"""Exercise byte preservation and failures after SSE headers have been sent."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relay import Relay


class RelayTransportTests(unittest.TestCase):
    def observe(self, payload, fail=False):
        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Type': 'text/event-stream', 'Transfer-Encoding': 'chunked'}
            def __next__(self):
                line = self.readline()
                if line:
                    return line
                if fail:
                    raise ConnectionResetError('fixture upstream reset')
                raise StopIteration
        class Opener:
            def open(self, *args, **kwargs):
                return Response(payload)
        with tempfile.TemporaryDirectory() as temp:
            relay = Relay('fixture', '127.0.0.1', temp, 'transport')
            relay.opener = Opener()
            try:
                request = urllib.request.Request(relay.base + '/anthropic/v1/messages',
                    data=json.dumps(dict(model='deepseek-flash', stream=True)).encode())
                with urllib.request.urlopen(request, timeout=3) as response:
                    received = response.read()
                deadline = time.monotonic()+3
                while not relay.records[0]['settled'] and time.monotonic()<deadline:
                    time.sleep(.01)
                return received, dict(relay.records[0])
            finally:
                relay.close()

    def test_complete_crlf_utf8_stream_preserved_byte_for_byte(self):
        payload = ('event: content_block_delta\r\ndata: '+json.dumps(dict(type='content_block_delta',
            delta=dict(text='中文')), ensure_ascii=False)+'\r\n\r\n'+
            'data: {"type":"message_delta","usage":{"output_tokens":2}}\r\n\r\n'+
            'data: {"type":"message_stop"}\r\n\r\n').encode()
        received, row = self.observe(payload)
        self.assertEqual(received, payload)
        self.assertTrue(row['transport_bytes_match'])
        self.assertEqual(row['stream_end'], 'terminal_complete')
        self.assertEqual(row['upstream_body_sha256'], hashlib.sha256(payload).hexdigest())
        self.assertTrue(row['final_usage_observed'])

    def test_early_eof_is_reported_without_fabricating_terminal_or_usage(self):
        payload = b'data: {"type":"content_block_delta"}\n\n'
        received, row = self.observe(payload)
        self.assertEqual(received, payload)
        self.assertEqual(row['stream_end'], 'upstream_eof_without_terminal')
        self.assertFalse(row['terminal'])
        self.assertFalse(row['final_usage_observed'])

    def test_late_read_error_never_inserts_second_http_response_into_sse(self):
        payload = b'data: {"type":"content_block_delta"}\n\n'
        received, row = self.observe(payload, fail=True)
        self.assertEqual(received, payload)
        self.assertNotIn(b'HTTP/1.0 502', received)
        self.assertEqual(row['stream_end'], 'upstream_read_error')
        self.assertEqual(row['error_type'], 'ConnectionResetError')
