# FirstCry Recent Order Cart Bridge

This unpacked Chrome extension makes dashboard `ADD TO CART` buttons use
FirstCry's recent-order carousel path instead of the product page button.

The recent-order button calls:

```js
sliderproductAddcart(productId, 1, buttonElement)
```

That path is important because FirstCry can accept a product from reorder /
recently-viewed widgets even while the product page still has no add button or
shows stale out-of-stock UI.

## Install

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select this folder: `firstcry_auto_cart_extension`.
5. Open your FirstCry order details page once, for example an
   `https://www.firstcry.com/orderdetails?poid=...` page.

When a dashboard `ADD TO CART` button is clicked, the extension opens your
orderdetails page with the clicked product ID in the URL hash, creates a hidden
button with the same data attributes as FirstCry's recent-order `ADD TO CART`
button, calls `sliderproductAddcart(productId, 1, button)`, then goes to
`https://checkout.firstcry.com/pay` after the target product appears in the
FirstCry cart cookie. If the recent-order call does not confirm, the runner
writes the same FirstCry cart cookie format on `firstcry.com` before checkout.

After editing this folder, click **Reload** on the extension in
`chrome://extensions`; Chrome does not automatically pick up changed unpacked
extension files.
