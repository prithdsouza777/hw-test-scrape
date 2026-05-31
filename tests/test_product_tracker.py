import unittest
from datetime import datetime

from product_tracker import ProductTracker


NOW = datetime(2026, 5, 31, 12, 30, 0)


def make_product(product_id, in_stock=True):
    return {
        "id": product_id,
        "name": f"Hot Wheels {product_id}",
        "in_stock": in_stock,
        "link": f"https://www.firstcry.com/hot-wheels/test/{product_id}/product-detail",
        "image": f"https://cdn.fcglcdn.com/products/{product_id}.webp",
    }


class ProductTrackerTests(unittest.TestCase):
    def test_missing_confirmation_count_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "at least 1"):
            ProductTracker(missing_confirmation_snapshots=0)

    def test_initial_snapshot_does_not_alert(self):
        tracker = ProductTracker()

        events = tracker.update({"1": make_product("1")}, now=NOW)

        self.assertEqual([], events)
        self.assertEqual(1, tracker.snapshot()["total_count"])

    def test_new_in_stock_product_alerts_after_initial_snapshot(self):
        tracker = ProductTracker()
        tracker.update({"1": make_product("1")}, now=NOW)

        events = tracker.update(
            {"1": make_product("1"), "2": make_product("2")},
            now=NOW,
        )

        self.assertEqual(["NEW"], [event["type"] for event in events])
        self.assertEqual("2", tracker.monitored_products[0]["id"])

    def test_missing_product_alerts_as_restock_when_it_returns(self):
        tracker = ProductTracker()
        tracker.update({"1": make_product("1"), "2": make_product("2", False)}, now=NOW)
        tracker.update({"2": make_product("2", False)}, now=NOW)
        tracker.update({"2": make_product("2", False)}, now=NOW)

        events = tracker.update(
            {"1": make_product("1"), "2": make_product("2", False)},
            now=NOW,
        )

        self.assertEqual(["STOCK"], [event["type"] for event in events])
        self.assertEqual("1", tracker.monitored_products[0]["id"])

    def test_transient_missing_product_does_not_alert_when_it_returns(self):
        tracker = ProductTracker()
        tracker.update({"1": make_product("1"), "2": make_product("2", False)}, now=NOW)
        tracker.update({"2": make_product("2", False)}, now=NOW)

        events = tracker.update(
            {"1": make_product("1"), "2": make_product("2", False)},
            now=NOW,
        )

        self.assertEqual([], events)

    def test_empty_snapshot_is_rejected_without_losing_state(self):
        tracker = ProductTracker()
        tracker.update({"1": make_product("1")}, now=NOW)

        with self.assertRaisesRegex(ValueError, "empty snapshot"):
            tracker.update({}, now=NOW)

        self.assertEqual(["1"], list(tracker.current_products))

    def test_snapshot_returns_a_copy(self):
        tracker = ProductTracker()
        tracker.update({"1": make_product("1")}, now=NOW)

        snapshot = tracker.snapshot()
        snapshot["products"]["1"]["name"] = "Modified"

        self.assertEqual("Hot Wheels 1", tracker.current_products["1"]["name"])

    def test_snapshot_exposes_cart_pending_products_separately(self):
        tracker = ProductTracker()
        pending = make_product("2", in_stock=False)
        pending["pending_cart"] = True

        tracker.update(
            {
                "1": make_product("1"),
                "2": pending,
                "3": make_product("3", in_stock=False),
            },
            now=NOW,
        )

        snapshot = tracker.snapshot()

        self.assertEqual(["1"], list(snapshot["products"]))
        self.assertEqual(["2"], list(snapshot["pending_products"]))
        self.assertEqual(1, snapshot["pending_count"])


if __name__ == "__main__":
    unittest.main()
