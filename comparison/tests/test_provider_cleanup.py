import http.client
import json
from pathlib import Path
import sys
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from native_read_probe import Provider


class SyntheticProviderCleanupTests(unittest.TestCase):
    def test_close_waits_for_admitted_exchange_and_retains_its_own_record(self):
        arrived=threading.Event();release=threading.Event();shutdown_done=threading.Event();closed=threading.Event();results=[]
        def decide(*unused):arrived.set();release.wait(3);return dict(text='ACK')
        provider=Provider(Path('/unused'),'unused',decision_fn=decide)
        def request():
            connection=http.client.HTTPConnection('127.0.0.1',provider.server.server_port,timeout=5)
            try:
                connection.request('POST','/v1/chat/completions',json.dumps(dict(messages=[dict(role='user',content='unique-input')])));response=connection.getresponse();results.append(json.loads(response.read()))
            finally:connection.close()
        worker=threading.Thread(target=request);worker.start();self.assertTrue(arrived.wait(2))
        original_shutdown=provider.server.shutdown
        def shutdown():original_shutdown();shutdown_done.set()
        provider.server.shutdown=shutdown
        def close():provider.close();closed.set()
        closer=threading.Thread(target=close);closer.start()
        try:
            self.assertTrue(shutdown_done.wait(2));self.assertFalse(closed.is_set())
        finally:release.set();worker.join(3);closer.join(3)
        self.assertTrue(closed.is_set());self.assertEqual(results[0]['choices'][0]['message']['content'],'ACK')
        self.assertEqual(provider.requests[0]['request']['messages'][0]['content'],'unique-input')
        self.assertIn('fixture_settled_ns',provider.requests[0])

if __name__=='__main__':unittest.main()
