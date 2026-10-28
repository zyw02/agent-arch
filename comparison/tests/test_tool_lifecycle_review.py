import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_tool_lifecycle_review import make_packet,expected_answers
from summarize_tool_lifecycle import summarize


class ToolNativePacketTests(unittest.TestCase):
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
