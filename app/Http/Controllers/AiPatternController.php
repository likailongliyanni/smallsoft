<?php

namespace App\Http\Controllers;

use App\Models\AiPattern;
use App\Services\AiScriptService;
use App\Services\KbVersionService;
use App\Services\TokenService;
use Illuminate\Http\Request;
use Illuminate\Support\Str;

// （文件内辅助方法，避免重复造）

/**
 * AI 经验包管理（学习文件）
 *
 * 设计哲学：
 *   - 管理员不需要懂技术细节
 *   - 流程：用户报错 → 找 Claude 写经验 → 粘贴 → 保存
 *   - 任何修改自动 bump 经验库版本号（用户能看到）
 */
class AiPatternController extends Controller
{
    /** GET /api/admin/ai-patterns — 列出所有经验包（文件内置 + 数据库自定义） */
    public function index(Request $request, TokenService $tokens, KbVersionService $kb): array
    {
        $admin = $tokens->adminFromRequest($request);
        abort_if(! $admin, 401, '管理员未登录');

        $items = [];

        // 1) 文件内置经验（只读，不可编辑）
        $patternsBase = resource_path('prompts/patterns');
        if (is_dir($patternsBase)) {
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
                    if ($raw === '') continue;

                    $title = $code;
                    if (preg_match('/^###\s*模式?[：:]\s*(.+)$/m', $raw, $m)) {
                        $title = trim($m[1]);
                    } elseif (preg_match('/^###?\s+(.+)$/m', $raw, $m)) {
                        $title = trim($m[1]);
                    }

                    $mtime = filemtime($f);
                    $items[] = [
                        'id' => 'file:' . $cat . '/' . $code,  // 文件来源用 file: 前缀
                        'code' => $code,
                        'category' => $cat,
                        'title' => $title,
                        'content' => $raw,
                        'enabled' => true,
                        'priority' => $priorityBase + $i,
                        'changelog' => null,
                        'source' => 'builtin',  // 标记为内置
                        'updated_at' => date('c', $mtime),
                        'stamp' => $this->makeStamp($mtime, $raw, $i + 1),
                    ];
                }
                $priorityBase += 100;
            }
        }

        // 2) 数据库经验包（可编辑）
        $dbItems = AiPattern::query()
            ->orderBy('priority')
            ->orderByDesc('id')
            ->limit(200)
            ->get();
        foreach ($dbItems as $p) {
            $arr = $p->toArray();
            $arr['source'] = 'custom';  // 标记为自定义
            $arr['priority'] = 1000 + (int) $p->priority;
            $ts = optional($p->updated_at)->timestamp ?: time();
            $arr['stamp'] = $this->makeStamp($ts, (string) $p->content, $p->id);
            $items[] = $arr;
        }

        return $this->ok([
            'items' => $items,
            'kb_version' => $kb->current(),
            'stats' => [
                'total' => count($items),
                'builtin' => count(array_filter($items, fn($x) => ($x['source'] ?? '') === 'builtin')),
                'custom' => count(array_filter($items, fn($x) => ($x['source'] ?? '') === 'custom')),
            ],
        ]);
    }

    /**
     * POST /api/admin/ai-patterns — 新增/更新经验包
     *
     * 简化版：用户只需提供 title + content 即可，其他字段自动处理
     * - code: 不传则自动生成（基于标题 + 时间戳）
     * - priority: 不传默认 50
     * - enabled: 不传默认 true
     */
    public function store(Request $request, TokenService $tokens, KbVersionService $kb): array
    {
        $admin = $tokens->adminFromRequest($request);
        abort_if(! $admin, 401, '管理员未登录');

        $data = $request->validate([
            'code' => ['nullable', 'string', 'max:60'],
            'category' => ['nullable', 'string', 'in:common,browser,excel,word,ps,pdf'],
            'title' => ['required', 'string', 'max:120'],
            'content' => ['required', 'string', 'max:20000'],
            'enabled' => ['nullable', 'boolean'],
            'priority' => ['nullable', 'integer', 'min:0', 'max:999'],
            'changelog' => ['nullable', 'string', 'max:2000'],
        ]);

        // 自动生成 code（如未传）
        $code = $data['code'] ?? null;
        if (! $code) {
            $base = Str::slug($data['title'], '-');
            if (! $base || mb_strlen($base) < 2) {
                $base = 'pattern';
            }
            $code = $base . '-' . date('mdHi');
            // 防冲突
            $i = 1;
            while (AiPattern::where('code', $code)->exists()) {
                $code = $base . '-' . date('mdHi') . '-' . $i++;
            }
        }

        $isNew = ! AiPattern::where('code', $code)->exists();
        $pattern = AiPattern::updateOrCreate(
            ['code' => $code],
            [
                'category' => $data['category'] ?? 'browser',
                'title' => $data['title'],
                'content' => $data['content'],
                'enabled' => (bool) ($data['enabled'] ?? true),
                'priority' => (int) ($data['priority'] ?? 50),
                'changelog' => $data['changelog'] ?? null,
            ]
        );

        // 自动 bump 经验库版本号
        $changeNote = $isNew
            ? "新增「{$pattern->title}」"
            : "更新「{$pattern->title}」";
        $kbMeta = $kb->bump($changeNote);

        return $this->ok([
            'pattern' => $pattern->fresh(),
            'kb_version' => $kbMeta,
        ]);
    }

    /** DELETE /api/admin/ai-patterns/{id} */
    public function destroy(Request $request, TokenService $tokens, KbVersionService $kb, int $id): array
    {
        $admin = $tokens->adminFromRequest($request);
        abort_if(! $admin, 401, '管理员未登录');

        $pattern = AiPattern::find($id);
        if (! $pattern) {
            return $this->ok(['deleted' => $id]);
        }
        $title = $pattern->title;
        $pattern->delete();

        $kbMeta = $kb->bump("删除「{$title}」");

        return $this->ok([
            'deleted' => $id,
            'kb_version' => $kbMeta,
        ]);
    }

    /**
     * GET /api/admin/ai-patterns/preview
     * 预览拼接出的完整 system prompt
     */
    public function preview(Request $request, TokenService $tokens, AiScriptService $service): array
    {
        $admin = $tokens->adminFromRequest($request);
        abort_if(! $admin, 401, '管理员未登录');

        $prompt = $service->jsonDslSystemPrompt();
        return $this->ok([
            'length' => mb_strlen($prompt),
            'system_prompt' => $prompt,
        ]);
    }

    /**
     * 生成"时间戳指纹"：YYYY-MMDD-HHmm-NNN
     * 让管理员一眼看出经验是哪个时间点的版本
     */
    private function makeStamp(int $ts, string $content, $serial = 0): string
    {
        $date = date('Y-md', $ts);
        $time = date('Hi', $ts);
        $suffix = substr(md5($content . '|' . $serial), 0, 3);
        return "{$date}-{$time}-{$suffix}";
    }

    /**
     * GET /api/admin/ai-patterns/diagnose
     *
     * 部署诊断卡片：让管理员一眼看出
     *   - rules-v1.0.1.json 是不是有 trigger_wrapper_classes（即下拉触发器修复是否生效）
     *   - 每个分类下有几条经验、最新文件的时间戳
     */
    public function diagnose(Request $request, TokenService $tokens, KbVersionService $kb): array
    {
        $admin = $tokens->adminFromRequest($request);
        abort_if(! $admin, 401, '管理员未登录');

        $report = [];

        // rules-v1.0.1.json 检查
        $rulesPath = public_path('../rules-v1.0.1.json');
        if (! file_exists($rulesPath)) {
            // 试试网站根目录的常见位置
            $rulesPath = base_path('rules-v1.0.1.json');
        }
        $rulesReport = [
            'exists' => file_exists($rulesPath),
            'path' => $rulesPath,
            'size' => file_exists($rulesPath) ? filesize($rulesPath) : 0,
            'mtime' => file_exists($rulesPath) ? date('Y-m-d H:i:s', filemtime($rulesPath)) : null,
            'has_trigger_classes' => false,  // 关键字段：有就说明是新版
            'inject_js_hash' => null,
        ];
        if (file_exists($rulesPath)) {
            $raw = (string) file_get_contents($rulesPath);
            $rulesReport['has_trigger_classes'] = str_contains($raw, 'trigger_wrapper_classes');
            $rulesReport['inject_js_hash'] = substr(md5($raw), 0, 12);
        }
        $report['rules'] = $rulesReport;

        // 经验文件统计
        $byCategory = [];
        $base = resource_path('prompts/patterns');
        if (is_dir($base)) {
            foreach (['common', 'browser', 'excel', 'word', 'ps', 'pdf'] as $cat) {
                $dir = $base . DIRECTORY_SEPARATOR . $cat;
                $files = is_dir($dir) ? array_filter(glob($dir . '/*.md'), fn($f) => basename($f) !== 'README.md') : [];
                $latest = 0;
                foreach ($files as $f) {
                    $latest = max($latest, filemtime($f));
                }
                $byCategory[$cat] = [
                    'count' => count($files),
                    'latest_mtime' => $latest ? date('Y-m-d H:i:s', $latest) : null,
                ];
            }
        }
        $report['patterns_by_category'] = $byCategory;

        // 知识库版本
        $report['kb_version'] = $kb->current();

        return $this->ok($report);
    }
}
