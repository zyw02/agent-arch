"""Exercise new input admission and native adapter boundaries without models."""
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import agent_entry
from native import inspect_native
from prepare_enhanced import require_inputs, verify_vendor
from reconcile import project
from sealed_input import transform


class EnhancedAdmissionTests(unittest.TestCase):
    def test_missing_sdk_stops_before_a_build_or_model_run(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('prepare_enhanced.INPUTS', Path(temp)):
                with self.assertRaisesRegex(FileNotFoundError, 'vendor package'):
                    require_inputs(dict(sealed_inputs={}))

    def test_sealed_input_roundtrip_and_corruption_rejected_by_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plain, sealed, decoded = root/'plain', root/'sealed.enc', root/'decoded'
            plain.write_bytes(b'private build input\x00' * 100)
            transform(plain, sealed, passphrase='test-key-not-a-real-credential')
            transform(sealed, decoded, decrypt=True, passphrase='test-key-not-a-real-credential')
            self.assertEqual(plain.read_bytes(), decoded.read_bytes())
            manifest = dict(sealed_inputs={sealed.name: hashlib.sha256(sealed.read_bytes()).hexdigest(),
                                           'agentloop-sdk.tgz.enc': 'not-used'})
            sealed.write_bytes(sealed.read_bytes() + b'corrupted')
            with patch('prepare_enhanced.INPUTS', root):
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    require_inputs(manifest)

    def test_sdk_requires_the_supplied_lock_integrity_and_package_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'sdk.tgz'
            with tarfile.open(path, 'w:gz') as archive:
                content = json.dumps(dict(name='@zte/agentloop-sdk', version='test')).encode()
                member = tarfile.TarInfo('package/package.json')
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            integrity = 'sha512-' + base64.b64encode(hashlib.sha512(path.read_bytes()).digest()).decode()
            verify_vendor(path, integrity)
            with self.assertRaisesRegex(ValueError, 'lockfile integrity'):
                verify_vendor(path, 'sha512-wrong')

    def test_source_build_is_selected_with_the_older_native_exec_policy(self):
        saved = {}
        def capture(path, text):
            saved[str(path)] = text
        def read(path, *args, **kwargs):
            return saved[str(path)]
        with patch.object(agent_entry, 'write', capture), \
             patch.object(Path, 'read_text', read), \
             patch.dict('os.environ', BENCH_RUN_ID='smoke-openclaw57_patched'), \
             patch('os.execvpe') as execute:
            agent_entry.launch('openclaw57_patched', 'http://relay', 'unchanged task')
        command, env = execute.call_args.args[1:]
        self.assertEqual(command[:3], ['node', '/opt/openclaw57/openclaw.mjs', 'agent'])
        self.assertEqual(command[-1], 'unchanged task')
        config = json.loads(saved['/home/bench/.openclaw/openclaw.json'])
        self.assertEqual(config['tools']['exec'], dict(security='full', ask='off'))
        self.assertEqual(config['agents']['defaults']['model']['primary'], 'deepseek/deepseek-flash')
        self.assertNotIn('DEEPSEEK_API_KEY', {k:v for k,v in env.items() if v == 'benchmark-relay-only'})

    def test_57_native_result_uses_openclaw_projection_without_unknown_as_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home, out = root/'home', root/'out'
            home.mkdir(); out.mkdir()
            stdout = root/'stdout'
            stdout.write_text(json.dumps(dict(meta=dict(agentMeta=dict(usage=dict(
                input=80, cacheRead=20, cacheWrite=0, output=10))))))
            native = inspect_native('openclaw57_patched', home, stdout, out)
            counters = project('openclaw57_patched', native)
            self.assertEqual(counters['input_total'], 100)
            self.assertEqual(counters['output_total'], 10)
            self.assertIsNone(native['native_tool_calls'])


if __name__ == '__main__':
    unittest.main()
