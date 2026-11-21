"""Safety regression: aggregate error budget, not twelve individually failing buckets."""
import unittest
from cloud_runner import rolling_5xx_exceeded


class ErrorWindowTests(unittest.TestCase):
    def test_one_clean_bucket_does_not_hide_overall_error_budget_breach(self):
        windows={i:[100,10] for i in range(12)}
        windows[5]=[100,0]
        self.assertTrue(rolling_5xx_exceeded(windows,11))

    def test_five_percent_is_not_above_five_percent(self):
        self.assertFalse(rolling_5xx_exceeded({i:[100,5] for i in range(12)},11))

    def test_quiet_window_does_not_trigger(self):
        self.assertFalse(rolling_5xx_exceeded({},11))

    def test_expired_error_bucket_does_not_trigger(self):
        self.assertFalse(rolling_5xx_exceeded({0:[100,100],12:[100,0]},12))


if __name__=='__main__':unittest.main()
