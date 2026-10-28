import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from expand_campaign import expand, validate_load_freeze


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.campaign = json.loads(Path(__file__).resolve().parents[1].joinpath('campaign.json').read_text())
        cls.rows = expand(cls.campaign)

    def test_required_baseline_observations_cannot_be_removed(self):
        for case_id in ('P01', 'H05'):
            for field in ('native_outcome', 'independent_oracle'):
                c = copy.deepcopy(self.campaign)
                next(case for case in c['cases'] if case['id'] == case_id)['required_observations'].remove(field)
                with self.subTest(case=case_id, field=field), self.assertRaises(ValueError):
                    expand(c)

    def test_extensions_cannot_be_removed(self):
        for case_id, factor, condition in [('P02', 'state_contract', None), ('H04', 'task_kind', None), ('H14', 'integration_state', 'C6')]:
            c = copy.deepcopy(self.campaign)
            case = next(case for case in c['cases'] if case['id'] == case_id)
            factors = case['factors'] if condition is None else case['condition_factors'][condition]
            factors[factor].pop()
            with self.subTest(case=case_id), self.assertRaises(ValueError):
                expand(c)

    def test_control_links_match_fixture_and_repeat(self):
        lookup = {r['unit_id']: r for r in self.rows}
        for row in self.rows:
            control = lookup[row['control_unit_id']]
            self.assertEqual((row['track'], row['repeat']), (control['track'], control['repeat']))
            for factor in ('instance', 'family', 'idempotency', 'task_kind', 'size_kib', 'state_contract'):
                if factor in row['factors']:
                    self.assertEqual(row['factors'][factor], control['factors'][factor])
            if 'integration_control_unit_id' in row:
                self.assertEqual(lookup[row['integration_control_unit_id']]['factors']['integration_state'], 'normal')
            if 'paired_unit_id' in row:
                self.assertNotEqual(row['factors']['arm'], lookup[row['paired_unit_id']]['factors']['arm'])

    def test_missing_control_fails(self):
        c = copy.deepcopy(self.campaign)
        c['cases'][0]['conditions'].remove('C0')
        with self.assertRaisesRegex(ValueError, 'control'):
            expand(c)

    def test_timing_and_real_model_repetitions(self):
        for track, expected in [('D', 6), ('N', 15), ('C', 15)]:
            self.assertEqual(len([r for r in self.rows if r['case'] == 'H08' and r['condition'] == 'C0' and r['track'] == track]), expected)
        for track in ('N', 'C'):
            for condition in ('C0', 'C1'):
                for kind in ('markers', 'distributed_aggregate'):
                    for size in (8, 64, 256):
                        self.assertEqual(len([r for r in self.rows if r['case'] == 'H04' and r['condition'] == condition and r['track'] == track and r['factors']['task_kind'] == kind and r['factors']['size_kib'] == size]), 15)
        self.assertEqual(len([r for r in self.rows if r['case'] == 'H18']), 360)

    def test_no_formal_scheduling_and_load_gate_closed_by_default(self):
        self.assertTrue(all(r['plan_only'] for r in self.rows))
        load = [r for r in self.rows if r['load_gate']]
        self.assertEqual(len(load), 72)
        self.assertTrue(all(not r['load_gate_satisfied'] for r in load))

    def test_load_freeze_evidence_and_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'capacity.json'
            report.write_text('{"kind":"synthetic-test-report"}')
            entry = {'path': report.name, 'sha256': hashlib.sha256(report.read_bytes()).hexdigest()}
            freeze = dict(selected_arrival_intervals_s=['2', '0.5'], capacity_controls_passed=True,
                          selection_rationale='synthetic test only', fixture_capacity=entry, observer_overhead=entry,
                          **{k: 10 for k in ('max_generator_delay_ms', 'max_fixture_p95_ms', 'max_observer_cpu_percent',
                                            'stop_memory_percent', 'stop_processes', 'stop_generator_delay_ms')})
            path = root / 'freeze.json'
            path.write_text(json.dumps(freeze))
            rows = expand(self.campaign, validate_load_freeze(path))
            self.assertEqual(len([r for r in rows if r['load_gate'] and r['load_gate_satisfied']]), 48)
            report.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Checksum'):
                validate_load_freeze(path)

    def test_invalid_freeze_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'freeze.json'
            p.write_text(json.dumps({'selected_arrival_intervals_s': ['2', '2']}))
            with self.assertRaises(ValueError):
                validate_load_freeze(p)


if __name__ == '__main__':
    unittest.main()
