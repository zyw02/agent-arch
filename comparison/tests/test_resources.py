import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from resource_collector import counters, disk_inventory
from live_read_provider import observe_event,real_usage


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

class StreamAccountingTests(unittest.TestCase):
    def test_anthropic_cumulative_output_is_merged_not_summed(self):
        row=dict(endpoint='/v1/messages',usage_events=[],tool_names=[],http_status=200)
        observe_event(dict(type='message_start',message=dict(usage=dict(input_tokens=100,output_tokens=0))),row)
        observe_event(dict(type='message_delta',usage=dict(output_tokens=3)),row)
        observe_event(dict(type='message_delta',usage=dict(output_tokens=8)),row)
        observe_event(dict(type='message_stop'),row)
        result=real_usage([row])['requests'][0]
        self.assertEqual(result['usage'],dict(input_tokens=100,output_tokens=8))
        self.assertTrue(result['complete'])

    def test_partial_stream_with_usage_is_not_complete(self):
        row=dict(endpoint='/v1/chat/completions',usage_events=[dict(prompt_tokens=100)],tool_names=[],http_status=200)
        self.assertFalse(real_usage([row])['requests'][0]['complete'])

if __name__=='__main__':unittest.main()
