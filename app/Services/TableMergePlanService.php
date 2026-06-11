<?php

namespace App\Services;

use App\Models\ModelConfig;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\Http;
use Throwable;

class TableMergePlanService
{
    /**
     * 常见同义表头分组，AI 不可用时的本地兜底。
     * 每组第一个名字作为目标字段名。
     */
    private const ALIAS_GROUPS = [
        ['商品名称', '品名', '名称', '商品名', '产品名称', '货品名称', 'title', 'name', 'product name'],
        ['69码', '69 码', '条码', '条形码', '商品条码', '国际条码', 'ean', 'barcode', 'bar code', 'upc'],
        ['商品编码', '货号', '款号', '编码', '编号', '商品编号', 'sku', 'item', 'code', 'item no'],
        ['颜色', '色号', 'color', 'colour'],
        ['尺码', '尺寸', 'size'],
        ['品牌', 'brand'],
        ['分类', '类目', 'category'],
        ['数量', 'qty', 'quantity'],
        ['单价', 'unit price'],
        ['金额', '总价', '合计', 'amount', 'total'],
        ['单位', 'unit'],
        ['规格', 'spec', '规格型号'],
        ['备注', '说明', 'remark', 'remarks', 'note', 'notes'],
        ['供应商', '供货商', '厂家', 'supplier', 'vendor'],
        ['日期', '时间', 'date'],
    ];

    public function makePlan(array $summary, string $instruction): array
    {
        $fallback = $this->fallbackPlan($summary);

        try {
            $config = $this->activeModelConfig();
            if (! $config) {
                return [
                    'source' => 'local-rule',
                    'used_provider' => null,
                    'used_model' => null,
                    'plan' => $fallback,
                    'warnings' => ['AI 模型未配置，已使用本地规则归类字段，请人工核对。'],
                ];
            }

            $aiPlan = $this->callModel($config, $summary, $instruction, $fallback);

            return [
                'source' => 'ai',
                'used_provider' => $config->provider,
                'used_model' => $config->model,
                'plan' => $this->normalizePlan($aiPlan, $summary, $fallback),
                'warnings' => [],
            ];
        } catch (Throwable $e) {
            return [
                'source' => 'local-rule',
                'used_provider' => null,
                'used_model' => null,
                'plan' => $fallback,
                'warnings' => ['AI 字段归类失败，已使用本地规则：'.$this->publicAiError($e)],
            ];
        }
    }

    /**
     * 本地兜底：按「归一化表头相同」+「同义词典」把各来源列聚成目标字段。
     * 有模板时以模板字段为准。
     */
    private function fallbackPlan(array $summary): array
    {
        $columns = $this->flattenColumns($summary);
        $templateFields = $this->templateFields($summary);

        if ($templateFields !== []) {
            $targets = [];
            foreach ($templateFields as $field) {
                $sources = [];
                foreach ($columns as $column) {
                    if ($this->sameField($field, $column['header'])) {
                        $sources[] = $this->sourceRef($column);
                    }
                }
                $targets[] = ['name' => $field, 'sources' => $sources];
            }

            return ['target_fields' => $targets, 'notes' => ['本地规则按模板字段名匹配，请人工核对未匹配的列。']];
        }

        $groups = [];
        foreach ($columns as $column) {
            $key = $this->groupKey($column['header']);
            if ($key === '') {
                continue;
            }
            $groups[$key]['headers'][] = $column['header'];
            $groups[$key]['sources'][] = $this->sourceRef($column);
        }

        $targets = [];
        foreach ($groups as $key => $group) {
            $name = $this->canonicalName($key, $group['headers']);
            $targets[] = ['name' => $name, 'sources' => $group['sources']];
        }

        return ['target_fields' => $targets, 'notes' => ['本地规则按表头同义词归类，请人工核对。']];
    }

