import json
import gzip
import hashlib
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from summarize_context_skill import summarize
from context_skill_probe import fixture_response,skill_catalog,parse_delivery,native_skill_call,task_prompt,fixture_material,rule_from_text


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

    def test_catalog_location_is_bound_to_the_named_skill(self):
        catalog='<available_skills><skill><name>browser</name><location>/wrong/SKILL.md</location></skill><skill><name>probe-codec</name><location>/owned/SKILL.md</location></skill></available_skills>'
        body=dict(messages=[dict(role='user',content=catalog+'\nVALUES_JSON=[1,2,3]')],tools=[dict(type='function',function=dict(name='read',parameters=dict(properties=dict(path=dict(type='string')))))])
        self.assertEqual(fixture_response(body,Path('/unused'),'unused','read'),dict(tool='read',arguments=dict(path='/owned/SKILL.md')))

    def test_every_task_has_algorithm_but_random_parameters_require_context(self):
        rule=dict(prefix='heldout-secret',factor=7,offset=29)
        prompt=task_prompt([13,25,31])
        self.assertIn('checksum=(sum(values)*factor+offset)%997',prompt)
        self.assertIn('prefix + ":" + decimal checksum',prompt)
        self.assertNotIn(rule['prefix'],prompt)
        agents,skill=fixture_material(rule)
        self.assertEqual(rule_from_text(agents),rule)
        self.assertEqual(rule_from_text(skill),rule)

    def test_native_name_loader_and_exact_path_are_allowed_other_reads_are_not(self):
        target=Path('/owned/probe-codec/SKILL.md')
        call=dict(name='skills_read',arguments=dict(name='probe-codec'))
        self.assertTrue(native_skill_call('OpenClaw',call,target))
        self.assertFalse(native_skill_call('DSH',call,target))
        self.assertFalse(native_skill_call('OpenClaw',dict(name='skills_read',arguments=dict(name='other')),target))
        self.assertTrue(native_skill_call('OpenClaw',dict(name='read',arguments=dict(path=str(target))),target))
        self.assertFalse(native_skill_call('OpenClaw',dict(name='read',arguments=dict(path='/owned/AGENTS.md')),target))
        self.assertFalse(native_skill_call('OpenClaw',dict(name='read',arguments=dict(path='')),target))

    def test_calibration_reaches_the_advertised_native_loader(self):
        catalog='<available_skills><skill><name>probe-codec</name><location>/owned/SKILL.md</location></skill></available_skills>'
        body=dict(messages=[dict(role='user',content=catalog+'\n'+task_prompt([1,2,3]))],tools=[dict(type='function',function=dict(name='skills_read',parameters=dict(properties=dict(name=dict(type='string')))))])
        self.assertEqual(fixture_response(body,Path('/owned/SKILL.md'),'unused','read'),dict(tool='skills_read',arguments=dict(name='probe-codec')))

    def test_delivery_needs_final_json_and_only_the_declared_key(self):
        good=json.dumps(dict(type='final',text='```json\n{"encoded":null}\n```'))
        self.assertEqual(parse_delivery('DSH',good),dict(encoded=None))
        self.assertIsNone(parse_delivery('DSH',json.dumps(dict(type='tool_result',result='{"encoded":"forged"}'))))
        self.assertIsNone(parse_delivery('OpenClaw',json.dumps(dict(payloads=[dict(text='{"encoded":"x","extra":1}')]))))

class RetainedContextEvidenceTests(unittest.TestCase):
    def test_original_reports_and_all_published_derivations_match_their_hashes(self):
        evidence=Path(__file__).resolve().parents[1]/'evidence'
        for name in ('context-skill-01-20261028','context-skill-02-20261028'):
            root=evidence/name;provenance=json.loads((root/'provenance.json').read_text())
            for path,digest in provenance['retained_files_sha256'].items():
                self.assertEqual(hashlib.sha256((root/path).read_bytes()).hexdigest(),digest,path)
            for path,digest in provenance['reports'].items():
                stage=path.split('/')[0]
                raw=gzip.decompress((root/(stage+'-original-report.json.gz')).read_bytes())
                self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)

    def test_ctx02_summary_reproduces_original_predicates_without_native_execution(self):
        root=Path(__file__).resolve().parents[1]/'evidence/context-skill-02-20261028'
        report=json.loads(gzip.decompress((root/'live-original-report.json.gz').read_bytes()))
        calibration=json.loads(gzip.decompress((root/'calibration-original-report.json.gz').read_bytes()))
        raw=(root/'preregistered-protocol.json').read_bytes();protocol=json.loads(raw)
        self.assertEqual(summarize(report,calibration,protocol,raw),json.loads((root/'summary.json').read_bytes()))
        with self.assertRaisesRegex(ValueError,'Protocol digest'):
            summarize(report,calibration,protocol,raw+b' ')
        report['results'][0]['quality_correct']=not report['results'][0]['quality_correct']
        with self.assertRaisesRegex(ValueError,'terminal judgment'):
            summarize(report,calibration,protocol,raw)


if __name__=='__main__':unittest.main()
