import json
import unittest
from unittest.mock import patch

from monitor_api import (
    ApiScrapeError,
    CartCheckoutRejected,
    _decode_page,
    _build_gap_product_candidates,
    _build_variant_seed_candidates,
    _build_variant_source_products,
    _verify_known_products_with_checkout,
    LISTING_SORT_EXPRESSIONS,
    add_cart_action_metadata,
    build_cart_cookie_value,
    build_cart_cookie_value_for_products,
    fetch_api_products,
    fetch_checkout_cart_stock_counts,
    fetch_verified_cart_product_count,
    fetch_known_products,
    fetch_variant_products,
    load_watchlist_ids,
    parse_cart_product_count,
    parse_checkout_cart_stock_count,
    parse_checkout_cart_stock_counts,
    parse_api_product,
    parse_detail_api_variant_candidates,
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
        self.assertNotIn("add_to_cart_link", product)

    def test_cart_cookie_value_for_products_batches_entries(self):
        products = [{"id": "123"}, {"id": "456"}]

        self.assertEqual(
            "NO^123^1^0*NO^456^1^0",
            build_cart_cookie_value_for_products(products),
        )

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

    def test_parse_detail_api_variant_candidates_reads_positive_hot_wheels_siblings(self):
        payload = {
            "PInfo": {
                "pid": 22597520,
                "pnm": "Hot Wheels Color Shifters Shark Hammer",
                "BID": 113,
            },
            "PColor": [
                {"pid": 22597520, "CS": 171, "Img": "22597520a.jpg;"},
                {"pid": 22597521, "CS": 1, "Img": "22597521a.jpg;"},
                {"pid": 22597522, "CS": 0, "Img": "22597522a.jpg;"},
            ],
        }

        candidates = parse_detail_api_variant_candidates(payload, "22597520")

        self.assertEqual({"22597520", "22597521"}, set(candidates))
        self.assertEqual(1, candidates["22597521"]["stock_count"])
        self.assertEqual(
            "https://cdn.fcglcdn.com/brainbees/images/products/219x265/22597521a.webp",
            candidates["22597521"]["image"],
        )

    def test_parse_detail_api_variant_candidates_accepts_hotwheels_without_space(self):
        payload = {
            "PInfo": {
                "pid": 23033008,
                "pnm": "Hotwheels 5 Diecast Free Wheel Toy Car Pack of 5",
                "BID": 113,
            },
            "PColor": [{"pid": 21348, "CS": 9, "Img": "21348a.jpg;"}],
        }

        candidates = parse_detail_api_variant_candidates(payload, "23033008")

        self.assertEqual(9, candidates["21348"]["stock_count"])

    def test_parse_detail_api_variant_candidates_ignores_other_brands(self):
        payload = {
            "PInfo": {"pid": 123, "pnm": "Other Brand Car", "BID": 999},
            "PColor": [{"pid": 456, "CS": 2, "Img": "456a.jpg;"}],
        }

        self.assertEqual({}, parse_detail_api_variant_candidates(payload, "123"))

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

    def test_parse_known_product_accepts_hotwheels_without_space_for_brand_113(self):
        payload = {
            "PInfo": {
                "pid": 21348,
                "pnm": "Hotwheels 5 Diecast Free Wheel Toy Car Pack of 5",
                "BID": 113,
                "CurSt": 9,
                "Img": "21348a.jpg;",
            },
            "PColor": [{"pid": 21348, "CS": 9}],
        }

        product = parse_known_product(payload, "21348")

        self.assertEqual("21348", product["id"])
        self.assertEqual(9, product["stock_count"])

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

    def test_parse_checkout_cart_stock_count_reads_matching_stock(self):
        html = (
            '<script>var cart_init = {"pOrderSummary":'
            '{"PurchaseOrderItemList":['
            '{"ProductID":"123","Quantity":1,"CurrentStock":2},'
            '{"ProductID":"456","Quantity":1,"CurrentStock":0}'
            "]}};</script>"
        )

        self.assertEqual(2, parse_checkout_cart_stock_count(html, "123"))

    def test_parse_checkout_cart_stock_counts_reads_multiple_products(self):
        html = (
            '<script>var cart_init = {"pOrderSummary":'
            '{"PurchaseOrderItemList":['
            '{"ProductID":"123","Quantity":1,"CurrentStock":2},'
            '{"ProductID":"456","Quantity":2,"CurrentStock":1}'
            "]}};</script>"
        )

        self.assertEqual(
            {"123": 2, "456": 0},
            parse_checkout_cart_stock_counts(html),
        )

    def test_parse_checkout_cart_stock_count_rejects_insufficient_stock(self):
        html = (
            '<script>var cart_init = {"pOrderSummary":'
            '{"PurchaseOrderItemList":['
            '{"ProductID":"123","Quantity":1,"CurrentStock":0}'
            "]}};</script>"
        )

        self.assertEqual(0, parse_checkout_cart_stock_count(html, "123"))

    def test_parse_checkout_cart_stock_count_rejects_undeliverable_stock(self):
        html = (
            '<script>var cart_init = {"pOrderSummary":'
            '{"PurchaseOrderItemList":['
            '{"ProductID":"123","Quantity":1,"CurrentStock":17,'
            '"IsServicable":0,"NoOfPinCodeToCheck":10,'
            '"isValidPincodeForDropShipment":false,"warehouseid":"0"}'
            "]}};</script>"
        )

        self.assertEqual(0, parse_checkout_cart_stock_count(html, "123"))

    def test_parse_checkout_cart_stock_count_reads_serviceable_stock(self):
        html = (
            '<script>var cart_init = {"pOrderSummary":'
            '{"PurchaseOrderItemList":['
            '{"ProductID":"123","Quantity":1,"CurrentStock":17,'
            '"IsServicable":17,"NoOfPinCodeToCheck":0,'
            '"isValidPincodeForDropShipment":false,"warehouseid":"10"}'
            "]}};</script>"
        )

        self.assertEqual(17, parse_checkout_cart_stock_count(html, "123"))

    def test_parse_checkout_cart_stock_count_rejects_unallocated_warehouse(self):
        html = (
            '<script>var cart_init = {"pOrderSummary":'
            '{"PurchaseOrderItemList":['
            '{"ProductID":"123","Quantity":1,"CurrentStock":17,'
            '"IsServicable":17,"NoOfPinCodeToCheck":0,'
            '"isValidPincodeForDropShipment":false,"warehouseid":"0"}'
            "]}};</script>"
        )

        self.assertEqual(0, parse_checkout_cart_stock_count(html, "123"))

    def test_parse_checkout_cart_stock_count_treats_missing_product_as_rejected(self):
        html = (
            '<script>var cart_init = {"pOrderSummary":'
            '{"PurchaseOrderItemList":['
            '{"ProductID":"456","Quantity":1,"CurrentStock":4}'
            "]}};</script>"
        )

        self.assertEqual(0, parse_checkout_cart_stock_count(html, "123"))

    def test_parse_checkout_cart_stock_count_rejects_missing_cart_data(self):
        with self.assertRaisesRegex(ApiScrapeError, "missing cart_init"):
            parse_checkout_cart_stock_count("<html></html>", "123")

    def test_fetch_verified_cart_product_count_rejects_stale_checkout_stock(self):
        class FakeResponse:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return self.body.encode("utf-8")

        calls = []

        def opener(request, timeout):
            calls.append((request.full_url, request.get_method()))
            if request.get_method() == "POST":
                return FakeResponse('{"GetCartProductCountResult":1}')
            return FakeResponse(
                '<script>var cart_init = {"pOrderSummary":'
                '{"PurchaseOrderItemList":['
                '{"ProductID":"123","Quantity":1,"CurrentStock":0}'
                "]}};</script>"
            )

        product = {
            "id": "123",
            "name": "Hot Wheels Hidden Car",
            "link": "https://www.firstcry.com/hot-wheels/hidden/123/product-detail",
        }

        with self.assertRaises(CartCheckoutRejected) as context:
            fetch_verified_cart_product_count(product, opener=opener)

        self.assertEqual(1, context.exception.cart_product_count)
        self.assertEqual(0, context.exception.checkout_stock_count)
        self.assertEqual(["POST", "GET"], [method for _, method in calls])

    def test_fetch_checkout_cart_stock_counts_sends_batched_cookie(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return (
                    '<script>var cart_init = {"pOrderSummary":'
                    '{"PurchaseOrderItemList":['
                    '{"ProductID":"123","Quantity":1,"CurrentStock":2},'
                    '{"ProductID":"456","Quantity":1,"CurrentStock":0}'
                    "]}};</script>"
                ).encode("utf-8")

        cookies = []

        def opener(request, timeout):
            cookies.append(request.get_header("Cookie"))
            return FakeResponse()

        products = [
            {
                "id": "123",
                "link": "https://www.firstcry.com/hot-wheels/a/123/product-detail",
            },
            {
                "id": "456",
                "link": "https://www.firstcry.com/hot-wheels/b/456/product-detail",
            },
        ]

        self.assertEqual(
            {"123": 2, "456": 0},
            fetch_checkout_cart_stock_counts(products, opener=opener),
        )
        self.assertEqual(
            "_$FC$_cookies_for_cart_v2_=NO^123^1^0*NO^456^1^0; "
            "globalPincode=575003; qwik_pincode=575003",
            cookies[0],
        )

    def test_verify_known_products_with_checkout_batches_cart_accepted_products(self):
        products = {
            "123": {
                "id": "123",
                "name": "Hot Wheels Available",
                "in_stock": True,
                "stock_count": 1,
                "cart_product_count": 1,
                "detail_stock_count": 0,
            },
            "456": {
                "id": "456",
                "name": "Hot Wheels Sold Out",
                "in_stock": True,
                "stock_count": 1,
                "cart_product_count": 1,
                "detail_stock_count": 0,
            },
        }

        batches = []

        def checkout_stock_fetcher(batch):
            batches.append([product["id"] for product in batch])
            return {"123": 2, "456": 0}

        verified = _verify_known_products_with_checkout(
            products,
            checkout_stock_fetcher=checkout_stock_fetcher,
        )

        self.assertEqual([["123", "456"]], batches)
        self.assertTrue(verified["123"]["in_stock"])
        self.assertEqual(2, verified["123"]["checkout_stock_count"])
        self.assertFalse(verified["456"]["in_stock"])
        self.assertTrue(verified["456"]["pending_cart"])
        self.assertEqual("known_product_checkout_rejected", verified["456"]["stock_signal"])


class ApiPaginationTests(unittest.TestCase):
    def test_default_listing_sorts_include_stock_relevant_firstcry_feeds(self):
        self.assertEqual(
            (
                "popularity",
                "NewArrivals",
                "BestSeller",
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

    def test_build_variant_source_products_uses_listing_variant_signals(self):
        raw_products = [
            {**make_raw_product("10000"), "ClrCnt": "1", "SzCnt": "0", "TTData": ""},
            {**make_raw_product("10001"), "ClrCnt": "2", "SzCnt": "0", "TTData": ""},
            {**make_raw_product("10002"), "ClrCnt": "1", "SzCnt": "1", "TTData": ""},
            {
                **make_raw_product("10003"),
                "ClrCnt": "1",
                "SzCnt": "0",
                "TTData": "10004|L 1 x B 1 x H 1 cm|FFFFFF|1",
            },
            {
                **make_raw_product("10005", stock="2"),
                "ClrCnt": "1",
                "SzCnt": "1",
                "TTData": "10005|L 1 x B 1 x H 1 cm|FFFFFF|1",
            },
        ]
        products = {
            raw_product["PId"]: parse_api_product(raw_product)
            for raw_product in raw_products
        }

        source_products = _build_variant_source_products(raw_products, products)

        self.assertEqual(["10001", "10002"], sorted(source_products))

    def test_build_variant_seed_candidates_reads_positive_ttdata_siblings(self):
        raw_products = [
            {
                **make_raw_product("10000"),
                "TTData": (
                    "10001|L 1 x B 1 x H 1 cm|FFFFFF|3,"
                    "10002|L 1 x B 1 x H 1 cm|FFFFFF|0"
                ),
            },
            {
                **make_raw_product("10003", stock="2"),
                "TTData": "10003|L 1 x B 1 x H 1 cm|FFFFFF|5",
            },
        ]
        products = {
            raw_product["PId"]: parse_api_product(raw_product)
            for raw_product in raw_products
        }

        candidates = _build_variant_seed_candidates(raw_products, products)

        self.assertEqual(["10001"], sorted(candidates))
        self.assertEqual(3, candidates["10001"]["stock_count"])

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

    def test_fetch_api_products_adds_variant_products_before_verification(self):
        def page_fetcher(page_number):
            return make_page(
                [
                    {
                        **make_raw_product("10", stock="0"),
                        "ClrCnt": "2",
                    }
                ],
                expected_products=1,
            )

        def variant_product_fetcher(products, source_products, seed_candidates):
            self.assertEqual(["10"], sorted(source_products))
            self.assertEqual({}, seed_candidates)
            return {
                "11": {
                    "id": "11",
                    "name": "Hot Wheels Hidden Variant",
                    "in_stock": True,
                    "stock_count": 2,
                    "detail_stock_count": 2,
                    "link": "https://www.firstcry.com/hot-wheels/hidden/11/product-detail",
                    "image": "",
                    "stock_signal": "variant_product_api",
                }
            }

        def detail_verifier(products):
            self.assertIn("11", products)
            return verify_in_stock_products(
                products,
                detail_fetcher=lambda product: 2 if product["id"] == "11" else 0,
                cart_fetcher=lambda product: 1 if product["id"] == "11" else 0,
            )

        products, result = fetch_api_products(
            page_fetcher=page_fetcher,
            detail_verifier=detail_verifier,
            variant_product_fetcher=variant_product_fetcher,
        )

        self.assertEqual(2, result.unique_products)
        self.assertTrue(products["11"]["in_stock"])
        self.assertEqual("cart_product_count", products["11"]["stock_signal"])

    def test_fetch_variant_products_discovers_missing_positive_sibling(self):
        products = {
            "10": {
                "id": "10",
                "name": "Hot Wheels Visible Source",
                "in_stock": True,
                "stock_count": 4,
                "link": "https://www.firstcry.com/hot-wheels/source/10/product-detail",
                "image": "",
            }
        }

        def source_fetcher(product):
            self.assertEqual("10", product["id"])
            return {
                "10": {"id": "10", "stock_count": 4, "image": ""},
                "11": {"id": "11", "stock_count": 2, "image": "variant.webp"},
            }

        def product_fetcher(product_id):
            self.assertEqual("11", product_id)
            return {
                "id": "11",
                "name": "Hot Wheels Hidden Variant",
                "in_stock": True,
                "stock_count": 2,
                "detail_stock_count": 2,
                "link": "https://www.firstcry.com/hot-wheels/hidden/11/product-detail",
                "image": "",
                "stock_signal": "known_product_api",
            }

        discovered_products = fetch_variant_products(
            products,
            source_fetcher=source_fetcher,
            product_fetcher=product_fetcher,
        )

        self.assertEqual(["11"], list(discovered_products))
        self.assertEqual("variant_product_api", discovered_products["11"]["stock_signal"])
        self.assertEqual("variant.webp", discovered_products["11"]["image"])

    def test_fetch_variant_products_marks_existing_oos_sibling_for_verification(self):
        products = {
            "10": {
                "id": "10",
                "name": "Hot Wheels Visible Source",
                "in_stock": False,
                "stock_count": 0,
                "link": "https://www.firstcry.com/hot-wheels/source/10/product-detail",
                "image": "",
            }
        }

        discovered_products = fetch_variant_products(
            products,
            source_fetcher=lambda product: {
                "10": {"id": "10", "stock_count": 3, "image": "10.webp"}
            },
            product_fetcher=lambda product_id: self.fail(
                "existing product metadata should be reused"
            ),
        )

        self.assertEqual(["10"], list(discovered_products))
        self.assertTrue(discovered_products["10"]["in_stock"])
        self.assertEqual(3, discovered_products["10"]["detail_stock_count"])
        self.assertEqual("variant_product_api", discovered_products["10"]["stock_signal"])

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

    def test_fetch_known_products_marks_checkout_rejected_cart_signal_not_live(self):
        def product_fetcher(product_id):
            return {
                "id": product_id,
                "name": "Hot Wheels Fast Sellout",
                "in_stock": False,
                "stock_count": 0,
                "detail_stock_count": 0,
                "link": f"https://www.firstcry.com/hot-wheels/sellout/{product_id}/product-detail",
                "image": "",
                "stock_signal": "known_product_api",
            }

        def cart_fetcher(product):
            raise CartCheckoutRejected(product, 1, 0)

        probed_products = fetch_known_products(
            {},
            known_products={},
            watchlist_ids={"99"},
            product_fetcher=product_fetcher,
            cart_fetcher=cart_fetcher,
        )

        self.assertEqual(["99"], list(probed_products))
        self.assertFalse(probed_products["99"]["in_stock"])
        self.assertTrue(probed_products["99"]["pending_cart"])
        self.assertEqual(1, probed_products["99"]["cart_product_count"])
        self.assertEqual(0, probed_products["99"]["checkout_stock_count"])
        self.assertEqual(
            "known_product_checkout_rejected",
            probed_products["99"]["stock_signal"],
        )

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

    def test_fetch_api_products_marks_checkout_rejected_listing_stock_pending(self):
        def page_fetcher(page_number):
            return make_page([make_raw_product("1", stock="5")], expected_products=1)

        def detail_verifier(products):
            def cart_fetcher(product):
                raise CartCheckoutRejected(product, 1, 0)

            return verify_in_stock_products(
                products,
                detail_fetcher=lambda product: 1,
                cart_fetcher=cart_fetcher,
            )

        products, _ = fetch_api_products(
            page_fetcher=page_fetcher,
            detail_verifier=detail_verifier,
        )

        self.assertFalse(products["1"]["in_stock"])
        self.assertTrue(products["1"]["pending_cart"])
        self.assertEqual(1, products["1"]["cart_product_count"])
        self.assertEqual(0, products["1"]["checkout_stock_count"])
        self.assertEqual("checkout_rejected", products["1"]["stock_signal"])


if __name__ == "__main__":
    unittest.main()
