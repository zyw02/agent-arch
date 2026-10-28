import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest
import tempfile
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_tool_lifecycle_review import make_packet,expected_answers
from summarize_tool_lifecycle import summarize
from audit_tool_cancellation import audit
from audit_tool_native_review import audit as audit_review
from export_native_review import export


class ToolNativePacketTests(unittest.TestCase):
    def test_retained_review_verifies_exact_inputs_original_scores_usage_and_separate_support_audit(self):
        comparison=Path(__file__).resolve().parents[1];root=comparison/'evidence/tool-lifecycle-20261028';review=root/'native-review'
        provenance=json.loads((review/'provenance.json').read_bytes())
        for name,digest in provenance['retained_files_sha256'].items():self.assertEqual(hashlib.sha256((review/name).read_bytes()).hexdigest(),digest,name)
        with tempfile.TemporaryDirectory() as directory:
            tmp=Path(directory)
            summary=export(review/'original-artifact.zip',provenance['artifact_zip_sha256'],root/'formal-original-report.json.gz',review/'protocol.json','HD',tmp/'derived')
            self.assertEqual(summary,json.loads((review/'summary.json').read_bytes()));self.assertEqual(summary['actual_paid_requests'],8);self.assertEqual(summary['provider_complete'],8)
            self.assertEqual(summary['known_input_tokens']+summary['known_output_tokens'],summary['known_total_tokens'])
            with zipfile.ZipFile(review/'original-artifact.zip') as zipped:
                for entry in zipped.infolist():self.assertTrue((tmp/entry.filename).resolve().is_relative_to(tmp))
                zipped.extractall(tmp)
            dataset=tmp/'native-hd-review-dataset';answers=tmp/'native-hd-review-answers';informed=audit_review(dataset,answers,review/'protocol.json')
            self.assertEqual(informed,json.loads((review/'informed-audit.json').read_bytes()))
            self.assertEqual(informed['original_counts'],summary['original_counts']);self.assertEqual(informed['original_strict_citation_matches'],0)
            self.assertEqual(informed['support_counts']['invalid_answer_preserved'],3)
            altered=json.loads((dataset/'score.json').read_bytes());altered['totals']['correct']+=1;(dataset/'score.json').write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError,'Original review scores changed'):audit_review(dataset,answers,review/'protocol.json')

    def test_formal_records_recompute_and_secondary_audit_preserves_original_outcomes(self):
        comparison=Path(__file__).resolve().parents[1];root=comparison/'evidence/tool-lifecycle-20261028'
        raw=gzip.decompress((root/'formal-original-report.json.gz').read_bytes());report=json.loads(raw)
        summary=summarize(report,comparison/'tool-lifecycle-protocol.json');published=json.loads((root/'formal-summary.json').read_bytes());published.pop('original_report_sha256')
        self.assertEqual(summary,published);self.assertTrue(summary['complete_comparison_blocks']);self.assertTrue(summary['healthy_controls_passed']);self.assertEqual(len(summary['rows']),24)
        self.assertEqual(audit(report),json.loads((root/'formal-cancellation-audit.json').read_bytes()))
        provenance=json.loads((root/'formal-provenance.json').read_bytes());self.assertEqual(hashlib.sha256(raw).hexdigest(),provenance['original_report_sha256'])
        for name,digest in provenance['retained_files_sha256'].items():self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest,name)
        admission=json.loads((comparison/'tool-lifecycle-formal-admission.json').read_bytes())
        self.assertEqual(provenance['analysis_scripts_sha256'],admission['frozen_analysis_scripts_sha256'])
        for name,digest in admission['frozen_analysis_scripts_sha256'].items():self.assertEqual(hashlib.sha256((comparison/name).read_bytes()).hexdigest(),digest,name)

    def test_secondary_audit_detects_late_dispatch_even_if_it_stops_before_snapshot(self):
        comparison=Path(__file__).resolve().parents[1]
        report=json.loads(gzip.decompress((comparison/'evidence/tool-lifecycle-20261028/pilot-original-report.json.gz').read_bytes()))
        result=audit(report);self.assertTrue(result['complete_cancel_arm_coverage'])
        self.assertTrue(next(r for r in result['rows'] if r['product']=='DSH')['accepted_original_has_no_extra_tool_dispatch'])
        arm=next(a for a in report['results'] if a['product']=='DSH' and a['condition']=='mcp_batch_cancel')
        # A new attempt may finish before the 10-second snapshot. Its absence
        # from live calls at that cut is insufficient to establish no dispatch.
        arm['fixture_events'].append(dict(kind='call_received',index=3,mcp_call_id=999,monotonic_ns=arm['cancel']['received_ns']+1))
        row=next(r for r in audit(report)['rows'] if r['product']=='DSH')
        self.assertTrue(row['original_handling_acceptance']);self.assertFalse(row['accepted_original_has_no_extra_tool_dispatch'])
        self.assertEqual(row['new_mcp_calls_after_cancel_before_health'][0]['index'],3)

    def test_complete_pilot_recomputes_original_judgments_hashes_and_admission(self):
        comparison=Path(__file__).resolve().parents[1];root=comparison/'evidence/tool-lifecycle-20261028'
        admission=json.loads((comparison/'tool-lifecycle-formal-admission.json').read_bytes());raw=gzip.decompress((comparison/admission['pilot_report_gzip']).read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(),admission['pilot_report_sha256'])
        summary=summarize(json.loads(raw),comparison/'tool-lifecycle-protocol.json');published=json.loads((root/'pilot-summary.json').read_bytes());published.pop('original_report_sha256')
        self.assertEqual(summary,published);self.assertTrue(summary['complete_comparison_blocks']);self.assertTrue(summary['healthy_controls_passed'])
        fixture=json.loads((root/'pilot-fixture-capacity.json').read_bytes());self.assertTrue(fixture['valid']);self.assertEqual(fixture['protocol_sha256'],admission['fixture_protocol_sha256'])
        self.assertEqual(hashlib.sha256((root/'pilot-fixture-protocol.json').read_bytes()).hexdigest(),fixture['protocol_sha256'])
        provenance=json.loads((root/'pilot-provenance.json').read_bytes())
        for name,digest in provenance['retained_files_sha256'].items():self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest,name)

    def test_native_packet_strips_condition_paths_and_excludes_controller_truth(self):
        arm=dict(task_marker='TOOL_INPUT_x',task=dict(session_id='native-session',native_result=dict(hidden='terminal-oracle')),
            condition='mcp_batch_failure',block=2,fixture_events=[dict(hidden='fixture-oracle')],provider_requests=[dict(hidden='provider-oracle')],
            native_history=dict(events=dict(records=[dict(text='TOOL_VALUE_x',cwd='/tmp/tool-lifecycle-abc/2-DSH-mcp_batch_failure/workspace')]),observer_cli=dict(cpu_seconds=999)),
            sanitized_native_log=['/tmp/tool-lifecycle-def/1-OpenClaw-mcp_four_batch/config'],resources=dict(hidden='resource-oracle'))
        original=copy.deepcopy(arm);packet=make_packet(arm,'random-case');text=str(packet)
        self.assertEqual(arm,original)
        for hidden in ('mcp_batch_failure','mcp_four_batch','999','oracle','observer_cli','cpu_seconds','provider_requests','fixture_events'):self.assertNotIn(hidden,text)
        self.assertIn('<owned-root>/workspace',text);self.assertIn('TOOL_VALUE_x',text);self.assertIn('native-session',text)

    def test_delivery_truth_requires_actual_assistant_final_and_independent_read(self):
        arm=dict(product='OpenClaw',input_values=['TOOL_VALUE_a','TOOL_VALUE_b','TOOL_VALUE_c','TOOL_VALUE_d'],
            fixture_events=[dict(kind='file_read',index=0),dict(kind='file_read',index=1),dict(kind='failure_injected',index=2)],
            task=dict(native_result=dict(choices=[dict(message=dict(role='assistant',content='TOOL_VALUE_a TOOL_VALUE_c'))])))
        answers=expected_answers(arm,dict(repeat_owner='native'))
        self.assertEqual(answers,dict(failed_read_index='2',repeat_owner='native',delivered_value_count='1'))
        arm['task']['native_result']['choices'][0]['message']['role']='user'
        self.assertEqual(expected_answers(arm,dict(repeat_owner='no_repeat'))['delivered_value_count'],'0')

if __name__=='__main__':unittest.main()
