import json
import unittest
from unittest.mock import patch

from monitor_api import (
    ApiScrapeError,
    _decode_page,
    _build_gap_product_candidates,
    LISTING_SORT_EXPRESSIONS,
    add_cart_action_metadata,
    build_auto_add_link,
    build_cart_cookie_value,
    fetch_api_products,
    fetch_known_products,
    load_watchlist_ids,
    parse_cart_product_count,
    parse_api_product,
    parse_detail_api_stock_count,
    parse_detail_stock_count,
    parse_gap_product,
    parse_known_product,
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
    def test_cart_action_metadata_uses_firstcry_cart_cookie_format(self):
        product = add_cart_action_metadata(
            {
                "id": "22928008",
                "name": "Bone Shaker",
                "link": (
                    "https://www.firstcry.com/hot-wheels/bone-shaker/"
                    "22928008/product-detail"
                ),
            }
        )

        self.assertEqual("NO^22928008^1^0", build_cart_cookie_value("22928008"))
        self.assertEqual("NO^22928008^1^0", product["cart_cookie"])
        self.assertEqual("_$FC$_cookies_for_cart_v2_", product["cart_cookie_name"])
        self.assertEqual("https://checkout.firstcry.com/pay", product["cart_url"])
        self.assertIn("hw_auto_add=1", product["add_to_cart_link"])
        self.assertIn("hw_checkout=1", product["add_to_cart_link"])
        self.assertIn("hw_pid=22928008", product["add_to_cart_link"])

    def test_build_auto_add_link_preserves_existing_query_parameters(self):
        link = build_auto_add_link(
            {
                "id": "23074890",
                "link": (
                    "https://www.firstcry.com/hot-wheels/quick-chat/"
                    "23074890/product-detail?ref2=dashboard"
                ),
            }
        )

        self.assertIn("ref2=dashboard", link)
        self.assertIn("hw_auto_add=1", link)
        self.assertIn("hw_checkout=1", link)
        self.assertIn("hw_pid=23074890", link)
        self.assertIn("#hw_auto_add=1", link)

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

    def test_parse_detail_api_stock_count_reads_current_product_stock(self):
        payload = {
            "PInfo": {"pid": 123, "CurSt": 0},
            "PColor": [{"pid": 123, "CS": 3, "pn": "Car"}],
        }

        self.assertEqual(3, parse_detail_api_stock_count(payload, "123"))

    def test_parse_detail_api_stock_count_uses_matching_product_info_fallback(self):
        payload = {
            "PInfo": {"pid": 123, "CurSt": 2},
            "PColor": [{"pid": 456, "CS": 5, "pn": "Other Car"}],
        }

        self.assertEqual(2, parse_detail_api_stock_count(payload, "123"))

    def test_parse_detail_api_stock_count_rejects_mismatched_product_data(self):
        payload = {
            "PInfo": {"pid": 456, "CurSt": 2},
            "PColor": [{"pid": 789, "CS": 5, "pn": "Other Car"}],
        }

        with self.assertRaisesRegex(ApiScrapeError, "mismatched product data"):
            parse_detail_api_stock_count(payload, "123")

    def test_parse_detail_stock_count_accepts_direct_product_api_json(self):
        payload = json.dumps(
            {
                "PInfo": {"pid": 123, "CurSt": 0},
                "PColor": [{"pid": 123, "CS": 4, "pn": "Car"}],
            }
        )

        self.assertEqual(4, parse_detail_stock_count(payload, "123"))

    def test_parse_gap_product_accepts_hot_wheels_stock(self):
        payload = {
            "PInfo": {
                "pid": 123,
                "pnm": "Hot Wheels Hidden Car - Blue",
                "BID": 113,
                "CurSt": 2,
                "Img": "123a.jpg;123b.jpg;",
            },
            "PColor": [{"pid": 123, "CS": 2}],
        }

        product = parse_gap_product(payload, "123")

        self.assertEqual("123", product["id"])
        self.assertEqual(2, product["stock_count"])
        self.assertTrue(product["in_stock"])
        self.assertEqual("gap_product_api", product["stock_signal"])
        self.assertEqual(
            "https://cdn.fcglcdn.com/brainbees/images/products/219x265/123a.webp",
            product["image"],
        )

    def test_parse_gap_product_ignores_non_hot_wheels_products(self):
        payload = {
            "PInfo": {"pid": 123, "pnm": "Other Brand Car", "BID": 999, "CurSt": 2},
            "PColor": [{"pid": 123, "CS": 2}],
        }

        self.assertIsNone(parse_gap_product(payload, "123"))

    def test_parse_known_product_keeps_out_of_stock_metadata_for_cart_probe(self):
        payload = {
            "PInfo": {
                "pid": 123,
                "pnm": "Hot Wheels Hidden Car - Blue",
                "BID": 113,
                "CurSt": 0,
                "Img": "123a.jpg;",
            },
            "PColor": [{"pid": 123, "CS": 0}],
        }

        product = parse_known_product(payload, "123")

        self.assertEqual("123", product["id"])
        self.assertFalse(product["in_stock"])
        self.assertEqual(0, product["stock_count"])
        self.assertEqual("known_product_api", product["stock_signal"])

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
    def test_default_listing_sorts_include_stock_relevant_firstcry_feeds(self):
        self.assertEqual(
            (
                "popularity",
                "NewArrivals",
                "HighestDiscount",
                "Rating",
            ),
            LISTING_SORT_EXPRESSIONS,
        )

    def test_build_gap_product_candidates_scans_small_missing_id_gaps(self):
        products = {
            "100": {"id": "100"},
            "103": {"id": "103"},
            "130": {"id": "130"},
            "abc": {"id": "abc"},
        }

        self.assertEqual(
            ("101", "102"),
            _build_gap_product_candidates(products),
        )

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

    def test_fetch_api_products_merges_multiple_listing_sorts(self):
        calls = []

        def page_fetcher(page_number, sort_expression=None):
            calls.append((sort_expression, page_number))
            if sort_expression == "popularity":
                return make_page(
                    [make_raw_product("1", stock="0")],
                    expected_products=1,
                    ttl_seconds=120,
                )
            return make_page(
                [
                    make_raw_product("1", stock="5"),
                    make_raw_product("2", stock="3"),
                ],
                expected_products=2,
                ttl_seconds=90,
            )

        products, result = fetch_api_products(
            page_fetcher=page_fetcher,
            detail_verifier=None,
            sort_expressions=("popularity", "newarrivals"),
        )

        self.assertEqual([("popularity", 1), ("newarrivals", 1)], calls)
        self.assertEqual(3, result.raw_products)
        self.assertEqual(2, result.unique_products)
        self.assertEqual(2, result.expected_products)
        self.assertEqual(90, result.ttl_seconds)
        self.assertEqual(("popularity", "newarrivals"), result.sort_expressions)
        self.assertEqual(5, products["1"]["stock_count"])
        self.assertTrue(products["1"]["in_stock"])
        self.assertEqual(3, products["2"]["stock_count"])

    def test_fetch_api_products_adds_gap_products_before_verification(self):
        def page_fetcher(page_number):
            return make_page(
                [
                    make_raw_product("10", stock="0"),
                    make_raw_product("13", stock="0"),
                ],
                expected_products=2,
            )

        def gap_product_fetcher(products):
            self.assertEqual(["10", "13"], sorted(products))
            return {
                "11": {
                    "id": "11",
                    "name": "Hot Wheels Hidden Product",
                    "in_stock": True,
                    "stock_count": 2,
                    "link": "https://www.firstcry.com/hot-wheels/hidden/11/product-detail",
                    "image": "",
                    "stock_signal": "gap_product_api",
                }
            }

        products, result = fetch_api_products(
            page_fetcher=page_fetcher,
            detail_verifier=None,
            gap_product_fetcher=gap_product_fetcher,
        )

        self.assertEqual(3, result.unique_products)
        self.assertEqual(2, products["11"]["stock_count"])
        self.assertTrue(products["11"]["in_stock"])

    def test_fetch_known_products_cart_probes_current_out_of_stock_products(self):
        products = {
            "11": {
                "id": "11",
                "name": "Hot Wheels Hidden Product",
                "in_stock": False,
                "stock_count": 0,
                "link": "https://www.firstcry.com/hot-wheels/hidden/11/product-detail",
                "image": "",
            },
            "12": {
                "id": "12",
                "name": "Hot Wheels Already In Stock",
                "in_stock": True,
                "stock_count": 2,
                "link": "https://www.firstcry.com/hot-wheels/visible/12/product-detail",
                "image": "",
            },
        }

        probed_products = fetch_known_products(
            products,
            known_products={},
            watchlist_ids=set(),
            product_fetcher=lambda product_id: self.fail("metadata should already exist"),
            cart_fetcher=lambda product: 1 if product["id"] == "11" else 0,
        )

        self.assertEqual(["11"], list(probed_products))
        self.assertTrue(probed_products["11"]["in_stock"])
        self.assertEqual(1, probed_products["11"]["cart_product_count"])
        self.assertEqual("known_product_cart_count", probed_products["11"]["stock_signal"])

    def test_fetch_known_products_uses_watchlist_ids(self):
        def product_fetcher(product_id):
            return {
                "id": product_id,
                "name": "Hot Wheels Old Order Product",
                "in_stock": False,
                "stock_count": 0,
                "detail_stock_count": 0,
                "link": f"https://www.firstcry.com/hot-wheels/old/{product_id}/product-detail",
                "image": "",
                "stock_signal": "known_product_api",
            }

        probed_products = fetch_known_products(
            {},
            known_products={},
            watchlist_ids={"99"},
            product_fetcher=product_fetcher,
            cart_fetcher=lambda product: 1,
        )

        self.assertEqual(["99"], list(probed_products))
        self.assertEqual("Hot Wheels Old Order Product", probed_products["99"]["name"])
        self.assertEqual("known_product_cart_count", probed_products["99"]["stock_signal"])

    def test_load_watchlist_ids_reads_product_urls_and_plain_ids(self):
        class FakePath:
            def exists(self):
                return True

            def read_text(self, encoding):
                return (
                    "https://www.firstcry.com/hot-wheels/car/12345/product-detail\n"
                    "67890\n"
                )

        self.assertEqual({"12345", "67890"}, load_watchlist_ids(FakePath()))

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
            "product_api_current_stock",
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
