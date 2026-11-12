"""Check observed scheduling cannot bypass admission or change frozen prompts."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from observed import combine, require_gate, selected_protocol
from run import calibration_prompt, formal_prompt


class ObservedTests(unittest.TestCase):
    def test_extended_timeout_changes_only_the_single_product_task_limit(self):
        original = json.loads((HERE / 'protocol-six.json').read_text())
        protocol = selected_protocol('openclaw57_patched', 1800)
        self.assertEqual(protocol['execution']['task_timeout_seconds'], 1800)
        expected_execution = dict(original['execution'], task_timeout_seconds=1800)
        self.assertEqual(protocol['execution'], expected_execution)
        self.assertEqual(protocol['provider'], original['provider'])
        self.assertEqual(protocol['products'], {'openclaw57_patched': original['products']['openclaw57_patched']})
        self.assertEqual(json.loads((HERE / 'protocol-six.json').read_text()), original)
        self.assertEqual(selected_protocol('openclaw57_patched', 600)['execution'], original['execution'])
        with self.assertRaises(ValueError):
            selected_protocol('openclaw57_patched', 3600)

    def test_formal_prompt_is_exactly_the_historical_prompt(self):
        task = json.loads((HERE / 'task.json').read_text())
        self.assertEqual(hashlib.sha256(formal_prompt(task).encode()).hexdigest(),
                         'a2c8ae7bced265097552c0ef19757fd95b3b4847fb805136770249331fd9372c')

    def test_admission_rejects_failed_calibration_and_changed_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controls = root / 'segments/controls/controls'
            controls.mkdir(parents=True)
            acceptance = controls / 'acceptance.json'
            acceptance.write_text(json.dumps(dict(passed=False)))
            with self.assertRaisesRegex(ValueError, 'Hidden-test'):
                require_gate(root, 'openclaw57_patched', 'block-1', 'image')
            acceptance.write_text(json.dumps(dict(passed=True)))
            (controls.parent / 'environment.json').write_text(json.dumps(dict(image_id='old')))
            calibration = root / 'segments/calibration'
            calibration.mkdir()
            summary = calibration / 'summary.json'
            result = dict(product='openclaw57_patched', calibration_passed=False)
            summary.write_text(json.dumps(dict(results=[result])))
            with self.assertRaisesRegex(ValueError, 'calibration'):
                require_gate(root, 'openclaw57_patched', 'block-1', 'image')
            result['calibration_passed'] = True
            summary.write_text(json.dumps(dict(results=[result])))
            with patch('observed.subprocess.check_output', return_value='new\n'):
                with self.assertRaisesRegex(ValueError, 'Image differs'):
                    require_gate(root, 'openclaw57_patched', 'block-1', 'image')
            protocol_path = root / 'protocol.json'
            protocol_path.write_text('{}')
            (controls.parent / 'environment.json').write_text(json.dumps(dict(
                image_id='old', protocol_sha256='different-timeout-protocol')))
            with patch('observed.subprocess.check_output', return_value='old\n'):
                with self.assertRaisesRegex(ValueError, 'Protocol differs'):
                    require_gate(root, 'openclaw57_patched', 'block-1', 'image', protocol_path)

    def test_incremental_combination_keeps_previous_and_failed_run_evidence(self):
        with tempfile.TemporaryDirectory() as tmp, patch('observed.subprocess.run'):
            root = Path(tmp)
            for stage in ('controls', 'calibration', 'block-1'):
                segment = root / 'segments' / stage
                segment.mkdir(parents=True)
                (segment / 'environment.json').write_text(json.dumps(dict(image_id='same')))
                (segment / 'observation.json').write_text(json.dumps(dict(stage=stage)))
                result = dict(run_id=stage, resolved=False)
                (segment / 'summary.json').write_text(json.dumps(dict(
                    results=[] if stage == 'controls' else [result],
                    latest_accounting={}, elapsed_seconds=1)))
                evidence = segment / 'runs' / stage
                evidence.mkdir(parents=True)
                (evidence / 'raw.txt').write_text(stage)
                combine(root)
            combine(root)
            combined = json.loads((root / 'campaign/summary.json').read_text())
            self.assertEqual([r['run_id'] for r in combined['results']], ['calibration', 'block-1'])
            self.assertFalse(combined['results'][-1]['resolved'])
            self.assertEqual((root / 'campaign/runs/calibration/raw.txt').read_text(), 'calibration')


if __name__ == '__main__':
    unittest.main()
