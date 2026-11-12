"""Idle gateways must not schedule background heartbeat agent turns."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import idle_native_entry as idle


class IdleNoTaskTests(unittest.TestCase):
    def test_both_gateway_profiles_explicitly_disable_heartbeat_task_generation(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(idle, 'ROOT', Path(temp)), \
             patch('agentloop_app.prepare_default_app'), \
             patch.dict(os.environ, {'BENCH_AIOS_CONTEXT_MODEL':'deepseek-flash[1m]',
                                      'BENCH_USE_ALL_ALLOCATED_CPUS':'1'}):
            for product in ('openclaw57_patched','openclaw'):
                app=idle.Application(product,1,'http://127.0.0.1:9')
                config=json.loads((app.home/'.openclaw/openclaw.json').read_text())
                self.assertEqual(config['agents']['defaults']['heartbeat']['every'],'0m')
                self.assertFalse(config['cron']['enabled'])
                self.assertEqual(app.cpus,sorted(os.sched_getaffinity(0)))

    def test_no_inference_stub_records_heartbeat_cause_and_never_returns_fake_model_output(self):
        trap=idle.NoInference()
        try:
            payload=json.dumps(dict(model='deepseek-flash[1m]',messages=[dict(role='user',
                content='Read HEARTBEAT.md if it exists (workspace context).')])).encode()
            request=urllib.request.Request(trap.base+'/v1/chat/completions',data=payload,
                headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request,timeout=3)
            self.assertEqual(error.exception.code,400)
            self.assertEqual(trap.requests[0]['purpose'],'heartbeat')
            self.assertEqual(trap.requests[0]['body_sha256'],hashlib.sha256(payload).hexdigest())
            self.assertNotIn('messages',trap.requests[0])
        finally:
            trap.close()
