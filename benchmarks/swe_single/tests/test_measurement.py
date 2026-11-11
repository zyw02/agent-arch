import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from accounting import merge_counters, normalize_usage, summarize_requests, union_seconds
from grading import compare_source, grading_workspace, parse_junit, score
from relay import Observation, Relay, effective_request
from resources import disk_tree
from reconcile import project


class AccountingTests(unittest.TestCase):
    def test_three_protocols_have_identical_billable_partitions(self):
        examples = {
            'messages': dict(input_tokens=80, cache_read_input_tokens=20,
                             cache_creation_input_tokens=0, output_tokens=10),
            'chat': dict(prompt_tokens=100, prompt_cache_hit_tokens=20,
                         completion_tokens=10, completion_tokens_details=dict(reasoning_tokens=7)),
            'responses': dict(input_tokens=100, input_tokens_details=dict(cached_tokens=20),
                              output_tokens=10, output_tokens_details=dict(reasoning_tokens=7)),
        }
        for api, usage in examples.items():
            actual = normalize_usage(api, usage)
            self.assertTrue(actual['core_complete'])
            self.assertEqual([actual[k] for k in ('input_total', 'input_noncache_billed', 'cache_read', 'output_total')],
                             [100, 80, 20, 10])
        self.assertIsNone(normalize_usage('messages', examples['messages'])['reasoning_subset'])

    def test_unknown_is_not_zero(self):
        self.assertFalse(normalize_usage('responses', dict(input_tokens=10, output_tokens=2))['core_complete'])
        measured_zero = normalize_usage('responses', dict(input_tokens=0, output_tokens=0,
                                                       input_tokens_details=dict(cached_tokens=0)))
        self.assertTrue(measured_zero['core_complete'])
        self.assertEqual(measured_zero['input_total'], 0)

    def test_stream_updates_are_cumulative_not_additive(self):
        merged = merge_counters(dict(input_tokens=80, output_tokens=0), dict(output_tokens=12))
        self.assertEqual(merged, dict(input_tokens=80, output_tokens=12))
        self.assertEqual(merge_counters(dict(details=dict(cached=20, other=3)), dict(details=dict(cached=30))),
                         dict(details=dict(cached=30, other=3)))

    def test_retry_and_missing_terminal_do_not_look_complete(self):
        good = dict(forwarded=True, settled=True, terminal=True, final_usage_observed=True,
                    started_ns=0, ended_ns=10**9,
                    normalized_usage=normalize_usage('chat', dict(prompt_tokens=100, prompt_cache_hit_tokens=20,
                                                                completion_tokens=10)))
        unknown = dict(forwarded=True, settled=True, terminal=False, http_status=503,
                       started_ns=10**9, ended_ns=2*10**9)
        result = summarize_requests([good, unknown])
        self.assertEqual(result['provider_attempts'], 2)
        self.assertFalse(result['usage_complete'])
        self.assertEqual(result['known_input_total'], 100)
        self.assertIsNone(result['input_total'])
        self.assertEqual(result['usage_unknown_attempts'], 1)
        self.assertFalse(summarize_requests([{**good, 'terminal': False}])['usage_complete'])

    def test_parallel_provider_time_is_union(self):
        self.assertEqual(union_seconds([(0, 2*10**9), (10**9, 3*10**9), (4*10**9, 5*10**9)]), 4)

    def test_declared_controls_do_not_replace_native_tools_or_prompt(self):
        request = dict(model='deepseek-flash', messages=[dict(role='user', content='original')],
                       tools=[dict(type='function', function=dict(name='native'))], stream=True)
        changed = effective_request('chat', request, 16384)
        self.assertEqual(changed['messages'], request['messages'])
        self.assertEqual(changed['tools'], request['tools'])
        self.assertNotIn('thinking', request)
        with self.assertRaises(ValueError):
            effective_request('responses', dict(model='other'), 16384)
        with self.assertRaises(ValueError):
            effective_request('responses', dict(model='deepseek-flash', tools=[dict(type='web_search')]), 16384)


