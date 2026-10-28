import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plan_core import plan_core

ROOT = Path(__file__).resolve().parents[1]


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'architecture-core.json').read_text())

    def test_whole_campaign_budget_includes_setup(self):
        plan = plan_core(self.config)
        self.assertEqual(plan['budget']['units'], 144)
        self.assertEqual(plan['budget']['worst_case_runner_seconds'], 14400)
        self.assertFalse(plan['runtime_ready'])
        self.assertTrue(all(r['plan_only'] for r in plan['units']))

    def test_more_repeats_or_time_are_rejected(self):
        for field in ('unit_timeout_seconds', 'setup_seconds_per_product'):
            config = copy.deepcopy(self.config)
            config[field] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                plan_core(config)
        self.config['studies'][0]['repetitions'] += 1
        with self.assertRaises(ValueError):
            plan_core(self.config)

    def test_cannot_raise_ceiling_or_enable_extra_profiles(self):
        for field, value in [('max_aggregate_runner_seconds', 14401), ('profiles_per_product', 2), ('long_soak_enabled', True)]:
            config = copy.deepcopy(self.config)
            config[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                plan_core(config)

    def test_claims_require_observations_and_limits(self):
        for field in ('alternative_explanations', 'required_observations', 'inference_rule', 'limit_and_tradeoff'):
            config = copy.deepcopy(self.config)
            config['studies'][0][field] = ''
            with self.subTest(field=field), self.assertRaises(ValueError):
                plan_core(config)

    def test_default_cli_is_bounded_core(self):
        plan = json.loads(subprocess.check_output([sys.executable, str(ROOT / 'expand_campaign.py')]))
        self.assertEqual(plan['budget']['worst_case_runner_seconds'], 14400)
        self.assertEqual(len(plan['units']), 144)


if __name__ == '__main__':
    unittest.main()
