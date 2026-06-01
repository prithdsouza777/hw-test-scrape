(function () {
    const COUPON_CODE = 'JP37TY';
    const CHECKOUT_HOST = 'checkout.firstcry.com';
    const CHECKOUT_PATH = '/pay';
    const RETRY_MS = 250;
    const MAX_ATTEMPTS = 80;
    const COUPON_WORDS = [
        'coupon',
        'promo',
        'voucher',
        'offer code',
        'discount code',
    ];

    if (
        window.location.hostname.toLowerCase() !== CHECKOUT_HOST ||
        !window.location.pathname.toLowerCase().startsWith(CHECKOUT_PATH)
    ) {
        return;
    }

    let prefilled = false;
    let scheduled = false;

    document.documentElement.setAttribute('data-hw-coupon-prefill', 'waiting');
    document.addEventListener('click', scheduleCouponPrefill, true);
    document.addEventListener('focusin', prefillFocusedCouponInput, true);

    const observer = new MutationObserver(scheduleCouponPrefill);
    observer.observe(document.documentElement, {
        childList: true,
        subtree: true,
    });

    waitForCouponInput(0);

    function waitForCouponInput(attempt) {
        scheduled = false;
        if (prefilled) {
            return;
        }

        const input = findCouponInput();
        if (input && prefillCoupon(input)) {
            markPrefilled();
            return;
        }

        if (attempt >= MAX_ATTEMPTS) {
            document.documentElement.setAttribute('data-hw-coupon-prefill', 'not-found');
            return;
        }

        window.setTimeout(() => waitForCouponInput(attempt + 1), RETRY_MS);
    }

    function scheduleCouponPrefill() {
        if (prefilled || scheduled) {
            return;
        }

        scheduled = true;
        window.setTimeout(() => waitForCouponInput(0), 100);
    }

    function prefillFocusedCouponInput(event) {
        if (
            !prefilled &&
            isUsableTextInput(event.target) &&
            inputLooksCouponRelated(event.target) &&
            prefillCoupon(event.target)
        ) {
            markPrefilled();
        }
    }

    function findCouponInput() {
        return findByDirectSelector() || findByNearbyText();
    }

    function findByDirectSelector() {
        const selectors = [
            'input[name*="coupon" i]',
            'input[id*="coupon" i]',
            'input[class*="coupon" i]',
            'input[placeholder*="coupon" i]',
            'input[aria-label*="coupon" i]',
            'input[name*="promo" i]',
            'input[id*="promo" i]',
            'input[class*="promo" i]',
            'input[placeholder*="promo" i]',
            'input[aria-label*="promo" i]',
        ];

        return selectors
            .flatMap((selector) => Array.from(document.querySelectorAll(selector)))
            .find(isUsableTextInput) || null;
    }

    function findByNearbyText() {
        return Array.from(document.querySelectorAll('input'))
            .filter(isUsableTextInput)
            .find(inputLooksCouponRelated) || null;
    }

    function isUsableTextInput(input) {
        if (!input || input.disabled || input.readOnly) {
            return false;
        }

        const type = (input.getAttribute('type') || 'text').toLowerCase();
        if (!['', 'text', 'search', 'tel'].includes(type)) {
            return false;
        }

        const rect = input.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function includesCouponWord(text) {
        const normalized = text.toLowerCase();
        return COUPON_WORDS.some((word) => normalized.includes(word));
    }

    function inputLooksCouponRelated(input) {
        const container = input.closest('label, form, section, div, li, article') || input.parentElement;
        const values = [
            input.name,
            input.id,
            input.className,
            input.placeholder,
            input.getAttribute('aria-label'),
            container ? container.textContent : '',
        ];

        return includesCouponWord(values.filter(Boolean).join(' '));
    }

    function prefillCoupon(input) {
        const existingValue = String(input.value || '').trim();
        if (existingValue && existingValue !== COUPON_CODE) {
            return false;
        }

        setInputValue(input, COUPON_CODE);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        input.setAttribute('data-hw-coupon-prefilled', '1');
        return true;
    }

    function markPrefilled() {
        prefilled = true;
        observer.disconnect();
        document.documentElement.setAttribute('data-hw-coupon-prefill', 'done');
    }

    function setInputValue(input, value) {
        const prototype = Object.getPrototypeOf(input);
        const descriptor = Object.getOwnPropertyDescriptor(prototype, 'value') ||
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');

        if (descriptor && typeof descriptor.set === 'function') {
            descriptor.set.call(input, value);
            return;
        }

        input.value = value;
    }
})();
