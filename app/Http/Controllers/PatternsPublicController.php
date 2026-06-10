<?php

namespace App\Http\Controllers;

use App\Models\AiPattern;
use App\Services\KbVersionService;
use Illuminate\Http\Request;

/**
 * 经验库公开接口（客户端同步用，无需 admin token）
 *
 * 客户端流程：
 *   1) GET /api/patterns/manifest → 轻量列表（含每条的 code + checksum）
 *   2) 对比本地缓存，找出缺失/变化的 code
 *   3) GET /api/patterns/{code} 单条拉取
 *   4) 写入本地 patterns.json
 *
 * 也支持一次性全量：
 *   GET /api/patterns/all
 *
 * 经验来源：
 *   - file: resources/prompts/patterns/*.md（内置默认）
 *   - db: ai_patterns 表（管理员通过 admin 后台添加/编辑）
 */
class PatternsPublicController extends Controller
{
    /**
     * 用容错 flag 输出 JSON，避免非法 UTF-8 字符报错
     */
    private function jsonResponse(array $data)
    {
        return response()->json(
            $data,
            200,
            ['Content-Type' => 'application/json; charset=utf-8'],
            JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE
        );
    }

    /** GET /api/patterns/manifest — 轻量元信息列表（同步前的检查） */
    public function manifest(KbVersionService $kb)
    {
        $patterns = $this->collectAll();

        $manifest = array_map(fn($p) => [
            'code' => $p['code'],
            'category' => $p['category'] ?? 'browser',
            'title' => $p['title'],
            'source' => $p['source'],
            'priority' => $p['priority'],
            'checksum' => md5($p['content']),
            'stamp' => $p['stamp'] ?? '',
            'updated_at' => $p['updated_at'] ?? '',
        ], $patterns);

        return $this->jsonResponse([
            'ok' => true,
            'kb_version' => $kb->current()['version'] ?? '1.0.0',
            'count' => count($manifest),
            'patterns' => $manifest,
        ]);
    }

    /** GET /api/patterns/all — 一次性全量拉取（小流量首选） */
    public function all(KbVersionService $kb)
    {
        $patterns = $this->collectAll();

        return $this->jsonResponse([
            'ok' => true,
            'kb_version' => $kb->current()['version'] ?? '1.0.0',
            'count' => count($patterns),
            'patterns' => $patterns,
        ]);
    }

    /** GET /api/patterns/{code} — 单条详情（增量补丁用） */
    public function show(string $code)
    {
        $patterns = $this->collectAll();
        foreach ($patterns as $p) {
            if ($p['code'] === $code) {
                return $this->jsonResponse(['ok' => true, 'pattern' => $p]);
            }
        }
        abort(404, '经验不存在：'.$code);
    }

    /**
     * 收集所有启用的经验（文件 + 数据库）
     * 文件按 prompts/patterns/{category}/ 子目录组织
     */
    private function collectAll(): array
    {
        $results = [];
        $patternsBase = resource_path('prompts/patterns');

        if (is_dir($patternsBase)) {
            // 已知的场景目录（按显示顺序）
            $categories = ['common', 'browser', 'excel', 'word', 'ps', 'pdf'];
            $priorityBase = 10;

            foreach ($categories as $cat) {
                $dir = $patternsBase . DIRECTORY_SEPARATOR . $cat;
                if (! is_dir($dir)) continue;
                $files = glob($dir . '/*.md');
                sort($files);
                foreach ($files as $i => $f) {
                    $baseName = basename($f);
                    if ($baseName === 'README.md') continue;

                    $code = pathinfo($f, PATHINFO_FILENAME);
                    $raw = (string) file_get_contents($f);
                    $content = $this->cleanUtf8($raw);
                    if ($content === '') continue;

                    $title = $code;
                    if (preg_match('/^###\s*模式?[：:]\s*(.+)$/m', $content, $m)) {
                        $title = $this->cleanUtf8(trim($m[1]));
                    } elseif (preg_match('/^###?\s+(.+)$/m', $content, $m)) {
                        $title = $this->cleanUtf8(trim($m[1]));
                    }

                    $mtime = filemtime($f);
                    $results[] = [
                        'code' => $this->cleanUtf8($code),
                        'category' => $cat,
                        'title' => $title,
                        'content' => $content,
                        'source' => 'builtin',
                        'priority' => $priorityBase + $i,
                        'updated_at' => date('c', $mtime),
                        'stamp' => $this->makeStamp($mtime, $content, $i + 1),  // 时间戳指纹
                    ];
                }
                $priorityBase += 100;  // 每个分类后续 priority 留空间
            }
        }

        // 数据库经验包
        try {
            if (\Schema::hasTable('ai_patterns')) {
                $dbItems = AiPattern::query()
                    ->where('enabled', true)
                    ->orderBy('priority')
                    ->orderBy('id')
                    ->get();
                foreach ($dbItems as $idx => $p) {
                    $ts = optional($p->updated_at)->timestamp ?: time();
                    $results[] = [
                        'code' => $this->cleanUtf8((string) $p->code),
                        'category' => $this->cleanUtf8((string) ($p->category ?? 'browser')),
                        'title' => $this->cleanUtf8((string) $p->title),
                        'content' => $this->cleanUtf8((string) $p->content),
                        'source' => 'custom',
                        'priority' => 1000 + (int) $p->priority,
                        'updated_at' => optional($p->updated_at)->toIso8601String(),
                        'stamp' => $this->makeStamp($ts, (string) $p->content, $p->id),
                    ];
                }
            }
        } catch (\Throwable $e) {
            // 表还没创建时静默
        }

        return $results;
    }

    /**
     * 生成"时间戳指纹"：让管理员一眼看出经验是哪个时间点的版本
     * 格式：YYYY-MMDD-HHmm-NNN
     *   - 前面是文件 mtime / DB updated_at
     *   - 末尾 NNN = 内容 md5 的前 3 个 hex 字符（同一时刻不同经验也能区分）
     * 示例：2026-0525-2143-a1b
     */
    private function makeStamp(int $ts, string $content, int $serial = 0): string
    {
        $date = date('Y-md', $ts);
        $time = date('Hi', $ts);
        $suffix = substr(md5($content . '|' . $serial), 0, 3);
        return "{$date}-{$time}-{$suffix}";
    }

    /**
     * 清理字符串：去 BOM + 仅在必要时修复非法 UTF-8
     * （保护合法 emoji 不被误伤）
     */
    private function cleanUtf8(string $s): string
    {
        if ($s === '') return $s;
        // 去 UTF-8 BOM
        $s = preg_replace('/^(?:\xEF\xBB\xBF)+/', '', $s) ?? $s;
        // 统一行尾
        $s = str_replace("\r\n", "\n", $s);
        // 只在字符串确实有非法 UTF-8 字节时才修复（避免动到合法 emoji）
        if (! mb_check_encoding($s, 'UTF-8')) {
            if (function_exists('mb_scrub')) {
                $s = mb_scrub($s, 'UTF-8');
            } else {
                $s = (string) iconv('UTF-8', 'UTF-8//IGNORE', $s);
            }
        }
        return trim($s);
    }
}
