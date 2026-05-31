(function () {
    const checkoutUrl = 'https://checkout.firstcry.com/pay';
    const request = readAutoAddRequest();

    if (!request.enabled || !request.productId) {
        return;
    }

    const root = document.documentElement;
    const currentState = root.getAttribute('data-hw-monitor-auto-cart');
    if (currentState === 'running' || currentState === 'done') {
        return;
    }

    root.setAttribute('data-hw-monitor-auto-cart', 'running');
    root.setAttribute('data-hw-monitor-auto-cart-owner', 'page');
    root.setAttribute('data-hw-monitor-pid', request.productId);

    waitForFirstCryProduct(0);

    function readAutoAddRequest() {
        const searchParams = new URLSearchParams(window.location.search);
        const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
        const enabled =
            searchParams.get('hw_auto_add') === '1' ||
            hashParams.get('hw_auto_add') === '1';
        const productId =
            searchParams.get('hw_pid') ||
            hashParams.get('hw_pid') ||
            getProductIdFromPath();

        return { enabled, productId };
    }

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
        return readCookie('_$FC$_cookies_for_cart_v2_').includes(`NO^${request.productId}^`);
    }

    function productIdentityMatches() {
        if (String(getProductIdFromPath()) === String(request.productId)) {
            return true;
        }

        if (typeof CurrentProductID !== 'undefined') {
            return String(CurrentProductID) === String(request.productId);
        }

        return false;
    }

    function findVisible(selector) {
        return Array.from(document.querySelectorAll(selector)).find((element) => {
            return element.offsetWidth || element.offsetHeight || element.getClientRects().length;
        });
    }

    function findAddButton() {
        return findVisible('.add_to_cart');
    }

    function findGoToCartButton() {
        return findVisible('.go_to_cart,.gcart,.go_to_cart_prod,.gotoccart');
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
            AddToCart(request.productId, '1', 'NO', '0', true, false, false);
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
            root.setAttribute('data-hw-monitor-auto-cart', 'done');
            clickElement(goToCartButton);
            forceCheckoutIfStillOnProductPage();
            return;
        }

        root.setAttribute('data-hw-monitor-auto-cart', 'done');
        window.location.href = checkoutTarget();
    }

    function waitForCartThenGo(attempt) {
        if (productIsInCart() || findGoToCartButton()) {
            goToCartOrCheckout();
            return;
        }

        if (attempt >= 80) {
            root.setAttribute('data-hw-monitor-auto-cart', 'failed');
            return;
        }

        window.setTimeout(() => waitForCartThenGo(attempt + 1), 200);
    }

    function waitForFirstCryProduct(attempt) {
        if (!/\/product-detail/i.test(window.location.pathname)) {
            root.setAttribute('data-hw-monitor-auto-cart', 'failed');
            return;
        }

        const canAdd =
            findAddButton() ||
            typeof AddProductToCart === 'function' ||
            typeof AddToCart === 'function';

        if (productIdentityMatches() && canAdd) {
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
            root.setAttribute('data-hw-monitor-auto-cart', 'failed');
            return;
        }

        window.setTimeout(() => waitForFirstCryProduct(attempt + 1), 250);
    }
})();
