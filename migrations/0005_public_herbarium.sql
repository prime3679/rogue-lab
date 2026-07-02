CREATE TABLE IF NOT EXISTS herbarium_specimens (
  word TEXT PRIMARY KEY,
  seed INTEGER NOT NULL,
  binomial TEXT NOT NULL,
  press_count INTEGER NOT NULL DEFAULT 1,
  first_pressed TEXT NOT NULL,
  last_pressed TEXT NOT NULL,
  hidden INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_herbarium_last_pressed ON herbarium_specimens(last_pressed DESC);
CREATE INDEX IF NOT EXISTS idx_herbarium_visible ON herbarium_specimens(hidden, last_pressed DESC);

CREATE TABLE IF NOT EXISTS herbarium_rate (
  bucket TEXT PRIMARY KEY,
  count INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
