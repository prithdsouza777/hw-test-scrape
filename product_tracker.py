from copy import deepcopy
from datetime import datetime


class ProductTracker:
    def __init__(self, max_alerts=50, max_monitored_products=20):
        self.max_alerts = max_alerts
        self.max_monitored_products = max_monitored_products
        self.current_products = {}
        self.seen_products = {}
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
            self.seen_products[product_id]["in_stock"] = False

        for product_id, product in products.items():
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
        return {
            "products": in_stock_products,
            "monitored_products": deepcopy(self.monitored_products),
            "alerts": deepcopy(self.alerts),
            "total_count": len(in_stock_products),
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
