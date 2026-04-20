# Health Vault — Claude Code Context

This is a personal health tracking vault synced automatically from Apple Health
twice a day via iOS Shortcuts → Cloudflare Worker → GitHub Actions.

## Data location

- **Daily notes:** `vault/Health/YYYY-MM-DD.md`  
  Each file has YAML frontmatter with all metrics plus a human-readable body.

- **Raw JSON:** `health/apple-health/parsed/`  
  One JSON file per metric type (e.g. `stepcount.json`, `sleep_data.json`).

## Frontmatter fields in each daily note

| Field             | Unit    | Description                        |
|-------------------|---------|------------------------------------|
| `date`            | —       | ISO date YYYY-MM-DD                |
| `sleep_hours`     | hours   | Total sleep duration               |
| `hrv`             | ms      | Heart Rate Variability (avg)       |
| `resting_hr`      | bpm     | Resting heart rate (avg)           |
| `steps`           | count   | Total daily steps                  |
| `weight`          | kg      | Body mass (last reading of day)    |
| `active_energy`   | kcal    | Active energy burned               |
| `resting_energy`  | kcal    | Basal / resting energy burned      |
| `blood_oxygen`    | %       | SpO2 (avg)                         |
| `exercise_min`    | minutes | Apple Exercise ring minutes        |
| `respiratory_rate`| brpm    | Breaths per minute (avg)           |

## How to answer health questions

1. Read the last 7–14 files in `vault/Health/` (sort by filename = sort by date)
2. Use frontmatter values for trend analysis
3. **Flag automatically if:**
   - HRV drops > 15% week-over-week
   - Sleep < 6 h for 3+ consecutive days
   - Resting HR elevated > 5 bpm above the prior 7-day average
   - Steps < 3,000 for more than 2 consecutive days
4. When asked for a summary, include: sleep trend, HRV trend, activity trend,
   and any flags with a plain-English recommendation.
