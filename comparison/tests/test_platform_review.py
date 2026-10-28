import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from review_platform_native import make_packet,quote_exists
from summarize_platform_fault import summarize
from export_native_review import export


class NativeOnlyPacketTests(unittest.TestCase):
    def test_pilot_original_hashes_and_frozen_admission_recompute_without_native_execution(self):
        comparison=Path(__file__).resolve().parents[1];root=comparison/'evidence/platform-fault-20261028'
        admission=json.loads((comparison/'platform-fault-formal-admission.json').read_bytes());raw=gzip.decompress((comparison/admission['pilot_report_gzip']).read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(),admission['pilot_report_sha256'])
        self.assertEqual(hashlib.sha256((comparison/'platform-fault-protocol.json').read_bytes()).hexdigest(),admission['protocol_sha256'])
        report=json.loads(raw);summary=summarize(report);published=json.loads((root/'pilot-summary.json').read_bytes());published.pop('original_report_sha256')
        self.assertEqual(summary,published);self.assertTrue(summary['complete_comparison_blocks'])
        provenance=json.loads((root/'pilot-provenance.json').read_bytes())
        for name,digest in provenance['retained_files_sha256'].items():self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest,name)

    def test_packet_excludes_external_truth_and_does_not_mutate_original_native_evidence(self):
        arm=dict(condition='owner_exit',block=1,owner=dict(pid=999),boundary_ledger=[dict(hidden='oracle')],
            tasks=dict(primary=dict(session_id='native-id',marker='PLATFORM_INPUT_'+'a'*32)),
            followups=dict(primary=dict(marker='PLATFORM_INPUT_'+'b'*32)),
            cycles=[dict(sanitized_native_log=['cwd /tmp/platform-fault-xyz/1-DSH-owner_exit/workspace'])],
            passive_histories=dict(primary=dict(native=dict(events=dict(records=[]),observer_cli=dict(cpu_seconds=12)),facts=dict(assistant_ack=False))))
        original=copy.deepcopy(arm);packet=make_packet(arm,'random-case')
        self.assertEqual(arm,original)
        text=str(packet)
        for hidden in ('owner_exit','oracle','observer_cli','cpu_seconds','assistant_ack','999'):self.assertNotIn(hidden,text)
        self.assertIn('<owned-root>/workspace',text)
        self.assertIn('native-id',text)

    def test_citation_must_name_an_existing_native_field_with_exact_substring(self):
        packet=dict(native_carrier_logs=[['started']])
        self.assertTrue(quote_exists(packet,'$.native_carrier_logs[0][0]','started'))
        self.assertFalse(quote_exists(packet,'$.native_carrier_logs[0][0]','SIGKILL'))
        self.assertFalse(quote_exists(packet,'$.owner.pid','started'))
        self.assertFalse(quote_exists(packet,None,None))

    def test_retained_reviews_reproduce_scores_native_packets_and_complete_usage(self):
        comparison=Path(__file__).resolve().parents[1]
        for study,kind in [('PA','fault'),('PC','resource')]:
            root=comparison/('evidence/platform-'+kind+'-20261028');review=root/'native-review'
            provenance=json.loads((review/'provenance.json').read_bytes())
            for name,expected in provenance['retained_files_sha256'].items():
                self.assertEqual(hashlib.sha256((review/name).read_bytes()).hexdigest(),expected,name)
            with tempfile.TemporaryDirectory() as tmp:
                summary=export(review/'original-artifact.zip',provenance['artifact_zip_sha256'],root/'formal-original-report.json.gz',review/'protocol.json',study,Path(tmp)/'derived')
                self.assertEqual(summary,json.loads((review/'summary.json').read_bytes()))
                self.assertEqual(summary['actual_paid_requests'],summary['provider_complete'])
                self.assertEqual(summary['known_input_tokens']+summary['known_output_tokens'],summary['known_total_tokens'])

    def test_export_rejects_archive_protocol_and_native_projection_changes(self):
        comparison=Path(__file__).resolve().parents[1];root=comparison/'evidence/platform-fault-20261028';review=root/'native-review'
        provenance=json.loads((review/'provenance.json').read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            with self.assertRaisesRegex(ValueError,'digest mismatch'):
                export(review/'original-artifact.zip','0'*64,root/'formal-original-report.json.gz',review/'protocol.json','PA',tmp/'bad-archive')
            protocol=json.loads((review/'protocol.json').read_bytes());protocol['questions']['ownership']['question']='Altered question'
            (tmp/'protocol.json').write_text(json.dumps(protocol))
            with self.assertRaisesRegex(ValueError,'protocol changed'):
                export(review/'original-artifact.zip',provenance['artifact_zip_sha256'],root/'formal-original-report.json.gz',tmp/'protocol.json','PA',tmp/'bad-protocol')
            report=json.loads(gzip.decompress((root/'formal-original-report.json.gz').read_bytes()))
            report['results'][0]['cycles'][0]['sanitized_native_log'].append('Altered native record')
            (tmp/'source.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'exact declared native-only projection'):
                export(review/'original-artifact.zip',provenance['artifact_zip_sha256'],tmp/'source.json',review/'protocol.json','PA',tmp/'bad-source')

if __name__=='__main__':unittest.main()
