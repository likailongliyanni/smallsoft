<?php
function app_config(?string $key = null, mixed $default = null): mixed
{
    global $APP_CONFIG;
    if ($key === null) {
        return $APP_CONFIG;
    }
    return $APP_CONFIG[$key] ?? $default;
}

function db(): PDO
{
    return Database::connection();
}

function now_sql(): string
{
    return date('Y-m-d H:i:s');
}

function json_input(): array
{
    $raw = file_get_contents('php://input');
    if ($raw === '' || $raw === false) {
        return [];
    }
    $data = json_decode($raw, true);
    if (!is_array($data)) {
        throw new HttpException('invalid json body', 400);
    }
    return $data;
}

function json_response(array $data, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function ok(array $data = []): void
{
    json_response(['ok' => true] + $data);
}

function fail(string $message, int $status = 400): void
{
    json_response(['ok' => false, 'error' => $message], $status);
}

function require_method(string $method): void
{
    if (strtoupper($_SERVER['REQUEST_METHOD'] ?? '') !== strtoupper($method)) {
        throw new HttpException('method not allowed', 405);
    }
}

function require_fields(array $data, array $fields): void
{
    foreach ($fields as $field) {
        if (!isset($data[$field]) || trim((string)$data[$field]) === '') {
            throw new HttpException("missing field: {$field}", 400);
        }
    }
}

function random_token(): string
{
    return rtrim(strtr(base64_encode(random_bytes(36)), '+/', '-_'), '=');
}

function token_hash(string $token): string
{
    return hash('sha256', $token);
}

function bearer_token(): string
{
    $header = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
    if (!$header && function_exists('getallheaders')) {
        $headers = getallheaders();
        $header = $headers['Authorization'] ?? $headers['authorization'] ?? '';
    }
    if (!preg_match('/^Bearer\s+(.+)$/i', $header, $matches)) {
        throw new HttpException('missing token', 401);
    }
    return trim($matches[1]);
}

function current_user(): array
{
    $tokenHash = token_hash(bearer_token());
    $stmt = db()->prepare(
        'SELECT users.* FROM user_tokens
         JOIN users ON users.id = user_tokens.user_id
         WHERE user_tokens.token_hash = ? AND user_tokens.expires_at > NOW()
         LIMIT 1'
    );
    $stmt->execute([$tokenHash]);
    $user = $stmt->fetch();
    if (!$user) {
        throw new HttpException('invalid token', 401);
    }
    if (($user['status'] ?? '') !== 'active') {
        throw new HttpException('account disabled', 403);
    }
    return $user;
}

function optional_user_id(): ?int
{
    try {
        return (int)current_user()['id'];
    } catch (Throwable $e) {
        return null;
    }
}

function require_admin(): void
{
    $tokenHash = token_hash(bearer_token());
    $stmt = db()->prepare('SELECT id FROM admin_tokens WHERE token_hash = ? AND expires_at > NOW() LIMIT 1');
    $stmt->execute([$tokenHash]);
    if (!$stmt->fetch()) {
        throw new HttpException('invalid admin token', 403);
    }
}

function public_user(array $user): array
{
    $free = (int)($user['free_generations'] ?? 0);
    $paid = (int)($user['paid_generations'] ?? 0);
    return [
        'id' => (int)$user['id'],
        'username' => $user['username'],
        'email' => $user['email'] ?? '',
        'free_generations' => $free,
        'paid_generations' => $paid,
        'remaining_generations' => $free + $paid,
        'status' => $user['status'] ?? 'active',
        'created_at' => $user['created_at'] ?? '',
    ];
}

function clean_text(mixed $value, int $max = 500): string
{
    $text = trim((string)$value);
    if (mb_strlen($text, 'UTF-8') > $max) {
        return mb_substr($text, 0, $max, 'UTF-8');
    }
    return $text;
}

function order_no(): string
{
    return 'WA' . date('YmdHis') . random_int(1000, 9999);
}
