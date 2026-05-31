(function () {
    const params = new URLSearchParams(window.location.search);
    if (params.get('hw_auto_add') !== '1') {
        return;
    }

    const checkoutUrl = 'https://checkout.firstcry.com/pay';
    const productId = params.get('hw_pid') || getProductIdFromPath();
    if (!productId) {
        return;
    }

    injectPageScript(productId, checkoutUrl);

    function getProductIdFromPath() {
        const match = window.location.pathname.match(/\/(\d+)\/product-detail/i);
        return match ? match[1] : '';
    }

    function injectPageScript(pid, checkout) {
        const script = document.createElement('script');
        script.textContent = `(${runInFirstCryPage.toString()})(${JSON.stringify(pid)}, ${JSON.stringify(checkout)});`;
        (document.documentElement || document.head).appendChild(script);
        script.remove();
    }

    function runInFirstCryPage(pid, checkout) {
        const cookieName = '_$FC$_cookies_for_cart_v2_';
        const entry = `NO^${pid}^1^0`;

        function readCookie(name) {
            const prefix = `${name}=`;
            const cookie = document.cookie
                .split(';')
                .map((value) => value.trim())
                .find((value) => value.startsWith(prefix));
            return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : '';
        }

        function mergeCartCookie(existing) {
            const entries = existing ? existing.split('*').filter(Boolean) : [];
            let found = false;
            const merged = entries.map((item) => {
                const parts = item.split('^');
                if (parts.length >= 4 && parts[1] === pid) {
                    parts[2] = String(Math.max(Number(parts[2]) || 1, 1));
                    found = true;
                    return parts.join('^');
                }
                return item;
            });
            if (!found) {
                merged.push(entry);
            }
            return merged.join('*');
        }

        function writeCartCookie() {
            const merged = mergeCartCookie(readCookie(cookieName));
            document.cookie = `${cookieName}=${encodeURIComponent(merged)}; path=/; domain=.firstcry.com; max-age=604800; SameSite=Lax`;
            try {
                localStorage.removeItem('CartCookieData');
                localStorage.removeItem('CartCookie');
            } catch (error) {}
        }

        function redirectToCheckout(delayMs) {
            window.setTimeout(() => {
                window.location.href = checkout;
            }, delayMs);
        }

        function tryAddToCart(attempt) {
            if (typeof AddToCart === 'function') {
                try {
                    AddToCart(pid, '1', 'NO', '0', true, false, false);
                    redirectToCheckout(900);
                    return;
                } catch (error) {
                    writeCartCookie();
                    redirectToCheckout(500);
                    return;
                }
            }

            if (attempt >= 40) {
                writeCartCookie();
                redirectToCheckout(500);
                return;
            }

            window.setTimeout(() => tryAddToCart(attempt + 1), 250);
        }

        tryAddToCart(0);
    }
})();
