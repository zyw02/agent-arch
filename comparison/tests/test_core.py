import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plan_core import plan_core, DIMENSIONS, MECHANISMS
ROOT = Path(__file__).resolve().parents[1]


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'architecture-core.json').read_text())

    def test_seven_studies_cover_both_layers(self):
        plan = plan_core(self.config)
        self.assertEqual(plan['scope']['studies'], 7)
        self.assertEqual(plan['scope']['complete_blocks'], 42)
        self.assertEqual(plan['scope']['planned_arms'], 192)
        for layer in ('platform', 'harness'):
            self.assertEqual({d for s in plan['studies'] if s['layer'] == layer for d in s['primary_dimensions']}, DIMENSIONS)
        self.assertFalse(plan['runtime_ready'])

    def test_no_arm_or_control_is_scheduled_outside_its_complete_block(self):
        plan = plan_core(self.config)
        lookup = {r['unit_id']: r for r in plan['units']}
        for block in plan['blocks']:
            for unit_id in block['unit_ids']:
                row = lookup[unit_id]
                self.assertIn(row['control_unit_id'], block['unit_ids'])
                self.assertNotIn('timeout_seconds', row)
                self.assertTrue(row['plan_only'])

    def test_missing_dimension_and_missing_control_rejected(self):
        self.config['studies'][0]['primary_dimensions'] = ['Reliability', 'Security']
        with self.assertRaises(ValueError):
            plan_core(self.config)
        self.setUp()
        del self.config['studies'][0]['control_conditions']['healthy']
        with self.assertRaises(ValueError):
            plan_core(self.config)

    def test_universal_cutoffs_and_extra_studies_rejected(self):
        for field in ('campaign_wall_cutoff_seconds', 'universal_unit_timeout_seconds'):
            c = copy.deepcopy(self.config)
            c['execution_policy'][field] = 90
            with self.subTest(field=field), self.assertRaises(ValueError):
                plan_core(c)
        self.config['studies'].append(copy.deepcopy(self.config['studies'][0]))
        with self.assertRaises(ValueError):
            plan_core(self.config)

    def test_claims_require_observations_and_limits(self):
        for field in ('required_observations', 'inference_rule', 'completion_requirements'):
            c = copy.deepcopy(self.config)
            c['studies'][0][field] = ''
            with self.subTest(field=field), self.assertRaises(ValueError):
                plan_core(c)

    def test_default_cli_uses_focused_plan_without_budget(self):
        plan = json.loads(subprocess.check_output([sys.executable, str(ROOT / 'expand_campaign.py')]))
        self.assertEqual(len(plan['studies']), 7)
        self.assertNotIn('budget', plan)
        self.assertIsNone(plan['execution_policy']['campaign_wall_cutoff_seconds'])


    def test_memory_collaboration_and_security_checks_cannot_disappear(self):
        for study_id, checks in MECHANISMS.items():
            for check in checks:
                c = copy.deepcopy(self.config)
                study = next(s for s in c['studies'] if s['id'] == study_id)
                study['mechanism_checks'].remove(check)
                with self.subTest(study=study_id, check=check), self.assertRaisesRegex(ValueError, 'mechanism'):
                    plan_core(c)

    def test_security_controls_cannot_be_replaced_by_unrelated_baseline(self):
        c = copy.deepcopy(self.config)
        study = next(s for s in c['studies'] if s['id'] == 'HC')
        study['control_conditions']['memory_scope_cross_access'] = 'binding_control'
        with self.assertRaisesRegex(ValueError, 'matched mechanism control'):
            plan_core(c)

    def test_memory_and_child_lifecycle_arms_are_emitted(self):
        p = plan_core(self.config)
        for product in self.config['products']:
            conditions = {u['condition'] for u in p['units'] if u['product'] == product}
            self.assertTrue({'fresh_session_memory_enabled', 'fresh_session_memory_disabled',
                             'native_two_children', 'one_child_failure', 'parent_cancellation',
                             'untrusted_content_injection', 'child_scope_escalation',
                             'memory_scope_cross_access'} <= conditions)


if __name__ == '__main__':
    unittest.main()
