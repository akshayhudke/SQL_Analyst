CREATE TABLE customers (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  region TEXT NOT NULL,
  country TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE products (
  id SERIAL PRIMARY KEY,
  sku TEXT NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  price NUMERIC(10,2) NOT NULL
);

CREATE TABLE orders (
  id SERIAL PRIMARY KEY,
  customer_id INT NOT NULL REFERENCES customers(id),
  product_id INT NOT NULL REFERENCES products(id),
  quantity INT NOT NULL,
  status TEXT NOT NULL,
  ordered_at TIMESTAMP NOT NULL DEFAULT NOW(),
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE order_items (
  id SERIAL PRIMARY KEY,
  order_id INT NOT NULL REFERENCES orders(id),
  product_id INT NOT NULL REFERENCES products(id),
  quantity INT NOT NULL
);

CREATE TABLE payments (
  id SERIAL PRIMARY KEY,
  order_id INT NOT NULL REFERENCES orders(id),
  status TEXT NOT NULL,
  amount NUMERIC(10,2) NOT NULL,
  paid_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_product_id ON orders(product_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_customers_country ON customers(country);
CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);
CREATE INDEX idx_payments_order_id ON payments(order_id);
CREATE INDEX idx_payments_status ON payments(status);

INSERT INTO customers (name, region, country, created_at)
SELECT
  'Customer ' || gs,
  CASE WHEN gs % 4 = 0 THEN 'west' WHEN gs % 4 = 1 THEN 'east' WHEN gs % 4 = 2 THEN 'north' ELSE 'south' END,
  CASE
    WHEN gs % 5 = 0 THEN 'india'
    WHEN gs % 5 = 1 THEN 'usa'
    WHEN gs % 5 = 2 THEN 'germany'
    WHEN gs % 5 = 3 THEN 'brazil'
    ELSE 'japan'
  END,
  NOW() - (gs || ' days')::interval
FROM generate_series(1, 100000) AS gs;

INSERT INTO products (sku, name, category, price)
SELECT
  'SKU-' || gs,
  'Product ' || gs,
  CASE WHEN gs % 3 = 0 THEN 'hardware' WHEN gs % 3 = 1 THEN 'software' ELSE 'service' END,
  (gs % 100) + 0.99
FROM generate_series(1, 20000) AS gs;

INSERT INTO orders (customer_id, product_id, quantity, status, ordered_at, created_at)
SELECT
  (random() * 99999 + 1)::int,
  (random() * 19999 + 1)::int,
  (random() * 5 + 1)::int,
  CASE WHEN gs % 5 = 0 THEN 'refunded' WHEN gs % 5 = 1 THEN 'pending' WHEN gs % 5 = 2 THEN 'shipped' WHEN gs % 5 = 3 THEN 'delivered' ELSE 'cancelled' END,
  NOW() - (gs || ' hours')::interval,
  NOW() - (gs || ' hours')::interval
FROM generate_series(1, 1000000) AS gs;

INSERT INTO order_items (order_id, product_id, quantity)
SELECT
  o.id,
  (random() * 19999 + 1)::int,
  (random() * 4 + 1)::int
FROM orders o
WHERE o.id % 2 = 0;

INSERT INTO payments (order_id, status, amount, paid_at)
SELECT
  o.id,
  CASE WHEN o.status IN ('shipped', 'delivered') THEN 'SUCCESS'
       WHEN o.status = 'pending' THEN 'PENDING'
       ELSE 'FAILED' END,
  (random() * 500 + 20)::numeric(10,2),
  o.ordered_at + (random() * 24 || ' hours')::interval
FROM orders o;