class NativeProjectionTests(unittest.TestCase):
    def test_hermes_main_and_auxiliary_use_different_input_boundaries(self):
        # Retained block-1 Hermes counters: provider input=186372, cache=175744.
        native = dict(native_usage=dict(input_tokens=185933, cache_read_tokens=175488,
            output_tokens=5888, api_calls=11,
            auxiliary=dict(input_tokens=183, cache_read_tokens=256, cache_write_tokens=0,
                           output_tokens=157, api_calls=1)))
        actual = project('hermes', native)
        self.assertEqual(actual['input_total'], 186372)
        self.assertEqual(actual['cache_read'], 175744)
        self.assertEqual(actual['output_total'], 6045)
        self.assertEqual(actual['native_api_calls'], 12)


class StorageAndScoringTests(unittest.TestCase):
    def test_storage_separates_sparse_allocation_hardlinks_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'logs').mkdir()
            (root / 'logs/a.jsonl').write_bytes(b'abcd')
            (root / 'state.db-wal').write_bytes(b'123')
            (root / 'alias').symlink_to('/etc/passwd')
            with (root / 'sparse').open('wb') as f:
                f.truncate(1024**2)
            measured = disk_tree(root)
            self.assertEqual(measured['logical_bytes'], 1024**2 + 7)
            self.assertEqual(measured['files'], 3)
            self.assertEqual(measured['symlinks'], 1)
            self.assertLess(measured['allocated_bytes'], measured['logical_bytes'])
            self.assertEqual(measured['categories']['database_and_journal']['logical_bytes'], 3)

    def test_hidden_grading_uses_clean_tests_and_rejects_candidate_test_edits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base, candidate, clean = root/'base', root/'candidate', root/'grading'
            for directory in (base, candidate):
                (directory/'src').mkdir(parents=True)
                (directory/'src/code.py').write_text('answer = 0\n')
                (directory/'test.py').write_text('assert answer == 1\n')
            (candidate/'src/code.py').write_text('answer = 1\n')
            (candidate/'test.py').write_text('pass\n')
            result = compare_source(base, candidate, root/'patch.diff')
            self.assertFalse(result['policy_passed'])
            self.assertEqual(result['forbidden_paths'], ['test.py'])
            grading_workspace(base, candidate, clean)
            self.assertEqual((clean/'src/code.py').read_text(), 'answer = 1\n')
            self.assertEqual((clean/'test.py').read_text(), 'assert answer == 1\n')

    def test_junit_full_identifiers_and_missing_cases(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'junit.xml'
            path.write_text('''<testsuites><testsuite>
<testcase classname="testing.test_skipping.TestXFail" file="testing/test_skipping.py" name="test_dynamic"/>
<testcase classname="testing.test_skipping" file="testing/test_skipping.py" name="test_existing[a b]"/>
</testsuite></testsuites>''')
            statuses = parse_junit(path)
            task = dict(FAIL_TO_PASS=['testing/test_skipping.py::TestXFail::test_dynamic'],
                        PASS_TO_PASS=['testing/test_skipping.py::test_existing[a'])
            self.assertTrue(score(task, statuses)['official_subset_resolved'])
            task['FAIL_TO_PASS'].append('missing')
            self.assertFalse(score(task, statuses)['official_subset_resolved'])


class RelayIntegrationTests(unittest.TestCase):
    def test_initial_usage_and_stop_without_final_usage_are_incomplete(self):
        row = dict(forwarded=True, settled=True, stream=True, started_ns=0, ended_ns=10**9)
        observer = Observation('messages', row)
        observer.event(dict(type='message_start', message=dict(usage=dict(
            input_tokens=80, cache_read_input_tokens=20, cache_creation_input_tokens=0, output_tokens=0))), 1)
        observer.event(dict(type='message_stop'), 2)
        observer.finish()
        self.assertTrue(row['terminal'])
        self.assertFalse(summarize_requests([row])['usage_complete'])
        observer.event(dict(type='message_delta', usage=dict(output_tokens=10)), 3)
        observer.finish()
        self.assertTrue(summarize_requests([row])['usage_complete'])

    def test_nonstream_responses_usage_is_top_level(self):
        row = dict(forwarded=True, settled=True, terminal=True, stream=False,
                   started_ns=0, ended_ns=10**9)
        observer = Observation('responses', row)
        observer.event(dict(type='response', id='fixture', usage=dict(
            input_tokens=100, input_tokens_details=dict(cached_tokens=20), output_tokens=10)), 1)
        observer.finish()
        self.assertTrue(summarize_requests([row])['usage_complete'])

    def test_native_messages_beta_query_reaches_fixed_upstream_with_usage(self):
        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Type': 'application/json'}
        class Opener:
            def open(self, req, timeout):
                self.request = req
                return Response(json.dumps(dict(id='fixture', model='deepseek-flash',
                    usage=dict(input_tokens=80, cache_read_input_tokens=20,
                               cache_creation_input_tokens=0, output_tokens=10))).encode())
        with tempfile.TemporaryDirectory() as temp:
            relay = Relay('test-secret-not-in-artifacts', '127.0.0.1', temp, 'test')
            relay.opener = Opener()
            body = json.dumps(dict(model='deepseek-flash', messages=[dict(role='user', content='original')])).encode()
            try:
                request = urllib.request.Request(relay.base + '/anthropic/v1/messages?beta=true', data=body)
                self.assertEqual(json.loads(urllib.request.urlopen(request).read())['id'], 'fixture')
                self.assertEqual(relay.opener.request.full_url,
                                 'https://api.deepseek.com/anthropic/v1/messages?beta=true')
                bad = urllib.request.Request(relay.base + '/anthropic/v1/messages?other=true', data=body)
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(bad)
            finally:
                relay.close()
            ledger = json.loads((Path(temp) / 'ledger.json').read_text())
            self.assertTrue(ledger['summary']['usage_complete'])
            self.assertEqual(ledger['summary']['provider_attempts'], 1)
            self.assertEqual(ledger['summary']['blocked_requests'], 1)
            self.assertEqual(ledger['summary']['input_total'], 100)

    def test_real_http_frontend_retains_usage_and_never_writes_credential(self):
        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Type': 'text/event-stream', 'x-request-id': 'fixture-physical-attempt'}
        class Opener:
            def open(self, req, timeout):
                self.request = req
                return Response(b'data: {"id":"fixture","model":"deepseek-flash","choices":[{"delta":{"content":"ok"}}]}\n\n'
                                b'data: {"choices":[],"usage":{"prompt_tokens":100,"prompt_cache_hit_tokens":20,"completion_tokens":10}}\n\n'
                                b'data: [DONE]\n\n')
        with tempfile.TemporaryDirectory() as temp:
            relay = Relay('test-secret-not-in-artifacts', '127.0.0.1', temp, 'test')
            relay.opener = Opener()
            request = urllib.request.Request(relay.base + '/v1/chat/completions',
                data=json.dumps(dict(model='deepseek-flash', messages=[dict(role='user', content='original')], stream=True)).encode(),
                headers={'Content-Type': 'application/json'})
            try:
                self.assertIn(b'[DONE]', urllib.request.urlopen(request).read())
            finally:
                relay.close()
            ledger = json.loads((Path(temp)/'ledger.json').read_text())
            self.assertTrue(ledger['summary']['usage_complete'])
            self.assertEqual(ledger['summary']['input_total'], 100)
            for path in Path(temp).rglob('*'):
                if path.is_file():
                    self.assertNotIn(b'test-secret-not-in-artifacts', path.read_bytes())


if __name__ == '__main__':
    unittest.main()
