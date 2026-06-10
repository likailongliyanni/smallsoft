<?php
declare(strict_types=1);

require_once __DIR__ . '/../app/bootstrap.php';

try {
    $action = $_GET['action'] ?? '';
    match ($action) {
        'auth.register' => api_register(),
        'auth.login' => api_login(),
        'me' => api_me(),
        'usage' => api_usage(),
        'training.submit' => api_training_submit(),
        'ai.generate' => api_ai_generate(),
        'feedback.create' => api_feedback_create(),
        'orders.mine' => api_orders_mine(),
        'admin.login' => api_admin_login(),
        'admin.logout' => api_admin_logout(),
        'admin.me' => api_admin_me(),
        'admin.stats' => api_admin_stats(),
        'admin.users' => api_admin_users(),
        'admin.user.update' => api_admin_user_update(),
        'admin.quota.add' => api_admin_quota_add(),
        'admin.model.get' => api_admin_model_get(),
        'admin.model.save' => api_admin_model_save(),
        'admin.model.test' => api_admin_model_test(),
        'admin.jobs' => api_admin_jobs(),
        'admin.orders' => api_admin_orders(),
        'admin.order.create' => api_admin_order_create(),
        'admin.feedback' => api_admin_feedback(),
        default => throw new HttpException('unknown action', 404),
    };
} catch (HttpException $e) {
    fail($e->getMessage(), $e->statusCode);
} catch (Throwable $e) {
    fail($e->getMessage(), 500);
}

function create_user_token(int $userId): string
{
    $token = random_token();
    $days = (int)app_config('token_days', 30);
    $stmt = db()->prepare('INSERT INTO user_tokens (user_id, token_hash, expires_at, created_at) VALUES (?, ?, DATE_ADD(NOW(), INTERVAL ? DAY), ?)');
    $stmt->execute([$userId, token_hash($token), $days, now_sql()]);
    return $token;
}

function api_register(): void
{
    require_method('POST');
    $data = json_input();
    require_fields($data, ['username', 'password']);
    $username = clean_text($data['username'], 64);
    $password = (string)$data['password'];
    if (mb_strlen($username, 'UTF-8') < 3) {
        throw new HttpException('username too short', 400);
    }
    if (strlen($password) < 6) {
        throw new HttpException('password too short', 400);
    }
    $email = clean_text($data['email'] ?? '', 191);
    $free = (int)app_config('free_generations', 1);
    $pdo = db();
    try {
        $stmt = $pdo->prepare(
            'INSERT INTO users (username, email, password_hash, free_generations, paid_generations, status, created_at)
             VALUES (?, ?, ?, ?, 0, "active", ?)'
        );
        $stmt->execute([$username, $email, password_hash($password, PASSWORD_DEFAULT), $free, now_sql()]);
    } catch (PDOException $e) {
        throw new HttpException('username already exists', 400);
    }
    $userId = (int)$pdo->lastInsertId();
    $user = $pdo->query('SELECT * FROM users WHERE id = ' . $userId)->fetch();
    ok(['token' => create_user_token($userId), 'user' => public_user($user)]);
}

function api_login(): void
{
    require_method('POST');
    $data = json_input();
    require_fields($data, ['username', 'password']);
    $stmt = db()->prepare('SELECT * FROM users WHERE username = ? LIMIT 1');
    $stmt->execute([clean_text($data['username'], 64)]);
    $user = $stmt->fetch();
    if (!$user || !password_verify((string)$data['password'], $user['password_hash'])) {
        throw new HttpException('invalid username or password', 401);
    }
    if ($user['status'] !== 'active') {
        throw new HttpException('account disabled', 403);
    }
    ok(['token' => create_user_token((int)$user['id']), 'user' => public_user($user)]);
}

function api_me(): void
{
    require_method('GET');
    ok(['user' => public_user(current_user())]);
}

