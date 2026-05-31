import unittest
from unittest.mock import patch

import app as app_module
from product_tracker import ProductTracker


class FakeSwitchTo:
    def __init__(self, driver):
        self.driver = driver

    def new_window(self, kind):
        self.driver.opened_new_tab = kind == "tab"
        self.driver.window_handles.append("new-tab")


class FakeDriver:
    def __init__(self, current_url, handles):
        self.current_url = current_url
        self.window_handles = list(handles)
        self.opened_new_tab = False
        self.switch_to = FakeSwitchTo(self)


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
        self.assertEqual("NO^1^1^0", payload["products"]["1"]["cart_cookie"])
        self.assertEqual(
            "_$FC$_cookies_for_cart_v2_",
            payload["products"]["1"]["cart_cookie_name"],
        )
        self.assertEqual(
            "https://www.firstcry.com/cart",
            payload["products"]["1"]["cart_url"],
        )
        self.assertEqual(1, payload["pending_count"])
        self.assertEqual(0, payload["pending_products"]["2"]["cart_product_count"])
        self.assertEqual("NO^2^1^0", payload["pending_products"]["2"]["cart_cookie"])

    def test_dashboard_uses_cart_acceptance_language_and_action(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(200, response.status_code)
        self.assertIn("Hot Wheels Monitor", html)
        self.assertIn("Cart Accepted", html)
        self.assertIn("ADD TO CART", html)
        self.assertNotIn("OPEN PRODUCT", html)

    def test_add_to_cart_opens_cart_browser_for_buyable_product(self):
        with patch.object(
            app_module,
            "add_product_to_firstcry_cart",
            return_value="NO^1^1^0",
        ) as add_to_cart:
            response = self.client.post("/api/add-to-cart/1")

        payload = response.get_json()
        self.assertEqual(200, response.status_code)
        self.assertTrue(payload["ok"])
        self.assertEqual("NO^1^1^0", payload["cart_cookie"])
        add_to_cart.assert_called_once()

    def test_add_to_cart_rejects_non_buyable_product(self):
        response = self.client.post("/api/add-to-cart/2")
        payload = response.get_json()

        self.assertEqual(409, response.status_code)
        self.assertFalse(payload["ok"])

    def test_open_new_cart_tab_reuses_initial_blank_tab(self):
        driver = FakeDriver(current_url="data:,", handles=["initial"])

        app_module._open_new_cart_tab(driver)

        self.assertFalse(driver.opened_new_tab)

    def test_open_new_cart_tab_opens_tab_after_first_use(self):
        driver = FakeDriver(current_url="https://www.firstcry.com/cart", handles=["cart"])

        app_module._open_new_cart_tab(driver)

        self.assertTrue(driver.opened_new_tab)


if __name__ == "__main__":
    unittest.main()
