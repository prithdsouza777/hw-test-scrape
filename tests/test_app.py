import unittest

import app as app_module
from product_tracker import ProductTracker


class ApiDashboardTests(unittest.TestCase):
    def setUp(self):
        self.original_tracker = app_module.tracker
        self.original_updated = app_module.last_updated
        self.original_error = app_module.last_error
        self.original_ttl = app_module.last_ttl_seconds
        self.original_catalog_count = app_module.catalog_count
        self.original_scraping = app_module.is_scraping

        app_module.tracker = ProductTracker()
        app_module.tracker.update(
            {
                "1": {
                    "id": "1",
                    "name": "Hot Wheels Test Car",
                    "in_stock": True,
                    "stock_count": 3,
                    "link": "https://www.firstcry.com/hot-wheels/test-car/1/product-detail",
                    "image": "",
                },
                "2": {
                    "id": "2",
                    "name": "Hot Wheels Pending Car",
                    "in_stock": False,
                    "pending_cart": True,
                    "stock_count": 0,
                    "detail_stock_count": 1,
                    "cart_product_count": 0,
                    "link": "https://www.firstcry.com/hot-wheels/test-car/2/product-detail",
                    "image": "",
                }
            }
        )
        app_module.last_updated = "2026-05-31 12:30:00"
        app_module.last_error = None
        app_module.last_ttl_seconds = 120
        app_module.catalog_count = 276
        app_module.is_scraping = False
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.tracker = self.original_tracker
        app_module.last_updated = self.original_updated
        app_module.last_error = self.original_error
        app_module.last_ttl_seconds = self.original_ttl
        app_module.catalog_count = self.original_catalog_count
        app_module.is_scraping = self.original_scraping

    def test_api_dashboard_exposes_source_and_listing_ttl(self):
        response = self.client.get("/api/data")
        payload = response.get_json()

        self.assertEqual(200, response.status_code)
        self.assertEqual("firstcry_listing_api", payload["source"])
        self.assertEqual(276, payload["catalog_count"])
        self.assertEqual(120, payload["listing_ttl_seconds"])
        self.assertEqual(3, payload["products"]["1"]["stock_count"])
        self.assertEqual(1, payload["pending_count"])
        self.assertEqual(0, payload["pending_products"]["2"]["cart_product_count"])


if __name__ == "__main__":
    unittest.main()
