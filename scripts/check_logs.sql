-- 사용자 역할
SELECT
    id AS user_id,
    username,
    role
FROM users
ORDER BY id ASC;

-- 최근 ChatExchange
SELECT
    id AS chat_exchange_id,
    user_id,
    status,
    created_at,
    request_id
FROM chat_exchanges
ORDER BY created_at DESC, id DESC
LIMIT 20;

-- 실패 ChatExchange 불변식
SELECT
    id,
    user_id,
    status,
    answer IS NULL AS answer_is_null,
    request_id,
    error_code,
    created_at
FROM chat_exchanges
WHERE status = 'failed'
ORDER BY created_at DESC;

-- 사용자별 ChatExchange 수
SELECT
    u.id AS user_id,
    u.username,
    COUNT(c.id) AS chat_exchange_count
FROM users AS u
LEFT JOIN chat_exchanges AS c ON c.user_id = u.id
GROUP BY u.id, u.username
ORDER BY u.id ASC;

-- 운영 metadata
SELECT
    id AS chat_exchange_id,
    user_id,
    created_at,
    request_id,
    user_agent,
    response_time_ms,
    status,
    error_code
FROM chat_exchanges
ORDER BY created_at DESC, id DESC;

-- Admin 9-field projection
SELECT
    c.user_id,
    u.username,
    c.id AS chat_exchange_id,
    c.created_at,
    c.request_id,
    c.user_agent,
    c.response_time_ms,
    c.status,
    c.error_code
FROM chat_exchanges AS c
LEFT JOIN users AS u ON u.id = c.user_id
ORDER BY c.created_at DESC, c.id DESC;