function api_usage(): void
{
    require_method('GET');
    $user = current_user();
    $stmt = db()->prepare('SELECT COUNT(*) AS count FROM generation_jobs WHERE user_id = ?');
    $stmt->execute([$user['id']]);
    ok(['user' => public_user($user), 'generation_jobs' => (int)$stmt->fetch()['count']]);
}

function api_training_submit(): void
{
    require_method('POST');
    $payload = [
        'product_name' => clean_text($_POST['product_name'] ?? '', 191),
        'category' => clean_text($_POST['category'] ?? '', 191),
        'brand' => clean_text($_POST['brand'] ?? '', 191),
        'price' => clean_text($_POST['price'] ?? '', 64),
        'detail' => clean_text($_POST['detail'] ?? '', 5000),
    ];
    require_fields($payload, ['product_name', 'category', 'brand', 'price', 'detail']);
    $imageName = '';
    $imageSize = 0;
    if (isset($_FILES['image']) && is_uploaded_file($_FILES['image']['tmp_name'])) {
        $imageSize = (int)$_FILES['image']['size'];
        if ($imageSize > 512 * 1024) {
            throw new HttpException('image too large; please compress it first', 400);
        }
        $imageName = basename((string)$_FILES['image']['name']);
        $uploadDir = __DIR__ . '/../storage/uploads';
        if (!is_dir($uploadDir)) {
            mkdir($uploadDir, 0755, true);
        }
        $safeName = date('YmdHis') . '_' . bin2hex(random_bytes(4)) . '_' . preg_replace('/[^a-zA-Z0-9._-]/', '_', $imageName);
        move_uploaded_file($_FILES['image']['tmp_name'], $uploadDir . '/' . $safeName);
    }
    $stmt = db()->prepare(
        'INSERT INTO training_submissions
         (user_id, product_name, category, brand, price, detail, image_name, image_size, payload_json, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
    );
    $stmt->execute([
        optional_user_id(),
        $payload['product_name'],
        $payload['category'],
        $payload['brand'],
        $payload['price'],
        $payload['detail'],
        $imageName,
        $imageSize,
        json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
        now_sql(),
    ]);
    ok(['id' => (int)db()->lastInsertId(), 'image_size' => $imageSize]);
}

function api_ai_generate(): void
{
    require_method('POST');
    $user = current_user();
    $remaining = (int)$user['free_generations'] + (int)$user['paid_generations'];
    if ($remaining <= 0) {
        throw new HttpException('no remaining generation quota', 402);
    }
    $data = json_input();
    $workflow = $data['workflow'] ?? null;
    if (!is_array($workflow)) {
        throw new HttpException('workflow is required', 400);
    }
    $excelSchema = is_array($data['excel_schema'] ?? null) ? $data['excel_schema'] : [];
    $targetUrl = clean_text($workflow['url'] ?? '', 500);
    $model = db()->query('SELECT * FROM model_config WHERE id = 1')->fetch() ?: [];
    $stmt = db()->prepare(
        'INSERT INTO generation_jobs (user_id, status, target_url, workflow_json, excel_schema_json, created_at)
         VALUES (?, "running", ?, ?, ?, ?)'
    );
    $stmt->execute([
        $user['id'],
        $targetUrl,
        json_encode($workflow, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
        json_encode($excelSchema, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
        now_sql(),
    ]);
    $jobId = (int)db()->lastInsertId();

    try {
        $modelReady = AiService::isReady($model);
        $script = AiService::generate($model, $workflow, $excelSchema);
        $status = $modelReady ? 'succeeded' : 'mock';
        $error = '';
    } catch (Throwable $e) {
        $script = '';
        $status = 'failed';
        $error = $e->getMessage();
    }

    $quotaConsumed = 0;
    $pdo = db();
    $pdo->beginTransaction();
    try {
        if ($status === 'succeeded') {
            if ((int)$user['free_generations'] > 0) {
                $pdo->prepare('UPDATE users SET free_generations = free_generations - 1, updated_at = ? WHERE id = ?')->execute([now_sql(), $user['id']]);
            } else {
                $pdo->prepare('UPDATE users SET paid_generations = paid_generations - 1, updated_at = ? WHERE id = ?')->execute([now_sql(), $user['id']]);
            }
            $quotaConsumed = 1;
        }
        $pdo->prepare(
            'UPDATE generation_jobs SET status = ?, result_script = ?, error = ?, quota_consumed = ?, updated_at = ? WHERE id = ?'
        )->execute([$status, $script, $error, $quotaConsumed, now_sql(), $jobId]);
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        throw $e;
    }
    if ($status === 'failed') {
        throw new HttpException($error, 500);
    }
    ok(['job_id' => $jobId, 'script' => $script, 'mock' => $status === 'mock', 'quota_consumed' => (bool)$quotaConsumed]);
}

function api_feedback_create(): void
{
    require_method('POST');
    $userId = optional_user_id();
    $data = json_input();
    $stmt = db()->prepare(
        'INSERT INTO feedback_logs (user_id, job_id, level, message, payload_json, created_at)
         VALUES (?, ?, ?, ?, ?, ?)'
    );
    $stmt->execute([
        $userId,
        isset($data['job_id']) ? (int)$data['job_id'] : null,
        in_array(($data['level'] ?? 'error'), ['info', 'warning', 'error'], true) ? $data['level'] : 'error',
        clean_text($data['message'] ?? '', 5000),
        json_encode($data['payload'] ?? [], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
        now_sql(),
    ]);
    ok(['id' => (int)db()->lastInsertId()]);
}

function api_orders_mine(): void
{
    require_method('GET');
    $user = current_user();
    $stmt = db()->prepare('SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 100');
    $stmt->execute([$user['id']]);
    ok(['orders' => $stmt->fetchAll()]);
}

function api_admin_login(): void
{
    require_method('POST');
    $data = json_input();
    if (($data['password'] ?? '') !== app_config('admin_password')) {
        throw new HttpException('invalid admin password', 401);
    }
    $token = random_token();
    $hours = (int)app_config('admin_token_hours', 12);
    $stmt = db()->prepare('INSERT INTO admin_tokens (token_hash, expires_at, created_at) VALUES (?, DATE_ADD(NOW(), INTERVAL ? HOUR), ?)');
    $stmt->execute([token_hash($token), $hours, now_sql()]);
    ok(['token' => $token]);
}

function api_admin_logout(): void
{
    require_method('POST');
    require_admin();
    $stmt = db()->prepare('DELETE FROM admin_tokens WHERE token_hash = ?');
    $stmt->execute([token_hash(bearer_token())]);
    ok();
}

function api_admin_me(): void
{
    require_admin();
    ok();
}

function api_admin_stats(): void
{
    require_admin();
    $pdo = db();
    $stats = [
        'users' => (int)$pdo->query('SELECT COUNT(*) AS c FROM users')->fetch()['c'],
        'active_users' => (int)$pdo->query('SELECT COUNT(*) AS c FROM users WHERE status="active"')->fetch()['c'],
        'generation_jobs' => (int)$pdo->query('SELECT COUNT(*) AS c FROM generation_jobs')->fetch()['c'],
        'succeeded_jobs' => (int)$pdo->query('SELECT COUNT(*) AS c FROM generation_jobs WHERE status="succeeded"')->fetch()['c'],
        'training_submissions' => (int)$pdo->query('SELECT COUNT(*) AS c FROM training_submissions')->fetch()['c'],
        'paid_orders' => (int)$pdo->query('SELECT COUNT(*) AS c FROM orders WHERE status="paid"')->fetch()['c'],
    ];
    ok($stats);
}

function api_admin_users(): void
{
    require_admin();
    $query = clean_text($_GET['query'] ?? '', 100);
    $limit = max(1, min(200, (int)($_GET['limit'] ?? 50)));
    $where = '';
    $params = [];
    if ($query !== '') {
        $where = 'WHERE users.username LIKE ? OR users.email LIKE ?';
        $params = ["%{$query}%", "%{$query}%"];
    }
    $totalStmt = db()->prepare("SELECT COUNT(*) AS c FROM users {$where}");
    $totalStmt->execute($params);
    $stmt = db()->prepare(
        "SELECT users.id, users.username, users.email, users.free_generations, users.paid_generations,
                users.status, users.note, users.created_at, users.updated_at,
                COALESCE(job_stats.job_count, 0) AS job_count
         FROM users
         LEFT JOIN (
            SELECT user_id, COUNT(*) AS job_count FROM generation_jobs GROUP BY user_id
         ) job_stats ON job_stats.user_id = users.id
         {$where}
         ORDER BY users.id DESC
         LIMIT {$limit}"
    );
    $stmt->execute($params);
    $users = $stmt->fetchAll();
    foreach ($users as &$user) {
        $user['remaining_generations'] = (int)$user['free_generations'] + (int)$user['paid_generations'];
    }
    ok(['total' => (int)$totalStmt->fetch()['c'], 'users' => $users]);
}

function api_admin_user_update(): void
{
    require_method('POST');
    require_admin();
    $data = json_input();
    $userId = (int)($data['user_id'] ?? 0);
    if ($userId <= 0) {
        throw new HttpException('user_id required', 400);
    }
    $status = $data['status'] ?? 'active';
    if (!in_array($status, ['active', 'disabled'], true)) {
        throw new HttpException('invalid status', 400);
    }
    $stmt = db()->prepare(
        'UPDATE users SET email = ?, free_generations = ?, paid_generations = ?, status = ?, note = ?, updated_at = ? WHERE id = ?'
    );
    $stmt->execute([
        clean_text($data['email'] ?? '', 191),
        max(0, (int)($data['free_generations'] ?? 0)),
        max(0, (int)($data['paid_generations'] ?? 0)),
        $status,
        clean_text($data['note'] ?? '', 500),
        now_sql(),
        $userId,
    ]);
    ok();
}

function api_admin_quota_add(): void
{
    require_method('POST');
    require_admin();
    $data = json_input();
    $userId = (int)($data['user_id'] ?? 0);
    $paid = (int)($data['paid_generations'] ?? 0);
    $free = (int)($data['free_generations'] ?? 0);
    if ($userId <= 0 || ($paid === 0 && $free === 0)) {
        throw new HttpException('invalid quota change', 400);
    }
    $pdo = db();
    $pdo->beginTransaction();
    try {
        $pdo->prepare(
            'UPDATE users SET paid_generations = paid_generations + ?, free_generations = free_generations + ?, updated_at = ? WHERE id = ?'
        )->execute([$paid, $free, now_sql(), $userId]);
        $pdo->prepare(
            'INSERT INTO quota_logs (user_id, delta_free, delta_paid, reason, admin_note, created_at) VALUES (?, ?, ?, ?, ?, ?)'
        )->execute([$userId, $free, $paid, clean_text($data['reason'] ?? 'manual', 255), clean_text($data['note'] ?? '', 500), now_sql()]);
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        throw $e;
    }
    ok();
}

function api_admin_model_get(): void
{
    require_admin();
    $model = db()->query('SELECT * FROM model_config WHERE id = 1')->fetch() ?: [];
    ok([
        'provider' => $model['provider'] ?? '',
        'base_url' => $model['base_url'] ?? '',
        'model_name' => $model['model_name'] ?? '',
        'api_key_set' => trim((string)($model['api_key'] ?? '')) !== '',
        'updated_at' => $model['updated_at'] ?? '',
    ]);
}

function api_admin_model_save(): void
{
    require_method('POST');
    require_admin();
    $data = json_input();
    $model = db()->query('SELECT * FROM model_config WHERE id = 1')->fetch() ?: [];
    $apiKey = $model['api_key'] ?? '';
    if (!empty($data['clear_api_key'])) {
        $apiKey = '';
    } elseif (trim((string)($data['api_key'] ?? '')) !== '') {
        $apiKey = trim((string)$data['api_key']);
    }
    $stmt = db()->prepare('UPDATE model_config SET provider = ?, base_url = ?, model_name = ?, api_key = ?, updated_at = ? WHERE id = 1');
    $stmt->execute([
        clean_text($data['provider'] ?? 'openai-compatible', 64),
        clean_text($data['base_url'] ?? '', 255),
        clean_text($data['model_name'] ?? '', 128),
        $apiKey,
        now_sql(),
    ]);
    ok();
}

function api_admin_model_test(): void
{
    require_method('POST');
    require_admin();
    $model = db()->query('SELECT * FROM model_config WHERE id = 1')->fetch() ?: [];
    ok(['message' => AiService::test($model)]);
}

function api_admin_jobs(): void
{
    require_admin();
    $limit = max(1, min(200, (int)($_GET['limit'] ?? 50)));
    $stmt = db()->query(
        "SELECT generation_jobs.id, generation_jobs.status, generation_jobs.target_url, generation_jobs.error,
                generation_jobs.quota_consumed, generation_jobs.created_at, users.username,
                CHAR_LENGTH(generation_jobs.result_script) AS script_size
         FROM generation_jobs
         JOIN users ON users.id = generation_jobs.user_id
         ORDER BY generation_jobs.id DESC
         LIMIT {$limit}"
    );
    ok(['jobs' => $stmt->fetchAll()]);
}

function api_admin_orders(): void
{
    require_admin();
    $stmt = db()->query(
        'SELECT orders.*, users.username FROM orders JOIN users ON users.id = orders.user_id ORDER BY orders.id DESC LIMIT 100'
    );
    ok(['orders' => $stmt->fetchAll()]);
}

function api_admin_order_create(): void
{
    require_method('POST');
    require_admin();
    $data = json_input();
    $userId = (int)($data['user_id'] ?? 0);
    $count = max(0, (int)($data['generation_count'] ?? 0));
    $status = in_array(($data['status'] ?? 'paid'), ['pending', 'paid', 'cancelled', 'refunded'], true) ? $data['status'] : 'paid';
    if ($userId <= 0 || $count <= 0) {
        throw new HttpException('invalid order', 400);
    }
    $pdo = db();
    $pdo->beginTransaction();
    try {
        $stmt = $pdo->prepare(
            'INSERT INTO orders (user_id, order_no, plan_name, amount_cents, generation_count, status, payment_method, note, created_at, paid_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
        );
        $stmt->execute([
            $userId,
            order_no(),
            clean_text($data['plan_name'] ?? '人工加次数', 128),
            max(0, (int)($data['amount_cents'] ?? 0)),
            $count,
            $status,
            clean_text($data['payment_method'] ?? 'manual', 64),
            clean_text($data['note'] ?? '', 500),
            now_sql(),
            $status === 'paid' ? now_sql() : null,
        ]);
        if ($status === 'paid') {
            $pdo->prepare('UPDATE users SET paid_generations = paid_generations + ?, updated_at = ? WHERE id = ?')->execute([$count, now_sql(), $userId]);
            $pdo->prepare(
                'INSERT INTO quota_logs (user_id, delta_paid, reason, admin_note, created_at) VALUES (?, ?, "manual_order", ?, ?)'
            )->execute([$userId, $count, clean_text($data['note'] ?? '', 500), now_sql()]);
        }
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        throw $e;
    }
    ok();
}

function api_admin_feedback(): void
{
    require_admin();
    $stmt = db()->query(
        'SELECT feedback_logs.*, users.username FROM feedback_logs
         LEFT JOIN users ON users.id = feedback_logs.user_id
         ORDER BY feedback_logs.id DESC LIMIT 100'
    );
    ok(['feedback' => $stmt->fetchAll()]);
}
