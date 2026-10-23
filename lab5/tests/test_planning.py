"""Focused offline regression checks; never query Azure or count as graded evidence."""
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from cloudlayer.planning import BillingThrottled, cost_response, retry_delay
from cloudlayer.readiness import quota_summary
from scripts.plan_run import select_linux_meter


class PlanningTests(unittest.TestCase):
    def test_longest_throttle_header_wins(self):
        delay, _ = retry_delay({"Retry-After": "1",
                               "x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after": "47"})
        self.assertEqual(delay, 47)

    def test_billing_retries_after_server_delay(self):
        failure = HTTPError("https://management.azure.com/test", 429, "throttled",
                            {"Retry-After": "1"}, None)
        with patch("cloudlayer.planning.urlopen", side_effect=[failure, BytesIO(b"{}")]) as call:
            with patch("cloudlayer.planning.time.sleep") as sleep:
                self.assertEqual(cost_response(object(), progress=lambda _: None), b"{}")
                sleep.assert_called_once_with(1)
                self.assertEqual(call.call_count, 2)

    def test_long_cooldown_stops_without_retrying_early(self):
        failure = HTTPError("https://management.azure.com/test", 429, "throttled",
                            {"Retry-After": "120"}, None)
        with patch("cloudlayer.planning.urlopen", side_effect=failure) as call:
            with patch("cloudlayer.planning.time.sleep") as sleep:
                with self.assertRaises(BillingThrottled) as caught:
                    cost_response(object())
                self.assertEqual(caught.exception.retry_after_seconds, 120)
                sleep.assert_not_called()
                self.assertEqual(call.call_count, 1)

    def test_sdk_usage_with_nested_dict(self):
        item = SimpleNamespace(name={"value": "standardDSv2Family"}, current_value=0, limit=4, unit="Count")
        self.assertEqual(quota_summary(item)["limit"], 4)
        self.assertEqual(quota_summary(item)["current"], 0)

    def test_usage_object_and_rest_dict(self):
        obj = SimpleNamespace(name=SimpleNamespace(value="cores"), current_value=2, limit=8)
        rest = {"name": {"value": "cores"}, "currentValue": 2, "limit": 8}
        self.assertEqual(quota_summary(obj), quota_summary(rest))
        with self.assertRaises(ValueError):
            quota_summary({"name": {"value": "cores"}, "limit": 8})

    def test_linux_meter_does_not_select_windows_or_spot(self):
        base = {"type": "Consumption", "currencyCode": "THB", "armSkuName": "Standard_DS2_v2",
                "armRegionName": "centralindia", "unitOfMeasure": "1 Hour", "tierMinimumUnits": 0,
                "productName": "Virtual Machines DSv2 Series", "meterName": "DS2 v2",
                "skuName": "DS2 v2", "retailPrice": 5.6784}
        windows = {**base, "productName": "Virtual Machines DSv2 Series Windows", "retailPrice": 8.7696}
        spot = {**base, "meterName": "DS2 v2 Spot", "retailPrice": 1.2742}
        prices = {"region": "centralindia", "meters": [windows, spot, base]}
        self.assertEqual(select_linux_meter(prices), base)
        with self.assertRaises(ValueError):
            select_linux_meter({**prices, "meters": [base, base]})


if __name__ == "__main__":
    unittest.main()
