import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inspect_reuse_archives import inspect


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

if __name__=='__main__':unittest.main()
