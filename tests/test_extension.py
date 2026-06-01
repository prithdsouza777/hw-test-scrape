import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "firstcry_auto_cart_extension"


class FirstCryExtensionTests(unittest.TestCase):
    def test_checkout_coupon_prefill_script_is_registered(self):
        manifest = json.loads((EXTENSION_DIR / "manifest.json").read_text())

        checkout_scripts = [
            script
            for script in manifest["content_scripts"]
            if "https://checkout.firstcry.com/pay*" in script["matches"]
        ]

        self.assertEqual(1, len(checkout_scripts))
        self.assertIn("checkout_coupon_content.js", checkout_scripts[0]["js"])

    def test_checkout_coupon_prefill_uses_expected_code(self):
        script = (EXTENSION_DIR / "checkout_coupon_content.js").read_text()

        self.assertIn("JP37TY", script)
        self.assertIn("data-hw-coupon-prefill", script)


if __name__ == "__main__":
    unittest.main()
