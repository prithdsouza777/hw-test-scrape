(function () {
    const ORDERDETAILS_PATH = '/orderdetails';

    if (!window.location.pathname.toLowerCase().startsWith(ORDERDETAILS_PATH)) {
        return;
    }

    chrome.storage.local.set({
        lastOrderDetailsUrl: stripHash(window.location.href),
    });

    window.addEventListener('hashchange', maybeRunBridge);
    maybeRunBridge();

    function maybeRunBridge() {
        const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
        if (params.get('hw_recent_order_add') !== '1') {
            return;
        }

        document.documentElement.setAttribute('data-hw-recent-order-bridge', 'loaded');
        injectPageRunner();
    }

    function injectPageRunner() {
        const script = document.createElement('script');
        script.src = chrome.runtime.getURL('orderdetails_page_runner.js');
        script.dataset.hwRecentOrderBridge = '1';
        script.onload = () => script.remove();
        (document.head || document.documentElement).appendChild(script);
    }

    function stripHash(url) {
        const parsed = new URL(url);
        parsed.hash = '';
        return parsed.toString();
    }
})();
