"""Admission, balanced ordering, and mandatory pre-solver idle measurement."""
import argparse
import json
import os
import re
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paired_campaign as paired


class PairedCampaignTests(unittest.TestCase):
    def test_workflow_executes_all_36_attempts_in_the_preregistered_order(self):
        repo=Path(__file__).resolve().parents[3]
        workflow=(repo/'.github/workflows/swe-two-task-same-host.yml').read_text()
        actual=[(int(i),p) for i,p in re.findall(r'--stage round --round (\d+) --product ([a-z0-9_]+)',workflow)]
        expected=[(b['index'],p) for b in paired.schedule() for p in b['products']]
        self.assertEqual(actual,expected)

    def test_split_steps_cannot_skip_an_incomplete_preceding_product(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'calibration-acceptance.json').write_text('{"passed":true}')
            args=argparse.Namespace(output=root,round=0,product='codex')
            with patch.object(paired,'require_controls'), patch.object(paired,'campaign_for') as prepare:
                with self.assertRaisesRegex(ValueError,'Previous product incomplete'):
                    paired.round_stage(args)
            prepare.assert_not_called()

    def test_two_tasks_three_repeats_and_every_product_visits_every_order_position(self):
        plan = paired.schedule()
        self.assertEqual(len(plan), 6)
        for task in paired.TASKS:
            self.assertEqual([b['repeat'] for b in plan if b['task_id']==task], [1,2,3])
        for product in paired.PRODUCTS:
            self.assertEqual(sorted(b['products'].index(product) for b in plan), list(range(6)))
        self.assertEqual(plan[0]['products'][0], 'openclaw57_patched')

    def test_admission_refuses_short_remaining_time_without_shortening_solver_timeout(self):
        with self.assertRaisesRegex(RuntimeError, 'unshortened'):
            paired.admit_time(3000, now=0)
        self.assertGreater(paired.admit_time(10000, now=0)['reserved_seconds'], 1800)
        with patch.dict(os.environ, {'BENCH_CPUSET_CPUS':'0,1,2,3', 'BENCH_ALLOCATED_CPUS':'4'}):
            protocol = paired.protocol_for(paired.TASKS[0])
        self.assertEqual(protocol['execution']['task_timeout_seconds'], 1800)
        self.assertEqual(protocol['execution']['provider_request_timeout_seconds'], 540)
        self.assertEqual(protocol['execution']['grading_timeout_seconds'], 540)
        self.assertEqual(protocol['execution']['cpuset_cpus'], '0,1,2,3')
        self.assertEqual(protocol['execution']['cpus'], 4)
        self.assertIsNone(protocol['execution']['maximum_provider_attempts_per_run'])
        self.assertEqual(set(protocol['products']), set(paired.PRODUCTS))

    def test_failed_idle_does_not_launch_the_solver(self):
        with tempfile.TemporaryDirectory() as temp:
            args=argparse.Namespace(output=Path(temp))
            campaign=Mock()
            with patch.object(paired, 'verify_host'), patch.object(paired, 'admit_time'), \
                 patch.object(paired, 'measure_before', side_effect=ValueError('bad idle')), \
                 patch.dict(os.environ, {'BENCH_JOB_DEADLINE_UTC':'9999999999'}):
                with self.assertRaisesRegex(ValueError, 'bad idle'):
                    paired.solve(args, campaign, 'dsh', paired.TASKS[0], 1)
            campaign.run_product.assert_not_called()

    def test_solver_launch_is_after_idle_and_result_retains_pair_identity(self):
        calls=[]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            args=argparse.Namespace(output=root)
            campaign=Mock()
            campaign.out=root/'segment'
            (campaign.out/'runs/block-1-dsh').mkdir(parents=True)
            campaign.task={}
            campaign.relays=[argparse.Namespace(run_id='block-1-dsh', records=[])]
            def idle(*args):
                calls.append('idle')
                return root/'idle/paired-result.json'
            def run(*args, **kwargs):
                calls.append('solver')
                return dict(resolved=True, wall_seconds=2)
            campaign.run_product.side_effect=run
            with patch.object(paired,'verify_host'), patch.object(paired,'measure_before',side_effect=idle), \
                 patch.object(paired,'formal_prompt',return_value='frozen prompt'), \
                 patch.dict(os.environ,{'BENCH_JOB_DEADLINE_UTC':str(time.time()+10000)}):
                result=paired.solve(args,campaign,'dsh',paired.TASKS[0],1)
            self.assertEqual(calls,['idle','solver'])
            self.assertEqual(result['preceding_idle_result'],'idle/paired-result.json')

    def test_finalize_keeps_missing_attempts_instead_of_ranking_them_as_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'host.json').write_text('{}')
            with patch.dict(os.environ,{'GITHUB_STEP_SUMMARY':''}):
                summary=paired.finalize(argparse.Namespace(output=root))
            self.assertEqual(summary['expected'],36)
            self.assertEqual(summary['completed'],0)
            self.assertFalse(summary['complete'])
            self.assertFalse(summary['comparison_ready'])
            self.assertTrue(all(r['status']=='not_completed' for r in summary['attempts']))
