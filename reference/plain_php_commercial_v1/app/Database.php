<?php
class Database
{
    private static ?PDO $pdo = null;

    public static function connection(): PDO
    {
        if (self::$pdo instanceof PDO) {
            return self::$pdo;
        }
        $config = app_config('db');
        $host = $config['host'] ?? '127.0.0.1';
        $port = (int)($config['port'] ?? 3306);
        $database = $config['database'] ?? '';
        $charset = $config['charset'] ?? 'utf8mb4';
        $dsn = "mysql:host={$host};port={$port};dbname={$database};charset={$charset}";
        self::$pdo = new PDO($dsn, $config['username'] ?? '', $config['password'] ?? '', [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]);
        return self::$pdo;
    }
}
