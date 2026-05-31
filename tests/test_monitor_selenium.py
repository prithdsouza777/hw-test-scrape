import unittest
from unittest.mock import patch

from monitor_selenium import (
    ScrapeError,
    ScrollResult,
    parse_catalog_count,
    parse_page,
    scrape_products,
    scroll_to_bottom,
)


class FakeElement:
    def __init__(self, text=""):
        self.text = text


class FakeScrollDriver:
    def __init__(self, states, expected_cards=3, html=""):
        self.states = states
        self.expected_cards = expected_cards
        self.html = html
        self.state_index = 0
        self.scroll_count = 0

    @property
    def page_source(self):
        return self.html

    def find_element(self, by, selector):
        return FakeElement(f"Hotwheels Toys & Games For Kids ({self.expected_cards} Items)")

    def find_elements(self, by, selector):
        card_count, _ = self.states[self.state_index]
        return [FakeElement()] * card_count

    def execute_script(self, script):
        if script.startswith("window.scrollTo"):
            self.scroll_count += 1
            if self.state_index < len(self.states) - 1:
                self.state_index += 1
            return None
        if script == "return document.body.scrollHeight":
            return self.states[self.state_index][1]
        raise AssertionError(f"Unexpected script: {script}")

    def get(self, url):
        self.url = url


def make_card(
    product_id="12345",
    name="Hot Wheels Test Car",
    button='<div class="ga_bn_btn_addcart">ADD TO CART</div>',
    extra_text="",
):
    return f"""
    <div class="list_block lft">
      <a href="//www.firstcry.com/hot-wheels/test-car/{product_id}/product-detail?ref=listing">
        <img data-src="//cdn.fcglcdn.com/products/{product_id}.webp" alt="{name}">
      </a>
      <a href="//www.firstcry.com/hot-wheels/test-car/{product_id}/product-detail"
         title="{name}">{name}</a>
      {button}
      <span>{extra_text}</span>
    </div>
    """


class ParsePageTests(unittest.TestCase):
    def test_parses_normalized_urls_and_stable_product_id(self):
        products = parse_page(make_card())

        self.assertEqual(["12345"], list(products))
        self.assertEqual(
            "https://www.firstcry.com/hot-wheels/test-car/12345/product-detail?ref=listing",
            products["12345"]["link"],
        )
        self.assertEqual(
            "https://cdn.fcglcdn.com/products/12345.webp",
            products["12345"]["image"],
        )
        self.assertTrue(products["12345"]["in_stock"])

    def test_explicit_out_of_stock_text_wins_over_cart_button(self):
        products = parse_page(make_card(extra_text="Notify Me when back in stock"))

        self.assertFalse(products["12345"]["in_stock"])

    def test_disabled_or_hidden_cart_button_is_not_available(self):
        disabled = '<div class="ga_bn_btn_addcart disabled">ADD TO CART</div>'
        hidden = '<div class="ga_bn_btn_addcart" style="display: none">ADD TO CART</div>'

        self.assertFalse(parse_page(make_card(button=disabled))["12345"]["in_stock"])
        self.assertFalse(parse_page(make_card(button=hidden))["12345"]["in_stock"])

    def test_ignores_non_product_list_blocks(self):
        html = '<div class="list_block"><a href="/offers">Offer</a></div>'

        self.assertEqual({}, parse_page(html))

    def test_extracts_catalog_count(self):
        self.assertEqual(1275, parse_catalog_count("Hot Wheels (1,275 Items)"))
        self.assertIsNone(parse_catalog_count("Hot Wheels"))


class ScrollTests(unittest.TestCase):
    @patch("monitor_selenium.time.sleep")
    def test_scrolls_until_expected_card_count_is_reached(self, sleep):
        driver = FakeScrollDriver(states=[(1, 100), (2, 200), (3, 300)])

        result = scroll_to_bottom(driver, max_seconds=1, settle_seconds=1, poll_seconds=0)

        self.assertEqual(3, result.observed_cards)
        self.assertTrue(result.reached_expected_count)
        self.assertEqual(2, driver.scroll_count)

    @patch("monitor_selenium.time.sleep")
    def test_stops_after_settling_when_catalog_count_is_unavailable(self, sleep):
        driver = FakeScrollDriver(states=[(1, 100)], expected_cards=None)

        result = scroll_to_bottom(driver, max_seconds=1, settle_seconds=0, poll_seconds=0)

        self.assertEqual(1, result.observed_cards)
        self.assertFalse(result.reached_expected_count)


class ScrapeProductsTests(unittest.TestCase):
    @patch("monitor_selenium.scroll_to_bottom")
    def test_rejects_incomplete_lazy_load(self, scroll_to_bottom_mock):
        scroll_to_bottom_mock.return_value = ScrollResult(20, 275, 1.0, False)
        driver = FakeScrollDriver(states=[(20, 100)], html=make_card())

        with self.assertRaisesRegex(ScrapeError, "stopped early"):
            scrape_products(driver)


if __name__ == "__main__":
    unittest.main()
