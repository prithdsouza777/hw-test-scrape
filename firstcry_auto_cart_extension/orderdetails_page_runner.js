(function () {
    const CHECKOUT_URL = 'https://checkout.firstcry.com/pay';
    const CART_COOKIE_NAME = '_$FC$_cookies_for_cart_v2_';
    const COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60;
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));

    if (params.get('hw_recent_order_add') !== '1') {
        return;
    }

    const product = {
        id: params.get('hw_pid') || '',
        name: params.get('hw_name') || 'Hot Wheels',
        url: params.get('hw_url') || '',
        image: params.get('hw_image') || '',
    };

    if (!/^\d+$/.test(product.id)) {
        markState('failed');
        return;
    }

    markState('waiting');
    waitForRecentOrderCartFunction(0);

    function markState(state) {
        document.documentElement.setAttribute('data-hw-recent-order-cart', state);
        document.documentElement.setAttribute('data-hw-recent-order-pid', product.id);
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
        return readCookie(CART_COOKIE_NAME).includes(`NO^${product.id}^`);
    }

    function imagePath() {
        if (!product.image) {
            return '';
        }

        return product.image.replace(/^https?:/, '');
    }

    function makeRecentOrderButton() {
        const sourceButton = findRecentOrderButton();
        const button = sourceButton
            ? sourceButton.cloneNode(true)
            : document.createElement('div');

        button.className = sourceButton
            ? sourceButton.className
            : 'J12M_42 cl_ff btn_comm btn_sb btn_outline ripple2';
        button.textContent = 'ADD TO CART';
        button.style.cssText = 'position:absolute;left:-99999px;top:-99999px;';
        button.setAttribute('onclick', `sliderproductAddcart(${product.id}, 1, this)`);

        const attributes = {
            reorderproductid: product.id,
            agef: '3',
            aget: '15',
            crntstock: '0',
            orderedqty: '1',
            comboqty: '0',
            reorderprodids: '',
            iscombo: '0',
            comboprodids: '',
            comboid: '',
            imageurl: imagePath(),
            isreorderall: '0',
            branddid: '113',
            pname: product.name,
            pcid: '5',
            scat: '94',
            clubprice: getDataValue(button, 'clubprice', '0'),
            discounted_price: getDataValue(button, 'discounted_price', '0'),
            mrp: getDataValue(button, 'mrp', '0'),
            product_id: product.id,
            size: getDataValue(button, 'size', ''),
            total_ratings: getDataValue(button, 'total_ratings', '0'),
            total_reviews: getDataValue(button, 'total_reviews', '0'),
            subcategory_name: 'Toy Cars, Trains & Vehicles',
            categoryname: 'Toys & Gaming',
            subcategoryname: 'Toy Cars, Trains & Vehicles',
            brandname: 'Hot Wheels',
            slider: 'recentlyview_unit_order_detail',
        };

        Object.entries(attributes).forEach(([name, value]) => {
            button.setAttribute(`data-${name}`, value);
        });

        document.body.appendChild(button);
        return button;
    }

    function findRecentOrderButton() {
        const selectors = [
            '[onclick*="sliderproductAddcart"]',
            '[data-slider="recentlyview_unit_order_detail"][data-product_id]',
            '[data-reorderproductid][data-product_id]',
        ];
        return selectors
            .flatMap((selector) => Array.from(document.querySelectorAll(selector)))
            .find((element) => {
                return typeof element.getAttribute('onclick') === 'string' ||
                    element.getAttribute('data-product_id');
            });
    }

    function getDataValue(element, name, fallback) {
        const value = element.getAttribute(`data-${name}`);
        return value === null || value === undefined || value === '' ? fallback : value;
    }

    function callRecentOrderAdd() {
        const button = makeRecentOrderButton();
        markState('running');

        try {
            sliderproductAddcart(Number(product.id), 1, button);
        } catch (error) {
            writeCartCookieAndCheckout('fallback-after-error');
            return;
        }

        waitForCartThenCheckout(0);
    }

    function waitForCartThenCheckout(attempt) {
        if (productIsInCart()) {
            markState('done');
            window.location.href = CHECKOUT_URL;
            return;
        }

        if (attempt >= 40) {
            writeCartCookieAndCheckout('fallback-unconfirmed');
            return;
        }

        window.setTimeout(() => waitForCartThenCheckout(attempt + 1), 250);
    }

    function waitForRecentOrderCartFunction(attempt) {
        if (typeof sliderproductAddcart === 'function' && document.body) {
            callRecentOrderAdd();
            return;
        }

        if (attempt >= 100) {
            writeCartCookieAndCheckout('fallback-no-slider-function');
            return;
        }

        window.setTimeout(() => waitForRecentOrderCartFunction(attempt + 1), 250);
    }

    function writeCartCookieAndCheckout(state) {
        const mergedCartCookie = mergeCartCookie(readCookie(CART_COOKIE_NAME), product.id, 1);
        writeCartCookie(mergedCartCookie);

        if (productIsInCart()) {
            markState(state);
            window.location.href = CHECKOUT_URL;
            return;
        }

        markState('failed-cookie-write');
    }

    function mergeCartCookie(existingValue, productId, quantity) {
        const entries = existingValue
            .split('*')
            .map((entry) => entry.trim())
            .filter(Boolean);
        let foundProduct = false;

        const mergedEntries = entries.map((entry) => {
            const parts = entry.split('^');
            if (parts.length >= 4 && parts[1] === productId) {
                const currentQuantity = Number(parts[2]) || 0;
                parts[0] = parts[0] || 'NO';
                parts[2] = String(Math.max(currentQuantity, quantity));
                parts[3] = parts[3] || '0';
                foundProduct = true;
                return parts.join('^');
            }

            return entry;
        });

        if (!foundProduct) {
            mergedEntries.push(`NO^${productId}^${quantity}^0`);
        }

        return mergedEntries.join('*');
    }

    function writeCartCookie(value) {
        if (window.jQuery && typeof window.jQuery.cookie === 'function') {
            const cookieDomain = typeof DomainName !== 'undefined' && DomainName
                ? DomainName
                : 'firstcry.com';
            window.jQuery.cookie(CART_COOKIE_NAME, value, {
                path: '/',
                expires: 7,
                domain: cookieDomain,
            });
            return;
        }

        document.cookie = `${CART_COOKIE_NAME}=${encodeURIComponent(value)}; path=/; domain=.firstcry.com; max-age=${COOKIE_MAX_AGE_SECONDS}; SameSite=Lax`;
    }
})();
