-- ResolveAI SQL analysis
-- Source: resolveai.db (24 mock orders and local prototype interactions)

-- 1. How many orders are in each status?
SELECT
    status,
    COUNT(*) AS order_count
FROM orders
GROUP BY status
ORDER BY status;

-- 2. What is the count and amount profile of each status?
SELECT
    status,
    COUNT(*) AS order_count,
    ROUND(SUM(amount), 2) AS total_amount,
    ROUND(AVG(amount), 2) AS average_amount
FROM orders
GROUP BY status
ORDER BY status;

-- 3. Which order facts are associated with each recorded interaction?
SELECT
    i.id AS interaction_id,
    i.created_at,
    i.order_id,
    o.status,
    o.amount,
    o.has_shipped,
    o.refunded,
    i.action,
    i.result
FROM interactions AS i
JOIN orders AS o
    ON o.order_id = i.order_id
ORDER BY i.id;

-- 4. What distinct outcomes were recorded for PROCESS_REFUND?
-- Underscores do not need escaping when using equality (=).
SELECT DISTINCT
    result
FROM interactions
WHERE action = 'PROCESS_REFUND'
ORDER BY result;

-- 5. Data consistency audit:
-- Every order with a successful simulated-refund interaction should now be refunded.
SELECT DISTINCT
    i.order_id,
    o.status,
    o.refunded,
    i.result,
    CASE
        WHEN o.refunded = 1 THEN 'CONSISTENT'
        ELSE 'INCONSISTENT'
    END AS audit_status
FROM interactions AS i
JOIN orders AS o
    ON o.order_id = i.order_id
WHERE i.action = 'PROCESS_REFUND'
  AND i.result = 'SIMULATED_REFUND_COMPLETED'
ORDER BY i.order_id;
