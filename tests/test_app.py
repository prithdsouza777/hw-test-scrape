import unittest

import app as app_module
from product_tracker import ProductTracker


def make_product(product_id, in_stock=True):
    return {
        "id": product_id,
        "name": f"Hot Wheels {product_id}",
        "in_stock": in_stock,
        "link": f"https://www.firstcry.com/hot-wheels/test/{product_id}/product-detail",
        "image": "",
    }


class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.original_tracker = app_module.tracker
        self.original_updated = app_module.last_updated
        self.original_error = app_module.last_error
        self.original_scraping = app_module.is_scraping

        app_module.tracker = ProductTracker()
        app_module.tracker.update(
            {"1": make_product("1"), "2": make_product("2", False)}
        )
        app_module.last_updated = "2026-05-31 12:30:00"
        app_module.last_error = "temporary failure"
        app_module.is_scraping = False
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.tracker = self.original_tracker
        app_module.last_updated = self.original_updated
        app_module.last_error = self.original_error
        app_module.is_scraping = self.original_scraping

    def test_api_exposes_last_good_in_stock_snapshot_and_error(self):
        response = self.client.get("/api/data")
        payload = response.get_json()

        self.assertEqual(200, response.status_code)
        self.assertEqual(["1"], list(payload["products"]))
        self.assertEqual(1, payload["total_count"])
        self.assertEqual("temporary failure", payload["last_error"])
        self.assertEqual("2026-05-31 12:30:00", payload["last_updated"])

    def test_dashboard_contains_visible_error_target(self):
        response = self.client.get("/")

        self.assertEqual(200, response.status_code)
        self.assertIn(b'id="scrape-error"', response.data)


if __name__ == "__main__":
    unittest.main()