    private function callModel(ModelConfig $config, array $summary, string $instruction, array $fallback): array
    {
        $apiKey = Crypt::decryptString($config->api_key_encrypted);
        $endpoint = $this->chatEndpoint((string) $config->base_url);

$system = <<<'PROMPT'
你是「表格整理」软件的字段归类规划器，只输出 JSON，不输出 Markdown。

用户的 Excel 原文件不会发给你。你只能看到浏览器本地提取出的轻量摘要：每个文件每个 sheet 的表头、每列样例值，以及可选的模板表字段列表。

背景：原始表通常是不同的人手工做的，同一个意思的字段写法五花八门。你的任务是把「很可能是同一个字段」的列归成一组，输出目标字段及其来源列映射，供用户人工确认后在浏览器本地合并表格。

归类原则：
1. 表头语义相同或高度相近的归为一组，例如「商品名称 / 名称 / 品名 / 产品名称」是一组；「69码 / 条码 / 商品条码 / EAN」是一组。
2. 表头不同但样例值形态一致也可以归为一组，例如某列表头叫「货号」但样例全是 13 位 69 开头的数字，应归入 69码 组。
3. 拿不准的不要硬归，宁可单独成组或放进 unmapped，让用户人工决定。
4. 如果提供了 template_fields，目标字段必须与模板字段完全一致（名称和顺序都不能改），把来源列映射到模板字段上；映射不上的模板字段 sources 留空数组。
5. 没有模板时，目标字段名选组内最规范、最常用的叫法（优先中文规范叫法，如「商品名称」优于「品名」）。
6. 用户的自然语言要求（instruction）优先级最高：用户说只要哪些字段、怎么命名、哪些 sheet 不要，都必须照做。
7. 明显不是数据列的（空表头且无样例、序号列「序号/No.」可以保留为一组但放在最后）。

必须输出这个 JSON 结构（file_index 是摘要里 files 数组的下标，column 是列字母）：
{
  "target_fields": [
    {
      "name": "商品名称",
      "sources": [
        {"file_index": 0, "sheet": "Sheet1", "column": "B"},
        {"file_index": 1, "sheet": "进货表", "column": "C"}
      ]
    }
  ],
  "notes": ["对用户有用的简短提示，可为空数组"]
}

规则：
1. sources 里的 file_index / sheet / column 必须取自摘要中真实存在的列，不能编造。
2. 同一个来源列只能出现在一个目标字段里。
3. 不要返回模糊建议，必须返回可直接执行的映射。
PROMPT;

        $user = json_encode([
            'instruction' => $instruction,
            'tables_summary' => $summary,
            'local_fallback_plan' => $fallback,
        ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);

        $body = [
            'model' => $config->model,
            'messages' => [
                ['role' => 'system', 'content' => $system],
                ['role' => 'user', 'content' => $user],
            ],
            'temperature' => 0.1,
            'max_tokens' => min((int) ($config->max_tokens ?: 4096), 8192),
            'stream' => false,
        ];

        if ($this->isDeepSeek($config)) {
            $body['thinking'] = ['type' => 'disabled'];
        }

        $response = Http::withToken($apiKey)
            ->timeout((int) ($config->request_timeout ?: config('ai.request_timeout', 180)))
            ->acceptJson()
            ->post($endpoint, $body);

        if (! $response->successful()) {
            throw new \RuntimeException('model returned '.$response->status().' '.$response->body());
        }

        $content = (string) data_get($response->json(), 'choices.0.message.content', '');
        $json = json_decode($this->extractJson($content), true);
        if (! is_array($json)) {
            throw new \RuntimeException('model did not return valid JSON');
        }

        return $json;
    }

    /**
     * 清洗 AI 返回：来源列必须真实存在、不能重复占用；模板字段强制对齐。
     */
    private function normalizePlan(array $plan, array $summary, array $fallback): array
    {
        $validColumns = [];
        foreach ($this->flattenColumns($summary) as $column) {
            $validColumns[$this->columnKey($column['file_index'], $column['sheet'], $column['column'])] = true;
        }

        $templateFields = $this->templateFields($summary);
        $usedColumns = [];
        $targets = [];

        foreach ((array) ($plan['target_fields'] ?? []) as $target) {
            if (! is_array($target)) {
                continue;
            }
            $name = trim((string) ($target['name'] ?? ''));
            if ($name === '') {
                continue;
            }

            $sources = [];
            foreach ((array) ($target['sources'] ?? []) as $source) {
                if (! is_array($source)) {
                    continue;
                }
                $fileIndex = (int) ($source['file_index'] ?? -1);
                $sheet = trim((string) ($source['sheet'] ?? ''));
                $column = strtoupper(trim((string) ($source['column'] ?? '')));
                $key = $this->columnKey($fileIndex, $sheet, $column);

                if (! isset($validColumns[$key]) || isset($usedColumns[$key])) {
                    continue;
                }
                $usedColumns[$key] = true;
                $sources[] = ['file_index' => $fileIndex, 'sheet' => $sheet, 'column' => $column];
            }

            $targets[] = ['name' => $name, 'sources' => $sources];
        }

        if ($templateFields !== []) {
            $byName = [];
            foreach ($targets as $target) {
                $byName[$this->normalizeHeader($target['name'])] = $target['sources'];
            }
            $targets = [];
            foreach ($templateFields as $field) {
                $targets[] = [
                    'name' => $field,
                    'sources' => $byName[$this->normalizeHeader($field)] ?? [],
                ];
            }
        }

        if ($targets === []) {
            return $fallback;
        }

        $notes = array_values(array_filter(
            array_map(fn ($note) => trim((string) $note), (array) ($plan['notes'] ?? [])),
            fn (string $note): bool => $note !== '',
        ));

        return ['target_fields' => $targets, 'notes' => array_slice($notes, 0, 10)];
    }

    /** @return array<int, array{file_index: int, file_name: string, sheet: string, column: string, header: string}> */
    private function flattenColumns(array $summary): array
    {
        $columns = [];
        foreach ((array) ($summary['files'] ?? []) as $fileIndex => $file) {
            foreach ((array) ($file['sheets'] ?? []) as $sheet) {
                $sheetName = trim((string) ($sheet['name'] ?? ''));
                foreach ((array) ($sheet['columns'] ?? []) as $column) {
                    $letters = strtoupper(trim((string) ($column['column'] ?? '')));
                    if (! preg_match('/^[A-Z]{1,3}$/', $letters)) {
                        continue;
                    }
                    $columns[] = [
                        'file_index' => (int) $fileIndex,
                        'file_name' => trim((string) ($file['file_name'] ?? '')),
                        'sheet' => $sheetName,
                        'column' => $letters,
                        'header' => trim((string) ($column['header'] ?? '')),
                    ];
                }
            }
        }

        return $columns;
    }

    /** @return string[] */
    private function templateFields(array $summary): array
    {
        $fields = [];
        foreach ((array) data_get($summary, 'template.fields', []) as $field) {
            $field = trim((string) $field);
            if ($field !== '') {
                $fields[] = $field;
            }
        }

        return $fields;
    }

    private function sourceRef(array $column): array
    {
        return [
            'file_index' => $column['file_index'],
            'sheet' => $column['sheet'],
            'column' => $column['column'],
        ];
    }

    private function columnKey(int $fileIndex, string $sheet, string $column): string
    {
        return $fileIndex.'#'.$sheet.'#'.$column;
    }

    private function sameField(string $a, string $b): bool
    {
        return $this->groupKey($a) !== '' && $this->groupKey($a) === $this->groupKey($b);
    }

    /** 归一化表头并映射到同义词组；无组则返回归一化表头本身。 */
    private function groupKey(string $header): string
    {
        $normalized = $this->normalizeHeader($header);
        if ($normalized === '') {
            return '';
        }

        foreach (self::ALIAS_GROUPS as $index => $group) {
            foreach ($group as $alias) {
                if ($normalized === $this->normalizeHeader($alias)) {
                    return 'group:'.$index;
                }
            }
        }

        return 'header:'.$normalized;
    }

    private function canonicalName(string $groupKey, array $headers): string
    {
        if (str_starts_with($groupKey, 'group:')) {
            $index = (int) substr($groupKey, 6);

            return self::ALIAS_GROUPS[$index][0] ?? ($headers[0] ?? '字段');
        }

        return $headers[0] ?? '字段';
    }

    private function normalizeHeader(string $header): string
    {
        $text = mb_strtolower(trim($header), 'UTF-8');

        return preg_replace('/[\s_：:\-（）()\/\\\\.]+/u', '', $text) ?? '';
    }

    /**
     * 取模型配置。和 AliyunAiService 同一原则：.env 的 DASHSCOPE_API_KEY 是当前维护的
     * 「阿里云全家桶」配置，优先使用；数据库 model_configs 是已废弃的旧表单，仅作回切兜底。
     */
    private function activeModelConfig(): ?ModelConfig
    {
        $apiKey = trim((string) env('DASHSCOPE_API_KEY', env('ALIYUN_API_KEY', '')));
        if ($apiKey !== '') {
            $spec = AliyunAiService::MODELS[AliyunAiService::DEFAULT_KEY];
            $config = new ModelConfig();
            $config->provider = 'aliyun';
            $config->base_url = AliyunAiService::BASE_URL;
            $config->model = $spec['model'];
            $config->api_key_encrypted = Crypt::encryptString($apiKey);
            $config->temperature = $spec['temperature'];
            $config->max_tokens = $spec['max_tokens'];
            $config->request_timeout = $spec['request_timeout'];

            return $config;
        }

        $config = ModelConfig::query()
            ->where('enabled', true)
            ->where('purpose', 'script')
            ->latest('id')
            ->first();

        if ($config && $config->base_url && $config->model && $config->api_key_encrypted) {
            return $config;
        }

        return null;
    }

    private function extractJson(string $content): string
    {
        $content = trim($content);
        if (str_starts_with($content, '```')) {
            $content = trim($content, "` \n\r\t");
            if (str_starts_with($content, 'json')) {
                $content = trim(substr($content, 4));
            }
        }

        $start = strpos($content, '{');
        $end = strrpos($content, '}');
        if ($start !== false && $end !== false && $end >= $start) {
            return substr($content, $start, $end - $start + 1);
        }

        return $content;
    }

    private function chatEndpoint(string $baseUrl): string
    {
        $baseUrl = rtrim($baseUrl, '/');

        return str_ends_with($baseUrl, '/chat/completions')
            ? $baseUrl
            : $baseUrl.'/chat/completions';
    }

    private function isDeepSeek(ModelConfig $config): bool
    {
        return $config->provider === 'deepseek'
            || str_contains((string) $config->base_url, 'deepseek.com');
    }

    private function publicAiError(Throwable $e): string
    {
        $message = $e->getMessage();
        $lower = mb_strtolower($message, 'UTF-8');

        if (str_contains($lower, 'invalid_api_key')
            || str_contains($lower, 'invalidapikey')
            || str_contains($lower, 'incorrect api key')
            || str_contains($lower, '401')) {
            return 'AI Key 无效，请检查服务器 .env 里的 DASHSCOPE_API_KEY。';
        }

        if (str_contains($lower, 'timeout') || str_contains($lower, 'timed out')) {
            return 'AI 请求超时，请稍后重试。';
        }

        return mb_substr($message, 0, 300, 'UTF-8');
    }
}
