"""Regress auxiliary-summary corruption, ignored budgets and host mismatch."""
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from argparse import Namespace

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import agent_entry
from relay import Observation, Relay, effective_request
from suite import selected_protocol
from run import Campaign
from validated_controls import (check_response_integrity, fixed_runner_admission,
                                 control_source_hashes, require_protocol_preflight)


class ValidatedControlTests(unittest.TestCase):
    def test_old_paid_entrypoint_is_blocked_before_credentials_or_docker(self):
        with patch.dict('os.environ',{'BENCH_ALLOW_LEGACY_REPRODUCTION':''}):
            with self.assertRaisesRegex(ValueError,'historical only'):
                Campaign(Namespace(protocol=HERE/'protocol-six.json'))

    def test_live_receipt_is_bound_to_all_six_probes_and_current_control_code(self):
        with self.assertRaises(ValueError):
            require_protocol_preflight(None)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'receipt.json'
            receipt=dict(complete=True,probes=[dict(api=api,mode=mode)
                for api in ('chat','messages','responses') for mode in ('main-high','auxiliary-disabled')],
                response_integrity=dict(clean=True),accounting=dict(usage_complete=True),
                control_source_hashes=control_source_hashes())
            path.write_text(json.dumps(receipt))
            self.assertTrue(require_protocol_preflight(path)['passed'])
            receipt['control_source_hashes']['relay.py']='different code'
            path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'different controller code'):
                require_protocol_preflight(path)

    def test_auxiliary_reasoning_and_smaller_budget_survive_all_protocols(self):
        for api in ('chat', 'messages', 'responses'):
            with self.subTest(api=api):
                request = dict(model='deepseek-flash', stream=True)
                if api == 'responses':
                    request.update(reasoning=dict(effort='none'), max_output_tokens=4096,
                                   input='Make a short context summary')
                else:
                    request.update(thinking=dict(type='disabled'), max_tokens=4096,
                                   messages=[dict(role='user', content='Make a short context summary')])
                frozen = json.dumps(request, sort_keys=True)
                result = effective_request(api, request, 65536, 'native-aux-v2')
                self.assertEqual(result.get('thinking', result.get('reasoning')),
                                 request.get('thinking', request.get('reasoning')))
                self.assertEqual(result.get('max_tokens', result.get('max_output_tokens')), 4096)
                self.assertEqual(json.dumps(request, sort_keys=True), frozen)
                self.assertNotIn('reasoning_effort', result)

    def test_main_task_uses_high_effort_and_larger_common_budget(self):
        for api in ('chat', 'messages', 'responses'):
            with self.subTest(api=api):
                request = dict(model='deepseek-flash', messages=[dict(role='user', content='original issue')],
                               tools=[dict(type='function', function=dict(name='native_tool'))])
                result = effective_request(api, request, 65536, 'native-aux-v2')
                self.assertEqual(result['messages'], request['messages'])
                self.assertEqual(result['tools'], request['tools'])
                self.assertEqual(result.get('max_tokens', result.get('max_output_tokens')), 65536)
                effort = (result.get('reasoning_effort') or result.get('output_config', {}).get('effort')
                          or result.get('reasoning', {}).get('effort'))
                self.assertEqual(effort, 'high')

    def test_historical_transform_is_available_without_rewriting_legacy_protocol(self):
        source = (HERE/'protocol-six.json').read_bytes()
        original = selected_protocol('openclaw57_patched', 'pytest-dev__pytest-7236')
        changed = selected_protocol('openclaw57_patched', 'pytest-dev__pytest-7236', validated=True)
        self.assertEqual(original['execution']['maximum_provider_attempts_per_run'], 64)
        self.assertIsNone(changed['execution']['maximum_provider_attempts_per_run'])
        self.assertEqual(changed['provider']['requested_max_output_tokens'], 65536)
        self.assertEqual(changed['execution']['task_timeout_seconds'], 1800)
        self.assertEqual((HERE/'protocol-six.json').read_bytes(), source)

    def test_exact_machine_admission_rejects_model_or_runner_mismatch(self):
        env = dict(BENCH_EXPECTED_CPU_MODEL='Pinned CPU', BENCH_EXPECTED_RUNNER_NAME='benchmark-01',
                   RUNNER_NAME='benchmark-01')
        self.assertTrue(fixed_runner_admission(env, 'model name : Pinned CPU\n')['passed'])
        for bad in ({}, {**env, 'RUNNER_NAME':'other'}, {**env, 'BENCH_EXPECTED_CPU_MODEL':'Other CPU'}):
            with self.assertRaises(ValueError):
                fixed_runner_admission(bad, 'model name : Pinned CPU\n')

    def test_messages_and_responses_truncations_are_detected_even_with_full_usage(self):
        for api, event in (
            ('messages', dict(type='message_delta', delta=dict(stop_reason='max_tokens'))),
            ('responses', dict(type='response.incomplete', response=dict(incomplete_details=dict(reason='max_output_tokens'))))):
            row = dict(request_index=0, forwarded=True, terminal=True, final_usage_observed=True)
            observer = Observation(api, row)
            observer.event(event, 1)
            check = check_response_integrity([row])
            self.assertFalse(check['clean'])
            self.assertEqual(check['issues'][0]['kind'], 'output_truncated')
        broken = dict(request_index=0, forwarded=True, terminal=False, final_usage_observed=False)
        self.assertEqual({x['kind'] for x in check_response_integrity([broken])['issues']},
                         {'missing_stream_terminal','missing_final_usage'})

    def test_real_relay_receives_protocol_budget_and_allows_request_65(self):
        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Type':'application/json'}
        class Opener:
            def __init__(self): self.requests=[]
            def open(self, request, timeout):
                self.requests.append(json.loads(request.data))
                return Response(json.dumps(dict(choices=[dict(finish_reason='stop')], usage=dict(
                    prompt_tokens=2, prompt_cache_hit_tokens=0, completion_tokens=1))).encode())
        protocol = selected_protocol('openclaw57_patched','pytest-dev__pytest-7236',validated=True)
        with tempfile.TemporaryDirectory() as temp:
            relay = Relay.from_protocol('fixture-not-a-key','127.0.0.1',Path(temp),'fixture',protocol)
            relay.opener = Opener()
            try:
                for _ in range(65):
                    body = dict(model='deepseek-flash',stream=False,messages=[dict(role='user',content='fixture')])
                    req = urllib.request.Request(relay.base+'/v1/chat/completions',data=json.dumps(body).encode(),
                        headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(req,timeout=3) as response:
                        self.assertEqual(response.status,200)
                self.assertEqual(len(relay.opener.requests),65)
                self.assertTrue(all(r['max_tokens']==65536 for r in relay.opener.requests))
                deadline=time.monotonic()+3
                while any(not r['settled'] for r in relay.records) and time.monotonic()<deadline:
                    time.sleep(0.01)
                self.assertTrue(check_response_integrity(relay.records)['clean'])
            finally:
                relay.close()

    def test_aios_native_output_and_turn_limits_are_configured_without_product_edits(self):
        saved = {}
        with patch.object(agent_entry,'write',lambda p,t:saved.__setitem__(str(p),t)), \
             patch.object(Path,'read_text',lambda p:saved[str(p)]), \
             patch.dict('os.environ',dict(BENCH_RUN_ID='fixture',BENCH_AIOS_RUNTIME='agentloop',
                 BENCH_TASK_TIMEOUT_SECONDS='1800',BENCH_MAX_OUTPUT_TOKENS='65536',BENCH_NATIVE_ITERATION_LIMIT='4096')), \
             patch('os.execvpe') as execute:
            agent_entry.launch('openclaw57_patched','http://fixture','original issue')
        config=json.loads(saved['/home/bench/.openclaw/openclaw.json'])
        self.assertEqual(config['models']['providers']['deepseek']['models'][0]['maxTokens'],65536)
        self.assertEqual(config['agents']['defaults']['thinkingDefault'],'high')
        self.assertEqual(execute.call_args.args[2]['AGENTLOOP_LOOP_MAX_TURNS'],'4096')


if __name__ == '__main__':
    unittest.main()
