-- Resilient Swarm Maestro: Tiger Data (TimescaleDB) queries over swarm_telemetry.
-- One row is written per beat by hub/ai_services.py (TelemetryStore).
-- Run with:  psql "$TIGER_DB_URL" -f hub/tiger_queries.sql
-- Queries 1 and 2 are what GET /api/history serves (combined into one statement there).

-- 1. Delivery % per 10 s: share of beats whose packet got through the loss injector.
SELECT time_bucket('10 seconds', time)                              AS bucket,
       round(100.0 * count(*) FILTER (WHERE delivered) / count(*))  AS delivery_pct,
       count(*)                                                     AS packets
FROM swarm_telemetry
WHERE time > now() - INTERVAL '15 minutes'
GROUP BY bucket
ORDER BY bucket;

-- 2. Average phase drift (beats between the swarm and the physical robot) per 10 s.
SELECT time_bucket('10 seconds', time)        AS bucket,
       round(avg(phase_drift)::numeric, 2)    AS avg_phase_drift,
       max(phase_drift)                       AS max_phase_drift
FROM swarm_telemetry
WHERE time > now() - INTERVAL '15 minutes'
GROUP BY bucket
ORDER BY bucket;

-- 3. Packets per rule per 10 s, with how many were dropped.
SELECT time_bucket('10 seconds', time)            AS bucket,
       rule,
       count(*)                                   AS packets,
       count(*) FILTER (WHERE NOT delivered)      AS dropped
FROM swarm_telemetry
WHERE time > now() - INTERVAL '15 minutes'
GROUP BY bucket, rule
ORDER BY bucket, rule;

-- 4. Blackout seconds per 10 s bucket. Each row is one beat, so a beat is worth 60/bpm seconds.
SELECT time_bucket('10 seconds', time)                                      AS bucket,
       round(sum(60.0 / bpm) FILTER (WHERE blackout)::numeric, 1)           AS blackout_seconds
FROM swarm_telemetry
WHERE time > now() - INTERVAL '15 minutes'
GROUP BY bucket
HAVING count(*) FILTER (WHERE blackout) > 0
ORDER BY bucket;

-- 4b. Total blackout seconds over the same 15 minutes (one number for the pitch).
SELECT coalesce(round(sum(60.0 / bpm) FILTER (WHERE blackout)::numeric, 1), 0) AS blackout_seconds
FROM swarm_telemetry
WHERE time > now() - INTERVAL '15 minutes';
