CREATE TABLE IF NOT EXISTS editions (
  edition_date TEXT PRIMARY KEY,
  issue_no INTEGER NOT NULL,
  condition TEXT NOT NULL,
  temp_hi INTEGER NOT NULL,
  temp_lo INTEGER NOT NULL,
  humidity INTEGER NOT NULL,
  cloud_cover INTEGER NOT NULL,
  wind_mph INTEGER NOT NULL,
  wind_deg INTEGER NOT NULL,
  precip_prob INTEGER NOT NULL,
  sunrise TEXT NOT NULL,
  sunset TEXT NOT NULL,
  moon_phase REAL NOT NULL,
  aqi INTEGER,
  accent TEXT NOT NULL,
  leader_text TEXT NOT NULL,
  motto_text TEXT NOT NULL,
  number_value TEXT NOT NULL,
  number_caption TEXT NOT NULL,
  ornament_seed INTEGER NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_editions_issue_no ON editions(issue_no DESC);
