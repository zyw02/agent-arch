import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from export_observability_reuse import CHECKS,extract,normalized_row


class ObservabilityReuseTests(unittest.TestCase):
    def fixture(self):
        assertions=[dict(name=name,verdict='fail' if key=='all_offered_ids_exported' else 'pass') for key,name in CHECKS.items()]
        observation=dict(scenario_id='OBS-02-S01',unit=1,state='fail',assertions=assertions,
            metadata=dict(offered_unique_events=3,independent_offered_workload_receipt=dict(collector_offered_count=3),
                missing_event_indices=[0,1,2],missing_event_count=3,native_local_missing_event_indices=[],native_local_event_indices=[0,1,2],
                successful_deliveries_by_index={},duplicate_successful_deliveries=0,mode='brief',sdk_default_queue_capacity=2048,
                sdk_default_batch_capacity=512,native_overflow_log_signal=False))
        raw=json.dumps(dict(observations=[observation])).encode()
        record=dict(scenario_id='OBS-02-S01',unit=1,state='fail',assertions=assertions,run_id='source',controller_commit='original',target_version='2026.10.7',native_summary_sha256=hashlib.sha256(raw).hexdigest())
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z:z.writestr('unit-1/summary.json',raw)
        archive=buffer.getvalue();asset=dict(source_zip_sha256=hashlib.sha256(archive).hexdigest(),download_url='https://synthetic.invalid')
        return observation,record,asset,archive

    def test_failed_original_stays_failed_and_local_remote_scopes_differ(self):
        observation,record,asset,archive=self.fixture()
        row=extract(archive,[record],asset)[0]
        self.assertEqual(row['historical_state'],'fail')
        self.assertEqual(row['remote_missing_fraction'],1)
        self.assertEqual(row['local_missing_fraction'],0)
        self.assertTrue(row['publication_after_restoration'])

    def test_truncated_or_inconsistent_event_partitions_cannot_look_complete(self):
        observation,record,asset,archive=self.fixture()
        observation['metadata']['missing_event_indices'].pop()
        with self.assertRaisesRegex(ValueError,'partition'):normalized_row(observation,record,asset)
        observation,record,asset,archive=self.fixture();observation['metadata']['native_local_event_indices']=[0,1]
        with self.assertRaisesRegex(ValueError,'partition'):normalized_row(observation,record,asset)

    def test_only_exact_archive_summary_identity_and_judgments_accepted(self):
        observation,record,asset,archive=self.fixture()
        with self.assertRaisesRegex(ValueError,'ZIP digest'):extract(archive+b'bad',[record],asset)
        wrong=copy.deepcopy(record);wrong['native_summary_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'summary missing'):extract(archive,[wrong],asset)
        observation['unit']=2
        with self.assertRaisesRegex(ValueError,'identity'):normalized_row(observation,record,asset)

if __name__=='__main__':unittest.main()
