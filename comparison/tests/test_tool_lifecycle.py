import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tool_lifecycle_mcp import ReadFixture
from tool_lifecycle_provider import response_parts
from tool_lifecycle_probe import ToolPlan,native_cancelled,read_ledger,fixture_receipts_complete


class ToolLifecycleTests(unittest.TestCase):
    def test_provider_does_not_use_answer_echo_in_user_prompt_as_a_tool_result(self):
        plan=ToolPlan('DSH','native_single',[Path('/owned/'+str(i)) for i in range(4)],['VALUE_'+str(i) for i in range(4)],'failure')
        body=dict(tools=[dict(name='read',input_schema=dict(type='object',properties=dict(path=dict(type='string'))))],messages=[dict(role='user',content=plan.prompt+' VALUE_0')])
        decision=plan.decide(body)
        self.assertEqual(decision['calls'][0]['arguments'],dict(path='/owned/0'))
        self.assertNotIn('text',decision)

    def test_batch_result_correlation_rejects_swapped_values_and_accepts_explicit_partial_failure(self):
        values=['VALUE_'+str(i) for i in range(4)];plan=ToolPlan('OpenClaw','mcp_batch_failure',[Path('/owned/'+str(i)) for i in range(4)],values,'CONTROLLED_FAILURE')
        messages=[dict(role='tool',tool_call_id=plan.call_ids[i],content=values[i] if i!=2 else 'Error: CONTROLLED_FAILURE') for i in range(4)]
        self.assertEqual(plan.decide(dict(messages=messages))['text'],plan.expected_text)
        self.assertNotIn(values[2],plan.expected_text)
        messages[0]['tool_call_id'],messages[1]['tool_call_id']=messages[1]['tool_call_id'],messages[0]['tool_call_id']
        self.assertTrue(plan.decide(dict(messages=messages))['text'].startswith('FIXTURE_RESULT_WITHOUT_MATCHING_VALUE'))

    def test_protocol_streams_preserve_all_four_call_ids_and_arguments(self):
        calls=[dict(id='call_'+str(i),name='probe__eval_read',arguments=dict(index=i)) for i in range(4)]
        for anthropic in (False,True):
            response,events=response_parts(dict(stream=True,_anthropic=anthropic),dict(calls=calls),'response')
            data=[json.loads(line.split(b'data: ',1)[1].strip()) for line in events if b'data: ' in line and b'[DONE]' not in line]
            if anthropic:
                self.assertEqual([b['id'] for b in response['content']],[c['id'] for c in calls])
                deltas=[e['delta'] for e in data if e['type']=='content_block_delta']
                self.assertEqual([json.loads(d['partial_json']) for d in deltas],[c['arguments'] for c in calls])
            else:
                emitted=data[0]['choices'][0]['delta']['tool_calls']
                self.assertEqual([c['id'] for c in emitted],[c['id'] for c in calls])
                self.assertEqual([json.loads(c['function']['arguments']) for c in emitted],[c['arguments'] for c in calls])
                self.assertEqual(data[-1]['usage']['total_tokens'],2)

    def config(self,root,**extra):
        files=[]
        for i in range(4):
            file=root/str(i);file.write_text('VALUE_'+str(i));files.append(str(file))
        return dict(files=files,ledger=str(root/'ledger.jsonl'),cleanup_release=str(root/'release'),failure_marker='FAILURE',**extra)

    def test_owned_mcp_is_concurrent_and_records_real_read_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sent=[];fixture=ReadFixture(self.config(root,delay_seconds=.15),sent.append)
            for i in range(4):fixture.dispatch(dict(jsonrpc='2.0',id=i,method='tools/call',params=dict(name='eval_read',arguments=dict(index=i))))
            for thread in fixture.threads:thread.join(timeout=2)
            fixture.finish();events=read_ledger(root/'ledger.jsonl')
            starts=[e['monotonic_ns'] for e in events if e['kind']=='call_received'];ends=[e['monotonic_ns'] for e in events if e['kind']=='file_read']
            self.assertEqual(len(starts),4);self.assertEqual(len(sent),4);self.assertLess(max(starts),min(ends))
            for e in [e for e in events if e['kind']=='file_read']:self.assertEqual(e['sha256'],hashlib.sha256(('VALUE_'+str(e['index'])).encode()).hexdigest())

    def test_native_cancel_notification_stops_held_call_without_read_or_success_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sent=[];fixture=ReadFixture(self.config(root,hold_index=2),sent.append)
            fixture.dispatch(dict(jsonrpc='2.0',id=7,method='tools/call',params=dict(name='eval_read',arguments=dict(index=2))))
            deadline=time.monotonic()+2
            while time.monotonic()<deadline and not any(e['kind']=='hold_entered' for e in read_ledger(root/'ledger.jsonl')):time.sleep(.005)
            fixture.dispatch(dict(jsonrpc='2.0',method='notifications/cancelled',params=dict(requestId=7)))
            fixture.finish();events=read_ledger(root/'ledger.jsonl')
            self.assertEqual(sent,[]);self.assertFalse(any(e['kind']=='file_read' for e in events))
            self.assertTrue(any(e['kind']=='call_stopped' and e['reason']=='cancelled' for e in events))

    def test_cleanup_release_and_controlled_failure_never_perform_the_target_read(self):
        for kind in ('cleanup','failure'):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);sent=[];extra=dict(hold_index=2) if kind=='cleanup' else dict(fail_index=2)
                fixture=ReadFixture(self.config(root,**extra),sent.append)
                if kind=='cleanup':(root/'release').touch()
                fixture.dispatch(dict(jsonrpc='2.0',id=9,method='tools/call',params=dict(name='eval_read',arguments=dict(index=2))))
                fixture.threads[0].join(timeout=2);fixture.finish()
                self.assertTrue(sent[0]['result']['isError']);self.assertFalse(any(e['kind']=='file_read' for e in read_ledger(root/'ledger.jsonl')))

    def test_native_cancellation_needs_structured_terminal_status(self):
        self.assertFalse(native_cancelled('DSH',dict(events=dict(records=[dict(event=dict(type='assistant/message',data=dict(text='aborted user')))]))))
        terminal=dict(type='turn/end',data=dict(reason=dict(kind='aborted',reason=dict(kind='user'))))
        self.assertTrue(native_cancelled('DSH',dict(events=dict(records=[dict(event=terminal)]))))
        self.assertFalse(native_cancelled('OpenClaw',dict(history=dict(messages=[dict(content='aborted')]))))
        self.assertTrue(native_cancelled('OpenClaw',dict(history=dict(messages=[dict(stopReason='aborted')]))))

    def test_final_answer_alone_cannot_replace_a_matching_independent_read_receipt(self):
        row=dict(condition='mcp_single',fixture_events=[],file_hashes={'0':'expected'},fixture_config={})
        self.assertFalse(fixture_receipts_complete(row))
        row['fixture_events']=[dict(kind='file_read',index=0,mcp_call_id=7,sha256='expected',monotonic_ns=1),dict(kind='result_sent',index=0,mcp_call_id=8,is_error=False,content_sha256='expected',monotonic_ns=2)]
        self.assertFalse(fixture_receipts_complete(row))
        row['fixture_events'][1]['mcp_call_id']=7
        self.assertTrue(fixture_receipts_complete(row))


if __name__=='__main__':unittest.main()
