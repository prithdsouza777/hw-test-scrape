(function () {
    const checkoutUrl = 'https://checkout.firstcry.com/pay';
    const request = readAutoAddRequest();

    if (!request.enabled || !request.productId) {
        return;
    }

    const root = document.documentElement;
    root.setAttribute('data-hw-monitor-helper', 'loaded');
    root.setAttribute('data-hw-monitor-pid', request.productId);

    injectPageRunner();
    window.setTimeout(() => {
        const state = root.getAttribute('data-hw-monitor-auto-cart');
        if (state === 'running' || state === 'done') {
            return;
        }

        runDomFallback(0);
    }, 900);

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

    function injectPageRunner() {
        if (!chrome.runtime || typeof chrome.runtime.getURL !== 'function') {
            return;
        }

        const script = document.createElement('script');
        script.src = chrome.runtime.getURL('page_auto_cart.js');
        script.dataset.hwMonitorAutoCart = '1';
        script.onload = () => script.remove();
        (document.head || document.documentElement).appendChild(script);
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

    function findVisible(selector) {
        return Array.from(document.querySelectorAll(selector)).find((element) => {
            return element.offsetWidth || element.offsetHeight || element.getClientRects().length;
        });
    }

    function clickElement(element) {
        element.scrollIntoView({ block: 'center' });
        element.click();
    }

    function goToCheckout() {
        const goToCartButton = findVisible('.go_to_cart,.gcart,.go_to_cart_prod,.gotoccart');
        if (goToCartButton) {
            clickElement(goToCartButton);
            window.setTimeout(() => {
                if (/\/product-detail/i.test(window.location.pathname)) {
                    window.location.href = checkoutUrl;
                }
            }, 700);
            return;
        }

        window.location.href = checkoutUrl;
    }

    function waitForCartThenGo(attempt) {
        if (productIsInCart() || findVisible('.go_to_cart,.gcart,.go_to_cart_prod,.gotoccart')) {
            root.setAttribute('data-hw-monitor-auto-cart', 'done');
            goToCheckout();
            return;
        }

        if (attempt >= 80) {
            root.setAttribute('data-hw-monitor-auto-cart', 'failed');
            return;
        }

        window.setTimeout(() => waitForCartThenGo(attempt + 1), 200);
    }

    function runDomFallback(attempt) {
        if (!/\/product-detail/i.test(window.location.pathname)) {
            return;
        }

        if (productIsInCart()) {
            root.setAttribute('data-hw-monitor-auto-cart', 'done');
            goToCheckout();
            return;
        }

        const addButton = findVisible('.add_to_cart');
        if (addButton) {
            root.setAttribute('data-hw-monitor-auto-cart', 'running');
            root.setAttribute('data-hw-monitor-auto-cart-owner', 'content-dom');
            clickElement(addButton);
            waitForCartThenGo(0);
            return;
        }

        if (attempt >= 80) {
            root.setAttribute('data-hw-monitor-auto-cart', 'failed');
            return;
        }

        window.setTimeout(() => runDomFallback(attempt + 1), 250);
    }
})();
