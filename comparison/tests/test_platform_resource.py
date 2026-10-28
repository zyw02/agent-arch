from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from platform_resource_probe import integrate_memory


class ResidentIntegralTests(unittest.TestCase):
    def test_piecewise_resident_integral_and_missing_observation(self):
        samples=[dict(monotonic_ns=0,rss=100),dict(monotonic_ns=2_000_000_000,rss=300),dict(monotonic_ns=4_000_000_000,rss=100)]
        self.assertEqual(integrate_memory(samples,0,4_000_000_000,'rss'),800)
        self.assertEqual(integrate_memory(samples,1_000_000_000,3_000_000_000,'rss'),500)
        self.assertIsNone(integrate_memory(samples,0,1,'unobserved'))

if __name__=='__main__':unittest.main()
