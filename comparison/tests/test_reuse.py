import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inspect_reuse_archives import inspect
from native_read_probe import choose_response,final_receipt_matches
from export_reuse_metrics import row_from


class ReuseIntegrityTests(unittest.TestCase):
    def fixture(self):
        raw=json.dumps({'scenarios':[{'id':'CASE-S01','duration_ms':123}]}).encode()
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            z.writestr('unit-1/summary.json',raw)
            z.writestr('quarantined/summary.json',b'{"bad":42}')
        archive=buf.getvalue()
        accepted=dict(source_zip_sha256=hashlib.sha256(archive).hexdigest(),
            summary_digests={hashlib.sha256(raw).hexdigest():[dict(scenario='CASE-S01',unit=1)]})
        return archive,accepted

    def test_only_digest_bound_accepted_summary_is_inspected(self):
        archive,accepted=self.fixture();rows=inspect(archive,accepted)
        self.assertEqual([r['path'] for r in rows],['unit-1/summary.json'])
        self.assertIn(('.scenarios[0].duration_ms',123),rows[0]['numeric_fields'])

    def test_changed_archive_is_rejected(self):
        archive,accepted=self.fixture()
        with self.assertRaisesRegex(ValueError,'digest mismatch'):inspect(archive+b'changed',accepted)

    def test_missing_accepted_summary_is_not_silently_dropped(self):
        archive,accepted=self.fixture();accepted['summary_digests']['0'*64]=[]
        with self.assertRaisesRegex(ValueError,'not found'):inspect(archive,accepted)


class NativeReadCalibrationTests(unittest.TestCase):
    def test_prompt_receipt_cannot_fake_actual_tool_return(self):
        body={'messages':[{'role':'user','content':'SECRET_RECEIPT'}],
              'tools':[{'type':'function','function':{'name':'read','parameters':{'properties':{'path':{'type':'string'}}}}}]}
        result=choose_response(body,Path('/synthetic/input'),'SECRET_RECEIPT')
        self.assertEqual(result.get('tool'),'read')
        self.assertNotIn('text',result)

    def test_missing_receipt_is_not_accepted_after_tool_failure(self):
        body={'messages':[{'role':'tool','content':'Error: read failed'}]}
        self.assertNotEqual(choose_response(body,Path('/synthetic/input'),'SECRET_RECEIPT').get('text'),'VERIFIED:SECRET_RECEIPT')


class FinalReceiptTests(unittest.TestCase):
    def test_terminal_receipt_allows_marker_whitespace(self):
        output=json.dumps(dict(type='final',text='VERIFIED: SECRET_RECEIPT'))
        self.assertTrue(final_receipt_matches('DSH',output,'SECRET_RECEIPT'))
        self.assertTrue(final_receipt_matches('OpenClaw',json.dumps(dict(payloads=[dict(text='VERIFIED:SECRET_RECEIPT')])), 'SECRET_RECEIPT'))

    def test_tool_output_or_wrong_final_cannot_fake_completion(self):
        output=json.dumps(dict(type='tool_result',result='VERIFIED:SECRET_RECEIPT'))+'\n'+json.dumps(dict(type='final',text='not completed'))
        self.assertFalse(final_receipt_matches('DSH',output,'SECRET_RECEIPT'))
        self.assertFalse(final_receipt_matches('OpenClaw',json.dumps(dict(meta=dict(finalAssistantVisibleText='VERIFIED:SECRET_RECEIPT'),payloads=[])), 'SECRET_RECEIPT'))


class ReuseMetricTests(unittest.TestCase):
    def fixture(self):
        usage=dict(prompt_tokens=10,completion_tokens=2,prompt_cache_hit_tokens=6,prompt_cache_miss_tokens=4)
        return dict(scenario_id='COST-03-S01',unit=1,state='pass',run_id='owned',native_summary_sha256='owned',evidence=['owned'],
            reuse_accounting=dict(usage_synthetic=False,groups=dict(baseline=dict(known_usage=usage,missing_counters={},requests=1)),
            normalization=dict(baseline=dict(accepted_deliveries=1,known_tokens_per_accepted_delivery=usage))))

    def test_cache_is_not_added_to_inclusive_input_twice(self):
        row=row_from(self.fixture(),'baseline')
        self.assertEqual(row['known_total_tokens'],12)
        self.assertIsNone(row['actual_charge_usd'])

    def test_inconsistent_usage_or_synthetic_counters_are_rejected(self):
        r=self.fixture();r['reuse_accounting']['groups']['baseline']['known_usage']['prompt_cache_hit_tokens']=7
        with self.assertRaisesRegex(ValueError,'partition'):row_from(r,'baseline')
        r=self.fixture();r['reuse_accounting']['usage_synthetic']=True
        with self.assertRaisesRegex(ValueError,'Real provider'):row_from(r,'baseline')

    def test_zero_accepted_keeps_cost_and_has_no_per_success_estimate(self):
        r=self.fixture();r['reuse_accounting']['normalization']['baseline']['accepted_deliveries']=0
        row=row_from(r,'baseline');self.assertEqual(row['known_total_tokens'],12)
        self.assertIsNone(row['known_tokens_per_accepted_delivery'])

if __name__=='__main__':unittest.main()
