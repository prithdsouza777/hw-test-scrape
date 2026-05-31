import json
import unittest
from unittest.mock import patch

from monitor_api import (
    ApiScrapeError,
    _decode_page,
    fetch_api_products,
    parse_cart_product_count,
    parse_api_product,
    parse_detail_stock_count,
    verify_in_stock_products,
)


def make_raw_product(product_id, stock="0", name=None):
    return {
        "PId": str(product_id),
        "PNm": name or f"Hot Wheels Product {product_id}",
        "CrntStock": stock,
        "Images": f"{product_id}a.jpg;{product_id}b.jpg;",
    }


def make_page(products, expected_products, ttl_seconds=120):
    return {
        "products": products,
        "expected_products": expected_products,
        "ttl_seconds": ttl_seconds,
    }


class ApiProductParsingTests(unittest.TestCase):
    def test_parse_api_product_uses_current_stock_quantity(self):
        product = parse_api_product(
            make_raw_product("123", stock="4", name="Hot Wheels Red & Blue Car")
        )

        self.assertEqual("123", product["id"])
        self.assertEqual(4, product["stock_count"])
        self.assertTrue(product["in_stock"])
        self.assertEqual(
            "https://www.firstcry.com/hot-wheels/hot-wheels-red-and-blue-car/"
            "123/product-detail",
            product["link"],
        )
        self.assertEqual(
            "https://cdn.fcglcdn.com/brainbees/images/products/219x265/123a.webp",
            product["image"],
        )

    def test_parse_api_product_treats_invalid_or_negative_stock_as_zero(self):
        invalid = parse_api_product(make_raw_product("123", stock="unknown"))
        negative = parse_api_product(make_raw_product("124", stock="-2"))

        self.assertEqual(0, invalid["stock_count"])
        self.assertFalse(invalid["in_stock"])
        self.assertEqual(0, negative["stock_count"])
        self.assertFalse(negative["in_stock"])

    def test_parse_api_product_rejects_missing_identity(self):
        with self.assertRaisesRegex(ApiScrapeError, "without an ID or name"):
            parse_api_product({"PId": "", "PNm": ""})

    def test_decode_page_handles_nested_json_response(self):
        payload = json.dumps(
            {
                "ProductResponse": json.dumps(
                    {"Products": [make_raw_product("123")], "Count": [1]}
                ),
                "TTL": 90,
            }
        )

        page = _decode_page(payload)

        self.assertEqual(1, page["expected_products"])
        self.assertEqual(90, page["ttl_seconds"])
        self.assertEqual("123", page["products"][0]["PId"])

    def test_decode_page_allows_later_page_without_catalog_count(self):
        payload = json.dumps(
            {
                "ProductResponse": json.dumps(
                    {"Products": [make_raw_product("123")]}
                ),
                "TTL": 90,
            }
        )

        page = _decode_page(payload)

        self.assertIsNone(page["expected_products"])

    def test_parse_detail_stock_count_reads_current_product_stock(self):
        html = (
            '<script>var CurrentProductDetailJSON={"123":{"CS":2,"pn":"Car"}},'
            'ProductDetailJSON={"PInfo":{"pid":123,"CurSt":0,"pnm":"Car"}};'
            "</script>"
        )

        self.assertEqual(2, parse_detail_stock_count(html, "123"))

    def test_parse_detail_stock_count_does_not_trust_stale_curst(self):
        html = (
            '<script>var CurrentProductDetailJSON={"123":{"CS":0,"pn":"Car"}},'
            'ProductDetailJSON={"PInfo":{"pid":123,"CurSt":5,"pnm":"Car"}};'
            "</script>"
        )

        self.assertEqual(0, parse_detail_stock_count(html, "123"))

    def test_parse_detail_stock_count_rejects_missing_detail_json(self):
        with self.assertRaisesRegex(ApiScrapeError, "missing CurrentProductDetailJSON"):
            parse_detail_stock_count("<html></html>", "123")

    def test_parse_cart_product_count_reads_count_result(self):
        self.assertEqual(
            1,
            parse_cart_product_count('{"GetCartProductCountResult":1}'),
        )

    def test_parse_cart_product_count_rejects_unexpected_response(self):
        with self.assertRaisesRegex(ApiScrapeError, "unexpected stock data"):
            parse_cart_product_count("{}")


