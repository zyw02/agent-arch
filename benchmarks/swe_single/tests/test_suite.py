"""Expanded campaign admission, memory isolation and runtime proof."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import agent_entry
import idle_native_entry
from agentloop_app import prepare_default_app
from live_observation import validate_agentloop
from suite import selected_protocol, shard_summary
from run import replace_task_source


class SuiteTests(unittest.TestCase):
    def test_aios_uses_native_complex_loop_without_a_custom_executor_or_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            apps=prepare_default_app(Path(temp))
            config=json.loads((apps/'default/agent.app.json').read_text())
            self.assertEqual(config,dict(app_name='default',loop_mode=[dict(id='main',type='complex')]))
            self.assertEqual((apps/'default/index.js').read_text(),'export {};\n')
    def test_new_snapshot_keeps_generated_editable_install_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); initial=root/'initial'; source=root/'source'
            for path in (initial,source):
                (path/'src/_pytest').mkdir(parents=True)
            (initial/'src/_pytest/_version.py').write_text('version = "6.0.0rc1"\n')
            (initial/'src/pytest.egg-info').mkdir()
            (initial/'src/pytest.egg-info/PKG-INFO').write_text('Name: pytest\nVersion: 6.0.0rc1\n')
            (initial/'src/_pytest/implementation.py').write_text('old code')
            (source/'src/_pytest/implementation.py').write_text('frozen new-task code')
            replace_task_source(initial,source)
            self.assertEqual((initial/'src/_pytest/_version.py').read_text(),'version = "6.0.0rc1"\n')
            self.assertTrue((initial/'src/pytest.egg-info/PKG-INFO').exists())
            self.assertEqual((initial/'src/_pytest/implementation.py').read_text(),'frozen new-task code')
            self.assertFalse((source/'src/_pytest/_version.py').exists())

    def test_frozen_four_task_scope_and_all_timeout_layers(self):
        original = (HERE/'protocol-six.json').read_bytes()
        selection = json.loads((HERE/'suite-selection.json').read_text())
        self.assertEqual(len(selection['tasks']), 4)
        self.assertEqual(len({t['instance_id'] for t in selection['tasks']}), 4)
        for entry in selection['tasks']:
            path = HERE/entry['task_file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry['task_sha256'])
            self.assertEqual(json.loads(path.read_text())['difficulty'], '15 min - 1 hour')
            c = selected_protocol('openclaw57_patched', entry['instance_id'])['execution']
            self.assertEqual(c['task_timeout_seconds'], 1800)
            self.assertEqual(c['smoke_timeout_seconds'], 540)
            self.assertEqual(c['grading_timeout_seconds'], 540)
            self.assertEqual(c['provider_request_timeout_seconds'], 540)
            self.assertEqual(c['controller_deadline_seconds'], 43200)
            self.assertEqual(c['memory_bytes'], 8*1024**3)
            self.assertEqual(c['cpus'], 2)
            self.assertFalse(c['cross_run_memory'])
        self.assertEqual((HERE/'protocol-six.json').read_bytes(), original)
        with self.assertRaises(ValueError):
            selected_protocol('openclaw57_patched', 'unfrozen-task')

    def test_new_aios_launcher_selects_sdk_without_changing_other_versions(self):
        saved = {}
        def write(path, text):
            saved[str(path)] = text
        with patch.object(agent_entry, 'write', write), \
             patch.object(Path, 'read_text', lambda p: saved[str(p)]), \
             patch.dict('os.environ', dict(BENCH_RUN_ID='isolated-repeat',
                        BENCH_AIOS_RUNTIME='agentloop', BENCH_TASK_TIMEOUT_SECONDS='1800')), \
             patch('os.execvpe') as execute:
            agent_entry.launch('openclaw57_patched', 'http://relay', 'original issue')
        command, env = execute.call_args.args[1:]
        self.assertEqual(command[:3], ['node', '/opt/openclaw57/openclaw.mjs', 'agent'])
        self.assertEqual(env['OPENCLAW_AGENT_RUNTIME'], 'agentloop')
        self.assertEqual(env['AGENTLOOP_WARMUP'], '0')
        config = json.loads(saved['/home/bench/.openclaw/openclaw.json'])
        self.assertEqual(config['agents']['defaults']['agentRuntime']['id'], 'agentloop')
        self.assertEqual(config['agents']['defaults']['timeoutSeconds'], 1800)
        self.assertTrue(config['plugins']['entries']['agentloop']['enabled'])

    def test_configuration_alone_cannot_prove_sdk_was_used(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp); (home/'.openclaw').mkdir()
            path = home/'.openclaw/openclaw.json'
            path.write_text(json.dumps(dict(agents=dict(defaults=dict(agentRuntime=dict(id='agentloop'))))))
            self.assertFalse(validate_agentloop(home, 'PI completed normally')['valid'])
            self.assertTrue(validate_agentloop(home, '[agentloop] loop.run starting agentId=main')['valid'])

    def test_missing_attempts_remain_incomplete_and_failures_are_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for i in (1, 2):
                target = root/'segments'/f'block-{i}'; target.mkdir(parents=True)
                result = dict(run_id=f'block-{i}-codex', smoke=False, resolved=False,
                              termination='timeout', wall_seconds=1800, native_execution_ok=False)
                (target/'summary.json').write_text(json.dumps(dict(results=[result])))
            summary = shard_summary(root, 'task', 'codex')
            self.assertEqual(summary['formal_completed'], 2)
            self.assertFalse(summary['complete'])
            self.assertEqual(summary['runs'][0]['wall_seconds'], 1800)
            with self.assertRaises(ValueError):
                shard_summary(root, 'task', 'codex', require_complete=True)

    def test_initial_idle_launchers_receive_no_task_and_use_only_disposable_credentials(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(idle_native_entry, 'ROOT', Path(temp)):
            for product in ('openclaw57_patched','openclaw','dsh','codex','claude','hermes'):
                app = idle_native_entry.Application(product, 1, 'http://127.0.0.1:9')
                self.assertNotIn('-p', app.command)
                self.assertNotIn('-z', app.command)
                self.assertNotIn('exec', app.command)
                self.assertNotIn('--message', app.command)
                self.assertNotIn('/root/workspace', ' '.join(app.command))
                self.assertEqual(app.cwd, Path('/testbed'))
                if product=='openclaw57_patched':
                    self.assertEqual(app.env['OPENCLAW_AGENT_RUNTIME'],'agentloop')
                    self.assertEqual(app.env['AGENTLOOP_WARMUP'],'0')
                    self.assertIn('--max-old-space-size=700',app.command)
                self.assertFalse(any('sk-' in v for v in app.env.values()))


if __name__ == '__main__':
    unittest.main()
