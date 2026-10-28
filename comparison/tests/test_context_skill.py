import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from context_skill_probe import fixture_response,skill_catalog,parse_delivery


class ContextSkillAcceptanceTests(unittest.TestCase):
    def test_named_skill_in_user_prompt_does_not_fake_native_discovery(self):
        body=dict(messages=[dict(role='user',content='Use probe-codec. VALUES_JSON=[1,2,3]')],tools=[])
        self.assertEqual(skill_catalog(body),'')
        self.assertEqual(json.loads(fixture_response(body,Path('/owned'),'unused','read')['text']),dict(encoded=None))

    def test_actual_catalog_routes_through_native_loader_before_answer(self):
        body=dict(messages=[dict(role='user',content='<available_skills>\n- `probe-codec`: encode\n</available_skills>\nVALUES_JSON=[1,2,3]')],
            tools=[dict(name='skill',input_schema=dict(type='object',properties=dict(name=dict(type='string'))))])
        decision=fixture_response(body,Path('/owned'),'unused','read')
        self.assertEqual(decision,dict(tool='skill',arguments=dict(name='probe-codec')))

    def test_delivery_needs_final_json_and_only_the_declared_key(self):
        good=json.dumps(dict(type='final',text='```json\n{"encoded":null}\n```'))
        self.assertEqual(parse_delivery('DSH',good),dict(encoded=None))
        self.assertIsNone(parse_delivery('DSH',json.dumps(dict(type='tool_result',result='{"encoded":"forged"}'))))
        self.assertIsNone(parse_delivery('OpenClaw',json.dumps(dict(payloads=[dict(text='{"encoded":"x","extra":1}')]))))

if __name__=='__main__':unittest.main()
