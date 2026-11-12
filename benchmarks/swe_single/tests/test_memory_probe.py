"""Check process coverage and no-inference model-ready observations."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memory_probe import ReadinessRelay, process_memory


class MemoryProbeTests(unittest.TestCase):
    def test_entire_cgroup_process_set_is_measured_with_pss(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);cg = root/'cg';cg.mkdir();proc = root/'proc';proc.mkdir()
            (cg/'cgroup.procs').write_text('11\n12\n')
            for pid, rss, pss in [(11, 1000, 700), (12, 600, 300)]:
                path=proc/str(pid);path.mkdir();(path/'comm').write_text('native\n')
                (path/'smaps_rollup').write_text(f'Rss: {rss} kB\nPss: {pss} kB\n')
            snapshot=process_memory(cg,proc)
            self.assertTrue(snapshot['complete']);self.assertEqual(snapshot['pss_kib'],1000)
            self.assertEqual(snapshot['rss_kib'],1600)
            (proc/'12/smaps_rollup').unlink()
            snapshot=process_memory(cg,proc)
            self.assertFalse(snapshot['complete']);self.assertIsNone(snapshot['pss_kib'])

    def test_readiness_relay_holds_native_stream_without_an_upstream(self):
        with tempfile.TemporaryDirectory() as temp:
            relay=ReadinessRelay('127.0.0.1',Path(temp))
            try:
                data=json.dumps(dict(model='deepseek-flash',stream=True,messages=[])).encode()
                request=urllib.request.Request(relay.base+'/v1/chat/completions',data=data,
                                               headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request,timeout=3) as response:
                    self.assertTrue(response.readline().startswith(b': readiness-probe'))
                    self.assertTrue(relay.ready.wait(1))
                self.assertEqual(len(relay.requests),1)
                self.assertFalse(relay.requests[0]['forwarded'])
            finally:
                relay.close()
            ledger=json.loads((Path(temp)/'readiness-requests.json').read_text())
            self.assertEqual(ledger['upstream_requests'],0)
            self.assertEqual(ledger['generated_tokens'],0)


if __name__=='__main__':
    unittest.main()
