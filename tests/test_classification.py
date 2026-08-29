import unittest

from specjam.classification import classify_request


class ClassificationTests(unittest.TestCase):
    def test_ambiguous_or_critical_work_starts_in_discovery(self):
        self.assertEqual(classify_request("Change the payment architecture", critical=True).flow, "discovery")
        self.assertEqual(classify_request("",).flow, "discovery")

    def test_bounded_work_stays_in_daily(self):
        self.assertEqual(classify_request("What is the current API?").flow, "daily")


if __name__ == "__main__":
    unittest.main()
