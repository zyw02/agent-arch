from pathlib import Path
import gzip
import hashlib
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from platform_resource_probe import integrate_memory
from summarize_platform_resource import summarize


class ResidentIntegralTests(unittest.TestCase):
    def test_retained_pc_pilot_and_admission_reproduce_without_product_execution(self):
        comparison=Path(__file__).resolve().parents[1];root=comparison/'evidence/platform-resource-20261028'
        admission=json.loads((comparison/'platform-resource-formal-admission.json').read_bytes());raw=gzip.decompress((comparison/admission['pilot_report_gzip']).read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(),admission['pilot_report_sha256'])
        self.assertEqual(hashlib.sha256((comparison/'platform-resource-protocol.json').read_bytes()).hexdigest(),admission['protocol_sha256'])
        published=json.loads((root/'pilot-summary.json').read_bytes());published.pop('original_report_sha256');self.assertEqual(summarize(json.loads(raw)),published)
        for name,digest in json.loads((root/'pilot-provenance.json').read_bytes())['retained_files_sha256'].items():self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest,name)

    def test_piecewise_resident_integral_and_missing_observation(self):
        samples=[dict(monotonic_ns=0,rss=100),dict(monotonic_ns=2_000_000_000,rss=300),dict(monotonic_ns=4_000_000_000,rss=100)]
        self.assertEqual(integrate_memory(samples,0,4_000_000_000,'rss'),800)
        self.assertEqual(integrate_memory(samples,1_000_000_000,3_000_000_000,'rss'),500)
        self.assertIsNone(integrate_memory(samples,0,1,'unobserved'))

if __name__=='__main__':unittest.main()
