CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(64) NOT NULL UNIQUE,
    email VARCHAR(191) NOT NULL DEFAULT '',
    password_hash VARCHAR(255) NOT NULL,
    free_generations INT NOT NULL DEFAULT 1,
    paid_generations INT NOT NULL DEFAULT 0,
    status ENUM('active','disabled') NOT NULL DEFAULT 'active',
    note VARCHAR(500) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NULL,
    INDEX idx_users_status (status),
    INDEX idx_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_tokens (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_tokens_user (user_id),
    INDEX idx_user_tokens_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_tokens (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    INDEX idx_admin_tokens_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS model_config (
    id TINYINT UNSIGNED PRIMARY KEY,
    provider VARCHAR(64) NOT NULL DEFAULT 'openai-compatible',
    base_url VARCHAR(255) NOT NULL DEFAULT '',
    model_name VARCHAR(128) NOT NULL DEFAULT '',
    api_key TEXT NULL,
    updated_at DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO model_config (id, provider, base_url, model_name, api_key, updated_at)
VALUES (1, 'openai-compatible', '', '', '', NULL);

CREATE TABLE IF NOT EXISTS generation_jobs (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    status ENUM('running','succeeded','failed','mock') NOT NULL DEFAULT 'running',
    target_url VARCHAR(500) NOT NULL DEFAULT '',
    workflow_json LONGTEXT NOT NULL,
    excel_schema_json LONGTEXT NOT NULL,
    result_script LONGTEXT NULL,
    error TEXT NULL,
    quota_consumed TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_jobs_user (user_id),
    INDEX idx_jobs_status (status),
    INDEX idx_jobs_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS training_submissions (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NULL,
    product_name VARCHAR(191) NOT NULL,
    category VARCHAR(191) NOT NULL,
    brand VARCHAR(191) NOT NULL,
    price VARCHAR(64) NOT NULL,
    detail TEXT NOT NULL,
    image_name VARCHAR(255) NOT NULL DEFAULT '',
    image_size INT NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    INDEX idx_training_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS orders (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    order_no VARCHAR(64) NOT NULL UNIQUE,
    plan_name VARCHAR(128) NOT NULL DEFAULT '',
    amount_cents INT NOT NULL DEFAULT 0,
    generation_count INT NOT NULL DEFAULT 0,
    status ENUM('pending','paid','cancelled','refunded') NOT NULL DEFAULT 'pending',
    payment_method VARCHAR(64) NOT NULL DEFAULT 'manual',
    note VARCHAR(500) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL,
    paid_at DATETIME NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_orders_user (user_id),
    INDEX idx_orders_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS quota_logs (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    delta_free INT NOT NULL DEFAULT 0,
    delta_paid INT NOT NULL DEFAULT 0,
    reason VARCHAR(255) NOT NULL DEFAULT '',
    admin_note VARCHAR(500) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_quota_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS feedback_logs (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NULL,
    job_id BIGINT UNSIGNED NULL,
    level ENUM('info','warning','error') NOT NULL DEFAULT 'error',
    message TEXT NOT NULL,
    payload_json LONGTEXT NULL,
    created_at DATETIME NOT NULL,
    INDEX idx_feedback_user (user_id),
    INDEX idx_feedback_job (job_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
