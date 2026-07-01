CREATE TABLE IF NOT EXISTS specimens (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  note TEXT NOT NULL,
  doctrine TEXT NOT NULL,
  readings TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_specimens_created_at ON specimens(created_at DESC);
