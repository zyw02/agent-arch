import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from resource_collector import counters, disk_inventory


class ResourceAccountingTests(unittest.TestCase):
    def test_disk_does_not_follow_external_symlink_or_count_hardlinks_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);inside=root/'inside';inside.mkdir()
            payload=inside/'payload';payload.write_bytes(b'a'*10000)
            outside=root/'outside';outside.write_bytes(b'b'*20000)
            (inside/'external').symlink_to(outside)
            os.link(payload,inside/'hardlink')
            observed=disk_inventory(dict(first=inside,overlap=payload))
            expected=sum(p.lstat().st_size for p in (inside,payload,inside/'external'))
            self.assertEqual(observed['logical_bytes'],expected)
            self.assertEqual(observed['categories']['overlap']['objects'],0)
            self.assertEqual(observed['errors'],[])

    def test_cpu_and_smaps_units_remain_separate_at_parser_boundary(self):
        self.assertEqual(counters('usage_usec 123\nuser_usec 100\nsystem_usec 23\n'),
                         dict(usage_usec=123,user_usec=100,system_usec=23))
        self.assertEqual(counters('Pss: 42\nRss: 84\n'),dict(Pss=42,Rss=84))

if __name__=='__main__':unittest.main()
