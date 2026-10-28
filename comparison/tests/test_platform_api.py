import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from platform_api_probe import NativeServer,fixture_response,redact


class PlatformApiCalibrationTests(unittest.TestCase):
    def test_provider_only_acknowledges_a_marker_in_the_actual_request(self):
        marker='PLATFORM_INPUT_'+'a'*32
        body=dict(messages=[dict(role='user',content=marker)])
        self.assertEqual(fixture_response(body,None,None,None),dict(text='PLATFORM_ACK:'+marker))
        self.assertEqual(fixture_response(dict(messages=[]),None,None,None),dict(text='CALIBRATION_MISSING_MARKER'))

    def test_launch_token_is_removed_from_retained_native_log(self):
        self.assertEqual(redact('dsh web: http://127.0.0.1:123/?token=synthetic-private\n'),'dsh web: http://127.0.0.1:123/?token=<redacted>\n')

    def test_wrong_rpc_correlation_and_native_rejection_cannot_look_accepted(self):
        server=NativeServer.__new__(NativeServer);server.cookie='owned-only'
        for response,expected in [
            (dict(type='server-response',rpcId='other',result=dict(ok=True,value={'accepted':True})),'envelope mismatch'),
            (dict(type='server-response',rpcId='expected',result=dict(ok=False,error={'code':'gateway/bad-request'})),'RPC failed')]:
            server.http=lambda *args,**kwargs:(200,{},json.dumps(response).encode())
            with patch('platform_api_probe.uuid.uuid4',return_value='expected'):
                with self.assertRaisesRegex(RuntimeError,expected):server.rpc('session/prompt',{})

if __name__=='__main__':unittest.main()
