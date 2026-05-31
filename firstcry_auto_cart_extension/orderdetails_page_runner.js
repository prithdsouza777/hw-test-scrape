(function () {
    const CHECKOUT_URL = 'https://checkout.firstcry.com/pay';
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
        return readCookie('_$FC$_cookies_for_cart_v2_').includes(`NO^${product.id}^`);
    }

    function imagePath() {
        if (!product.image) {
            return '';
        }

        return product.image.replace(/^https?:/, '');
    }

    function makeRecentOrderButton() {
        const button = document.createElement('div');
        button.className = 'J12M_42 cl_ff btn_comm btn_sb btn_outline ripple2';
        button.textContent = 'ADD TO CART';
        button.style.cssText = 'position:absolute;left:-99999px;top:-99999px;';

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
            clubprice: '0',
            discounted_price: '0',
            mrp: '0',
            product_id: product.id,
            size: '',
            total_ratings: '0',
            total_reviews: '0',
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

    function callRecentOrderAdd() {
        const button = makeRecentOrderButton();
        markState('running');

        try {
            sliderproductAddcart(Number(product.id), 1, button);
        } catch (error) {
            markState('failed');
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
            markState('checkout-unconfirmed');
            window.location.href = CHECKOUT_URL;
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
            markState('failed');
            return;
        }

        window.setTimeout(() => waitForRecentOrderCartFunction(attempt + 1), 250);
    }
})();
