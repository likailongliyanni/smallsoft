<?php

namespace App\Services;

use App\Models\AiPattern;
use Illuminate\Support\Facades\Cache;

/**
 * 经验库（Knowledge Base）版本管理
 *
 * 每次经验包变更（新增/编辑/删除/启用切换）→ 版本号自动 bump +0.0.1
 * 客户端通过 GET /api/kb-version 拿到当前版本号，显示在首页
 */
class KbVersionService
{
    private const CACHE_KEY = 'kb_meta_v1';
    private const DEFAULT_VERSION = '1.0.0';

    /**
     * 当前版本元信息
     * 形如：{ version: "1.0.7", signature: "a1b2c3d4", updated_at: "...", count: 8, latest_change: "..." }
     *
     * 关键改造：
     *   每次调用 current() 都重新算一次 signature（文件 mtime + DB updated_at 的 hash）
     *   如果 signature 跟缓存里的不一样 → 自动把版本号 +0.0.1
     *   这样部署新经验后，无需手动 bump 就能让客户端感知到变化
     */
    public function current(): array
    {
        $stored = Cache::get(self::CACHE_KEY) ?: [
            'version' => self::DEFAULT_VERSION,
            'signature' => null,
            'updated_at' => null,
            'count' => 0,
            'latest_change' => null,
        ];

        $liveSig = $this->computeSignature();

        // 文件/数据库变了 → 自动 bump
        if (($stored['signature'] ?? null) !== $liveSig) {
            $stored['version'] = $this->bumpVersion($stored['version'] ?? self::DEFAULT_VERSION);
            $stored['signature'] = $liveSig;
            $stored['updated_at'] = now()->toIso8601String();
            $stored['count'] = $this->countEnabled();
            $stored['latest_change'] = $stored['latest_change'] ?: '检测到经验文件变更，自动升级';
            Cache::put(self::CACHE_KEY, $stored, now()->addYears(10));
        }

        return $stored;
    }

    /**
     * 算"内容指纹"：所有 .md 文件 mtime + 数据库经验 updated_at 的 MD5
     * 文件加一个字节 → 指纹变 → 版本号自动升
     */
    private function computeSignature(): string
    {
        $parts = [];

        $base = resource_path('prompts/patterns');
        if (is_dir($base)) {
            foreach (['common', 'browser', 'excel', 'word', 'ps', 'pdf'] as $cat) {
                $dir = $base . DIRECTORY_SEPARATOR . $cat;
                if (! is_dir($dir)) continue;
                $files = glob($dir . '/*.md');
                sort($files);
                foreach ($files as $f) {
                    if (basename($f) === 'README.md') continue;
                    $parts[] = $cat . '/' . basename($f) . ':' . filemtime($f) . ':' . filesize($f);
                }
            }
        }

        // 基础提示词文件也算进去
        $sysPrompt = resource_path('prompts/json_dsl_system.md');
        if (is_file($sysPrompt)) {
            $parts[] = 'sys:' . filemtime($sysPrompt) . ':' . filesize($sysPrompt);
        }

        // 数据库自定义经验
        try {
            if (\Schema::hasTable('ai_patterns')) {
                $rows = AiPattern::query()
                    ->orderBy('id')
                    ->get(['id', 'code', 'updated_at', 'enabled']);
                foreach ($rows as $p) {
                    $ts = optional($p->updated_at)->timestamp ?: 0;
                    $parts[] = 'db:' . $p->code . ':' . $ts . ':' . ($p->enabled ? '1' : '0');
                }
            }
        } catch (\Throwable $e) {
            // 表不存在时静默
        }

        return substr(md5(implode('|', $parts)), 0, 8);
    }

    private function countEnabled(): int
    {
        try {
            return AiPattern::query()->where('enabled', true)->count();
        } catch (\Throwable $e) {
            return 0;
        }
    }

    /**
     * 经验包变更后调用：版本号 +0.0.1，刷新元信息
     *
     * @param string|null $changeNote 本次变更说明，会显示给用户看
     */
    public function bump(?string $changeNote = null): array
    {
        $cur = $this->current();
        $version = $this->bumpVersion($cur['version'] ?: self::DEFAULT_VERSION);

        $meta = [
            'version' => $version,
            'signature' => $this->computeSignature(),
            'updated_at' => now()->toIso8601String(),
            'count' => $this->countEnabled(),
            'latest_change' => $changeNote,
        ];

        // 缓存 10 年，等于持久化（PHP cache file driver）
        Cache::put(self::CACHE_KEY, $meta, now()->addYears(10));

        return $meta;
    }

    /**
     * 把 "1.0.7" 变成 "1.0.8"
     */
    private function bumpVersion(string $v): string
    {
        $parts = array_map('intval', explode('.', $v));
        while (count($parts) < 3) {
            $parts[] = 0;
        }
        $parts[2] = ($parts[2] ?? 0) + 1;
        return implode('.', array_slice($parts, 0, 3));
    }

    /**
     * 设置具体版本（管理员强制修正用）
     */
    public function setVersion(string $version, ?string $changeNote = null): array
    {
        $meta = [
            'version' => $version,
            'signature' => $this->computeSignature(),
            'updated_at' => now()->toIso8601String(),
            'count' => $this->countEnabled(),
            'latest_change' => $changeNote,
        ];
        Cache::put(self::CACHE_KEY, $meta, now()->addYears(10));
        return $meta;
    }
}
