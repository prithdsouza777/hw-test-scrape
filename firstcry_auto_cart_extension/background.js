const CHECKOUT_URL = 'https://checkout.firstcry.com/pay';
const DEFAULT_ORDERDETAILS_URL = 'https://www.firstcry.com/orderdetails';
const ORDERDETAILS_TAB_PATTERNS = [
    'https://www.firstcry.com/orderdetails*',
    'https://firstcry.com/orderdetails*',
];

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || message.type !== 'HW_MONITOR_ADD_FROM_RECENT_ORDER') {
        return false;
    }

    openRecentOrderBridge(message)
        .then((result) => sendResponse(result))
        .catch((error) => {
            sendResponse({
                ok: false,
                error: error && error.message ? error.message : String(error),
            });
        });

    return true;
});

async function openRecentOrderBridge(message) {
    const productId = normalizeProductId(message.productId);
    const existingOrderTab = await findOpenOrderDetailsTab();
    const orderDetailsUrl = existingOrderTab && existingOrderTab.url
        ? stripHash(existingOrderTab.url)
        : await getStoredOrderDetailsUrl();
    const bridgeUrl = buildBridgeUrl(orderDetailsUrl, {
        productId,
        productName: message.productName || '',
        productUrl: message.productUrl || '',
        productImage: message.productImage || '',
    });

    const tab = existingOrderTab
        ? await chrome.tabs.update(existingOrderTab.id, { url: bridgeUrl, active: true })
        : await chrome.tabs.create({ url: bridgeUrl, active: true });

    return {
        ok: true,
        productId,
        orderDetailsUrl,
        checkoutUrl: CHECKOUT_URL,
        tabId: tab.id,
    };
}

async function findOpenOrderDetailsTab() {
    for (const pattern of ORDERDETAILS_TAB_PATTERNS) {
        const tabs = await chrome.tabs.query({ url: pattern });
        if (tabs.length) {
            return tabs[0];
        }
    }

    return null;
}

async function getStoredOrderDetailsUrl() {
    const stored = await chrome.storage.local.get('lastOrderDetailsUrl');
    if (stored.lastOrderDetailsUrl) {
        return stripHash(stored.lastOrderDetailsUrl);
    }

    return DEFAULT_ORDERDETAILS_URL;
}

function buildBridgeUrl(orderDetailsUrl, product) {
    const url = new URL(orderDetailsUrl || DEFAULT_ORDERDETAILS_URL);
    const params = new URLSearchParams();
    params.set('hw_recent_order_add', '1');
    params.set('hw_pid', product.productId);
    params.set('hw_name', product.productName);
    params.set('hw_url', product.productUrl);
    params.set('hw_image', product.productImage);
    url.hash = params.toString();
    return url.toString();
}

function stripHash(url) {
    const parsed = new URL(url || DEFAULT_ORDERDETAILS_URL);
    parsed.hash = '';
    return parsed.toString();
}

function normalizeProductId(value) {
    const productId = String(value || '').trim();
    if (!/^\d+$/.test(productId)) {
        throw new Error('Missing FirstCry product ID');
    }
    return productId;
}
