import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from platform_api_probe import NativeServer,fixture_response,redact,fresh_session_bindings,select_service_owner
from platform_fault_probe import Gate,history_facts,safe_histories
import os
import threading
import subprocess


class PlatformApiCalibrationTests(unittest.TestCase):
    def test_native_history_unavailable_response_is_retained_and_is_not_a_missing_ack(self):
        server=NativeServer.__new__(NativeServer);server.product='OpenClaw';server.port=1234;server.runtime=Path('/owned/runtime');server.workspace=Path('/owned/workspace');server.env={}
        failure=subprocess.CompletedProcess([],1,stdout='{"error":"UNAVAILABLE: startup inspection pending"}',stderr='')
        with patch('platform_api_probe.subprocess.run',return_value=failure):
            result=safe_histories(server,dict(primary=dict(session_id='native-id',marker='PLATFORM_INPUT_'+'a'*32)))['primary']
        self.assertIsNone(result['facts']);self.assertIn('UNAVAILABLE',result['native']['history_error']['stdout'])

    def test_owner_must_be_unique_native_root_with_worker_uid_and_start_identity(self):
        root=dict(pid=17,ppid=1,uid=os.getuid(),start_ticks=52,cmdline='openclaw-gateway')
        child=dict(pid=18,ppid=17,uid=os.getuid(),start_ticks=53,cmdline='node worker')
        self.assertEqual(select_service_owner([root,child],'OpenClaw'),root)
        with self.assertRaisesRegex(RuntimeError,'Ambiguous'):select_service_owner([root,{**child,'ppid':1}],'OpenClaw')
        with self.assertRaisesRegex(RuntimeError,'identity'):select_service_owner([{**root,'uid':-1}],'OpenClaw')
        with self.assertRaisesRegex(RuntimeError,'command'):select_service_owner([{**root,'cmdline':'sudo monitor'}],'OpenClaw')

    def test_fault_gate_records_actual_arrival_before_release_and_keeps_title_separate(self):
        marker='PLATFORM_INPUT_'+'a'*32;gate=Gate([marker]);result=[]
        body=dict(messages=[dict(role='user',content=marker)])
        thread=threading.Thread(target=lambda:result.append(gate.decide(body)));thread.start()
        try:
            self.assertTrue(gate.arrived[marker].wait(1));self.assertEqual(len(gate.ledger),1)
            self.assertFalse(result);self.assertNotIn('released_ns',gate.ledger[0])
        finally:gate.release.set();thread.join()
        self.assertEqual(result,[dict(text='PLATFORM_ACK:'+marker)])
        title=Gate([marker]);title.decide(dict(messages=[dict(role='user',content='Generate the session title from this JSON array '+marker)]))
        self.assertFalse(title.arrived[marker].is_set())

    def test_native_ack_must_come_from_assistant_not_user_echo_or_fixture_string(self):
        marker='PLATFORM_INPUT_'+'a'*32
        history=dict(events=dict(records=[dict(event=dict(type='user/message',data=dict(content=[dict(type='text',text=marker+' PLATFORM_ACK:'+marker)])))]))
        self.assertEqual(history_facts('DSH',history,marker),dict(user_retained=True,assistant_ack=False))
        history['events']['records'].append(dict(event=dict(type='assistant/message',data=dict(message=dict(role='assistant',content=[dict(type='text',text='PLATFORM_ACK:'+marker)])))))
        self.assertTrue(history_facts('DSH',history,marker)['assistant_ack'])
        self.assertFalse(history_facts('OpenClaw',dict(history=dict(messages=[dict(role='user',content='PLATFORM_ACK:'+marker)])),marker)['assistant_ack'])

    def test_provider_only_acknowledges_a_marker_in_the_actual_request(self):
        marker='PLATFORM_INPUT_'+'a'*32
        body=dict(messages=[dict(role='user',content=marker)])
        self.assertEqual(fixture_response(body,None,None,None),dict(text='PLATFORM_ACK:'+marker))
        self.assertEqual(fixture_response(dict(messages=[]),None,None,None),dict(text='CALIBRATION_MISSING_MARKER'))

    def test_launch_token_is_removed_from_retained_native_log(self):
        self.assertEqual(redact('dsh web: http://127.0.0.1:123/?token=synthetic-private\n'),'dsh web: http://127.0.0.1:123/?token=<redacted>\n')

    def test_native_session_projection_and_disjoint_context_are_required(self):
        tasks=[dict(session_id=str(i),session_key='agent:main:platform:'+str(i),marker='PLATFORM_INPUT_'+digit*32) for i,digit in enumerate(('a','b'))]
        requests=[dict(request=dict(messages=[dict(role='user',content=t['marker']+'\nRuntime: agent=main | session='+t['session_key']+' | model=fixture')])) for t in tasks]
        self.assertTrue(fresh_session_bindings('OpenClaw',tasks,requests)['valid'])
        requests[1]['request']['messages'][0]['content']+='\n'+tasks[0]['marker']
        self.assertFalse(fresh_session_bindings('OpenClaw',tasks,requests)['valid'])
        requests[1]['request']['messages'][0]['content']=tasks[1]['marker']
        self.assertFalse(fresh_session_bindings('OpenClaw',tasks,requests)['valid'])

    def test_wrong_rpc_correlation_and_native_rejection_cannot_look_accepted(self):
        server=NativeServer.__new__(NativeServer);server.cookie='owned-only'
        for response,expected in [
            (dict(type='server-response',rpcId='other',result=dict(ok=True,value={'accepted':True})),'envelope mismatch'),
            (dict(type='server-response',rpcId='expected',result=dict(ok=False,error={'code':'gateway/bad-request'})),'RPC failed')]:
            server.http=lambda *args,**kwargs:(200,{},json.dumps(response).encode())
            with patch('platform_api_probe.uuid.uuid4',return_value='expected'):
                with self.assertRaisesRegex(RuntimeError,expected):server.rpc('session/prompt',{})

if __name__=='__main__':unittest.main()