class ApiPaginationTests(unittest.TestCase):
    def test_fetch_api_products_reads_all_pages_and_deduplicates_variants(self):
        calls = []

        def page_fetcher(page_number):
            calls.append(page_number)
            if page_number == 1:
                return make_page(
                    [make_raw_product(str(index), stock="1") for index in range(1, 21)],
                    expected_products=22,
                    ttl_seconds=120,
                )
            return make_page(
                [make_raw_product("20", stock="2"), make_raw_product("21", stock="0")],
                expected_products=22,
                ttl_seconds=110,
            )

        products, result = fetch_api_products(
            page_fetcher=page_fetcher,
            detail_verifier=None,
        )

        self.assertEqual([1, 2], calls)
        self.assertEqual(22, result.raw_products)
        self.assertEqual(21, result.unique_products)
        self.assertEqual(110, result.ttl_seconds)
        self.assertEqual(2, products["20"]["stock_count"])
        self.assertFalse(products["21"]["in_stock"])

    def test_fetch_api_products_rejects_incomplete_snapshot(self):
        def page_fetcher(page_number):
            return make_page([make_raw_product("1")], expected_products=21)

        with self.assertRaisesRegex(ApiScrapeError, "incomplete snapshot"):
            fetch_api_products(page_fetcher=page_fetcher, detail_verifier=None)

    def test_fetch_api_products_allows_near_complete_snapshot(self):
        def page_fetcher(page_number):
            if page_number == 1:
                return make_page(
                    [make_raw_product(str(index), stock="1") for index in range(20)],
                    expected_products=21,
                )
            return make_page([], expected_products=21)

        products, result = fetch_api_products(
            page_fetcher=page_fetcher,
            detail_verifier=None,
        )

        self.assertEqual(20, result.raw_products)
        self.assertEqual(20, len(products))

    def test_fetch_api_products_rejects_missing_first_page_count(self):
        def page_fetcher(page_number):
            return make_page([make_raw_product("1")], expected_products=None)

        with self.assertRaisesRegex(ApiScrapeError, "missing its product count"):
            fetch_api_products(page_fetcher=page_fetcher, detail_verifier=None)

    def test_fetch_api_products_rejects_count_change_mid_scrape(self):
        def page_fetcher(page_number):
            count = 21 if page_number == 1 else 22
            return make_page([make_raw_product(str(page_number))], expected_products=count)

        with self.assertRaisesRegex(ApiScrapeError, "changed mid-scrape"):
            fetch_api_products(page_fetcher=page_fetcher, detail_verifier=None)

    @patch("monitor_api.MAX_PAGES", 1)
    def test_fetch_api_products_honors_page_safety_limit(self):
        def page_fetcher(page_number):
            return make_page([make_raw_product("1")], expected_products=21)

        with self.assertRaisesRegex(ApiScrapeError, "configured maximum"):
            fetch_api_products(page_fetcher=page_fetcher, detail_verifier=None)

    def test_fetch_api_products_can_confirm_listing_stock_with_detail_page(self):
        def page_fetcher(page_number):
            return make_page(
                [
                    make_raw_product("1", stock="5"),
                    make_raw_product("2", stock="4"),
                    make_raw_product("3", stock="0"),
                ],
                expected_products=3,
            )

        def detail_verifier(products):
            return verify_in_stock_products(
                products,
                detail_fetcher=lambda product: 0 if product["id"] == "1" else 2,
                cart_fetcher=None,
            )

        products, _ = fetch_api_products(
            page_fetcher=page_fetcher,
            detail_verifier=detail_verifier,
        )

        self.assertFalse(products["1"]["in_stock"])
        self.assertEqual(0, products["1"]["stock_count"])
        self.assertEqual(0, products["1"]["detail_stock_count"])
        self.assertEqual(
            "detail_page_current_product_cs",
            products["1"]["stock_signal"],
        )
        self.assertTrue(products["2"]["in_stock"])
        self.assertEqual(2, products["2"]["stock_count"])
        self.assertEqual(2, products["2"]["detail_stock_count"])
        self.assertFalse(products["3"]["in_stock"])

    def test_fetch_api_products_can_confirm_stock_with_cart_api(self):
        def page_fetcher(page_number):
            return make_page(
                [
                    make_raw_product("1", stock="5"),
                    make_raw_product("2", stock="4"),
                ],
                expected_products=2,
            )

        def detail_verifier(products):
            return verify_in_stock_products(
                products,
                detail_fetcher=lambda product: 1,
                cart_fetcher=lambda product: 0 if product["id"] == "1" else 1,
            )

        products, _ = fetch_api_products(
            page_fetcher=page_fetcher,
            detail_verifier=detail_verifier,
        )

        self.assertFalse(products["1"]["in_stock"])
        self.assertEqual(0, products["1"]["stock_count"])
        self.assertEqual(0, products["1"]["cart_product_count"])
        self.assertTrue(products["1"]["pending_cart"])
        self.assertEqual("cart_pending", products["1"]["stock_signal"])
        self.assertTrue(products["2"]["in_stock"])
        self.assertEqual(1, products["2"]["cart_product_count"])
        self.assertEqual("cart_product_count", products["2"]["stock_signal"])


if __name__ == "__main__":
    unittest.main()
