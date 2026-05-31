(function () {
    const params = new URLSearchParams(window.location.search);
    if (params.get('hw_auto_add') !== '1') {
        return;
    }
    if (window.__hotWheelsMonitorAutoAddStarted) {
        return;
    }
    window.__hotWheelsMonitorAutoAddStarted = true;

    const checkoutUrl = 'https://checkout.firstcry.com/pay';
    const requestedProductId = params.get('hw_pid') || getProductIdFromPath();

    function getProductIdFromPath() {
        const match = window.location.pathname.match(/\/(\d+)\/product-detail/i);
        return match ? match[1] : '';
    }

    function readCookie(name) {
        const prefix = `${name}=`;
        const hit = document.cookie
            .split(';')
            .map((value) => value.trim())
            .find((value) => value.startsWith(prefix));
        return hit ? decodeURIComponent(hit.slice(prefix.length)) : '';
    }

    function productIsInCart() {
        if (!requestedProductId) {
            return false;
        }
        return readCookie('_$FC$_cookies_for_cart_v2_').includes(`NO^${requestedProductId}^`);
    }

    function currentProductIsReady() {
        if (!requestedProductId) {
            return false;
        }
        if (typeof CurrentProductID === 'undefined') {
            return false;
        }
        return String(CurrentProductID) === String(requestedProductId);
    }

    function findAddButton() {
        return findVisible('.add_to_cart');
    }

    function findGoToCartButton() {
        return findVisible('.go_to_cart,.gcart,.go_to_cart_prod,.gotoccart');
    }

    function findVisible(selector) {
        return Array.from(document.querySelectorAll(selector)).find((element) => {
            return element.offsetWidth || element.offsetHeight || element.getClientRects().length;
        });
    }

    function clickElement(element) {
        element.scrollIntoView({ block: 'center' });
        element.click();
    }

    function addUsingFirstCryFlow() {
        const addButton = findAddButton();
        if (addButton) {
            clickElement(addButton);
            return true;
        }

        if (typeof AddProductToCart === 'function') {
            AddProductToCart();
            if (typeof addtocartbutton === 'function') {
                addtocartbutton();
            }
            return true;
        }

        if (typeof AddToCart === 'function') {
            AddToCart(requestedProductId, '1', 'NO', '0', true, false, false);
            return true;
        }

        return false;
    }

    function checkoutTarget() {
        if (typeof cartpdpurl !== 'undefined' && cartpdpurl) {
            return cartpdpurl;
        }

        return checkoutUrl;
    }

    function forceCheckoutIfStillOnProductPage() {
        window.setTimeout(() => {
            if (/\/product-detail/i.test(window.location.pathname)) {
                window.location.href = checkoutTarget();
            }
        }, 700);
    }

    function goToCartOrCheckout() {
        const goToCartButton = findGoToCartButton();
        if (goToCartButton) {
            clickElement(goToCartButton);
            forceCheckoutIfStillOnProductPage();
            return;
        }

        window.location.href = checkoutTarget();
    }

    function waitForCartThenGo(attempt) {
        if (productIsInCart() || findGoToCartButton()) {
            goToCartOrCheckout();
            return;
        }

        if (attempt >= 80) {
            return;
        }

        window.setTimeout(() => waitForCartThenGo(attempt + 1), 200);
    }

    function waitForFirstCryProduct(attempt) {
        if (!/\/product-detail/i.test(window.location.pathname)) {
            return;
        }

        const canAdd =
            findAddButton() ||
            typeof AddProductToCart === 'function' ||
            typeof AddToCart === 'function';

        if (currentProductIsReady() && canAdd) {
            if (productIsInCart()) {
                goToCartOrCheckout();
                return;
            }

            if (addUsingFirstCryFlow()) {
                waitForCartThenGo(0);
                return;
            }
        }

        if (attempt >= 80) {
            return;
        }

        window.setTimeout(() => waitForFirstCryProduct(attempt + 1), 250);
    }

    waitForFirstCryProduct(0);
})();
