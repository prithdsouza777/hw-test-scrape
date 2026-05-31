from copy import deepcopy
from datetime import datetime


class ProductTracker:
    def __init__(
        self,
        max_alerts=50,
        max_monitored_products=20,
        missing_confirmation_snapshots=2,
    ):
        if missing_confirmation_snapshots < 1:
            raise ValueError("missing_confirmation_snapshots must be at least 1")

        self.max_alerts = max_alerts
        self.max_monitored_products = max_monitored_products
        self.missing_confirmation_snapshots = missing_confirmation_snapshots
        self.current_products = {}
        self.seen_products = {}
        self.missing_counts = {}
        self.alerts = []
        self.monitored_products = []
        self.initialized = False

    def update(self, products, now=None):
        if not products:
            raise ValueError("Refusing to replace product state with an empty snapshot")

        now = now or datetime.now()
        products = deepcopy(products)
        events = []

        missing_ids = self.seen_products.keys() - products.keys()
        for product_id in missing_ids:
            self.missing_counts[product_id] = self.missing_counts.get(product_id, 0) + 1
            if self.missing_counts[product_id] >= self.missing_confirmation_snapshots:
                self.seen_products[product_id]["in_stock"] = False

        for product_id, product in products.items():
            self.missing_counts.pop(product_id, None)
            old_product = self.seen_products.get(product_id)
            if old_product is None:
                if self.initialized and product["in_stock"]:
                    events.append(self._record_event("NEW", product, now))
            elif not old_product["in_stock"] and product["in_stock"]:
                events.append(self._record_event("STOCK", product, now))

            self.seen_products[product_id] = deepcopy(product)

        self.current_products = products
        self.monitored_products = [
            product
            for product in self.monitored_products
            if product["id"] in products and products[product["id"]]["in_stock"]
        ]
        self.initialized = True
        return events

    def snapshot(self):
        in_stock_products = {
            product_id: deepcopy(product)
            for product_id, product in self.current_products.items()
            if product["in_stock"]
        }
        pending_products = {
            product_id: deepcopy(product)
            for product_id, product in self.current_products.items()
            if not product["in_stock"] and product.get("pending_cart")
        }
        return {
            "products": in_stock_products,
            "pending_products": pending_products,
            "monitored_products": deepcopy(self.monitored_products),
            "alerts": deepcopy(self.alerts),
            "total_count": len(in_stock_products),
            "pending_count": len(pending_products),
        }

    def _record_event(self, event_type, product, now):
        timestamp = now.strftime("%H:%M:%S")
        label = "New Product" if event_type == "NEW" else "Back in Stock"
        event = {
            "id": f"{now.isoformat()}-{event_type}-{product['id']}",
            "type": event_type,
            "message": f"{label}: {product['name']}",
            "link": product["link"],
            "time": timestamp,
            "product": deepcopy(product),
        }
        self.alerts.insert(0, {key: value for key, value in event.items() if key != "product"})
        del self.alerts[self.max_alerts :]

        monitored_product = deepcopy(product)
        monitored_product["alert_type"] = event_type
        monitored_product["alert_time"] = timestamp
        self.monitored_products = [
            existing
            for existing in self.monitored_products
            if existing["id"] != product["id"]
        ]
        self.monitored_products.insert(0, monitored_product)
        del self.monitored_products[self.max_monitored_products :]
        return event
