import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from review_platform_native import make_packet,quote_exists


class NativeOnlyPacketTests(unittest.TestCase):
    def test_packet_excludes_external_truth_and_does_not_mutate_original_native_evidence(self):
        arm=dict(condition='owner_exit',block=1,owner=dict(pid=999),boundary_ledger=[dict(hidden='oracle')],
            tasks=dict(primary=dict(session_id='native-id',marker='PLATFORM_INPUT_'+'a'*32)),
            followups=dict(primary=dict(marker='PLATFORM_INPUT_'+'b'*32)),
            cycles=[dict(sanitized_native_log=['cwd /tmp/platform-fault-xyz/1-DSH-owner_exit/workspace'])],
            passive_histories=dict(primary=dict(native=dict(events=dict(records=[]),observer_cli=dict(cpu_seconds=12)),facts=dict(assistant_ack=False))))
        original=copy.deepcopy(arm);packet=make_packet(arm,'random-case')
        self.assertEqual(arm,original)
        text=str(packet)
        for hidden in ('owner_exit','oracle','observer_cli','cpu_seconds','assistant_ack','999'):self.assertNotIn(hidden,text)
        self.assertIn('<owned-root>/workspace',text)
        self.assertIn('native-id',text)

    def test_citation_must_name_an_existing_native_field_with_exact_substring(self):
        packet=dict(native_carrier_logs=[['started']])
        self.assertTrue(quote_exists(packet,'$.native_carrier_logs[0][0]','started'))
        self.assertFalse(quote_exists(packet,'$.native_carrier_logs[0][0]','SIGKILL'))
        self.assertFalse(quote_exists(packet,'$.owner.pid','started'))
        self.assertFalse(quote_exists(packet,None,None))

if __name__=='__main__':unittest.main()
