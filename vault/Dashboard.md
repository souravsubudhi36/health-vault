# Health Dashboard

> Auto-updated twice daily from Apple Health. Last 14 days shown by default.

---

## Last 14 Days

```dataview
TABLE
  sleep_hours  AS "Sleep (h)",
  hrv          AS "HRV (ms)",
  resting_hr   AS "RHR (bpm)",
  steps        AS "Steps",
  weight       AS "Weight (kg)",
  active_energy AS "Active kcal"
FROM "Health"
WHERE date >= date(today) - dur(14 days)
SORT date DESC
```

---

## 7-Day Averages

```dataview
TABLE WITHOUT ID
  round(average(rows.sleep_hours), 1) AS "Avg Sleep (h)",
  round(average(rows.hrv), 0)         AS "Avg HRV (ms)",
  round(average(rows.resting_hr), 0)  AS "Avg RHR (bpm)",
  round(average(rows.steps), 0)       AS "Avg Steps",
  round(average(rows.weight), 1)      AS "Avg Weight (kg)"
FROM "Health"
WHERE date >= date(today) - dur(7 days)
```

---

## 30-Day History

```dataview
TABLE
  sleep_hours AS "Sleep (h)",
  hrv         AS "HRV (ms)",
  steps       AS "Steps",
  weight      AS "Weight (kg)"
FROM "Health"
WHERE date >= date(today) - dur(30 days)
SORT date DESC
```
