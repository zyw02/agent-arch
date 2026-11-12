"""Reject idle observations that did not initialize the requested SDK."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from idle_memory import configuration, validate_idle


class IdleMemoryTests(unittest.TestCase):
    def test_idle_requires_initialized_sdk_and_no_agent_tasks(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            path = home / '.openclaw/openclaw.json'; path.parent.mkdir()
            path.write_text(json.dumps(configuration(home)))
            with self.assertRaisesRegex(ValueError, 'SDK initialization'):
                validate_idle(home, '')
            logs = '[agentloop] tools prewarm ==========\n[agentloop] all apps loaded apps=[]'
            self.assertTrue(validate_idle(home, logs)['sdk_initialized'])
            (home / 'unexpected.trajectory.jsonl').write_text('{}\n')
            with self.assertRaisesRegex(ValueError, 'Unexpected agent task'):
                validate_idle(home, logs)


if __name__ == '__main__':
    unittest.main()
