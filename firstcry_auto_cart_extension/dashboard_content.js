(function () {
    const ADD_ACTION_SELECTOR = '[data-firstcry-cart-action="add"]';

    document.documentElement.setAttribute('data-firstcry-cart-bridge', 'loaded');

    document.addEventListener('click', (event) => {
        const action = event.target.closest(ADD_ACTION_SELECTOR);
        if (!action) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();

        if (action.dataset.cartState === 'pending') {
            return;
        }

        const originalText = action.textContent;
        setActionState(action, 'pending', 'OPENING CART');

        chrome.runtime.sendMessage(
            {
                type: 'HW_MONITOR_ADD_FROM_RECENT_ORDER',
                productId: action.dataset.productId,
                productName: action.dataset.productName,
                productUrl: action.dataset.productUrl,
                productImage: action.dataset.productImage,
            },
            (response) => {
                const runtimeError = chrome.runtime.lastError;
                if (runtimeError || !response || !response.ok) {
                    setActionState(action, 'failed', 'RELOAD HELPER');
                    window.setTimeout(() => {
                        setActionState(action, '', originalText);
                    }, 2500);
                    return;
                }

                setActionState(action, '', originalText);
            }
        );
    }, true);

    function setActionState(action, state, text) {
        if (state) {
            action.dataset.cartState = state;
        } else {
            delete action.dataset.cartState;
        }
        action.textContent = text;
    }
})();
