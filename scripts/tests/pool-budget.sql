-- Read-only operational inventory. Run with a monitoring role that can see pg_stat_activity.
-- No SQL text, credentials or session tokens are returned.
BEGIN READ ONLY;
SELECT clock_timestamp() AS checked_at, datname, usename, application_name,
       client_addr, state, count(*) AS connections,
       max(clock_timestamp() - xact_start) AS oldest_transaction_age
FROM pg_stat_activity
WHERE backend_type = 'client backend'
  AND datname = current_database()
GROUP BY datname, usename, application_name, client_addr, state
ORDER BY client_addr, usename, application_name, state;
COMMIT;
-- Compare task ENI addresses with ECS task inventory, not EC2 host addresses.
-- Conservative rolling ceiling: API16 x (business2+counter1) + worker2 x pool1 + publisher2 x pool1 + maintenance1 + reserve12 =65 <= budget66.
-- Exclude migration/operator/monitoring clients explicitly; do not assume total DB connections == app pool.
-- An empty result is not proof of a drain; correlate with ingress/app request completion and policy lock.

-- Lock wait inventory without query text or application parameters.
SELECT wait_event_type, wait_event, count(*) AS sessions
FROM pg_stat_activity
WHERE datname=current_database() AND wait_event_type='Lock'
GROUP BY wait_event_type, wait_event;
