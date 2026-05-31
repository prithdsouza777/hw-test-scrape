# FirstCry Auto Cart Helper

This unpacked Chrome extension makes dashboard `ADD TO CART` links complete the
same flow as clicking FirstCry's product-page add button and then going to
checkout.

## Install

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select this folder: `firstcry_auto_cart_extension`.

After that, dashboard links containing `hw_auto_add=1` will open in your normal
Chrome session, inject a page runner on FirstCry, click FirstCry's own
`ADD TO CART` button on the product page, wait for FirstCry's cart confirmation,
and then follow `GO TO CART` to `https://checkout.firstcry.com/pay`.

After editing this folder, click **Reload** on the extension in
`chrome://extensions`; Chrome does not automatically pick up changed unpacked
extension files.
