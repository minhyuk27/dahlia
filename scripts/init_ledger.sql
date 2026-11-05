CREATE TABLE IF NOT EXISTS articles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft',  -- draft | review | published | archived
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    published_at TEXT,
    product_ids TEXT,   -- 쉼표 구분 제품 식별자
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    brand       TEXT NOT NULL,
    category    TEXT NOT NULL,
    covered_at  TEXT,   -- 이 제품을 처음 다룬 날짜
    UNIQUE(brand, name)
);

CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
