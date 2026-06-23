<?php

namespace App\Services;

use App\Models\ModelConfig;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\Http;
use Throwable;

/**
 * 「智能统计（透视汇总）」规划器。
 *
 * 隐私口径与 TableTidy / TableMerge 一致：用户的 xlsx 不上传，后端只看到浏览器本地
 * 算好的轻量摘要（每列表头、值形态、唯一值数、少量样例）。本服务只产出一份「透视计划」
 * （分组维度 + 统计度量 + 筛选 + 时间粒度 + 是否铺成交叉表），真正的统计在浏览器本地执行。
 *
 * 处理对象是**标准表**（脏表先走「数据清洗」）。绝不写死业务字段，维度/度量完全由
 * 表头 + 值形态 + 用户自然语言推断。
 */
class TablePivotPlanService
{
    private const AGGS = ['sum', 'count', 'count_distinct', 'avg', 'max', 'min'];
    private const BUCKETS = ['year', 'quarter', 'month'];
    private const FILTER_OPS = ['in', 'eq', 'ne', 'gte', 'lte', 'contains'];

    public function makePlan(array $summary, string $instruction): array
    {
        $fallback = $this->fallbackPlan($summary, $instruction);

        try {
            $config = $this->activeModelConfig();
            if (! $config) {
                return $this->wrap('local-rule', null, null, $fallback,
                    ['AI 模型未配置，已按列形态本地推断维度和度量，请人工核对。']);
            }

            $aiPlan = $this->callModel($config, $summary, $instruction, $fallback);

            return $this->wrap('ai', $config->provider, $config->model,
                $this->normalizePlan($aiPlan, $summary, $fallback), []);
        } catch (Throwable $e) {
            return $this->wrap('local-rule', null, null, $fallback,
                ['AI 统计规划失败，已使用本地规则：'.$this->publicAiError($e)]);
        }
    }

    private function wrap(string $source, ?string $provider, ?string $model, array $plan, array $warnings): array
    {
        return [
            'source' => $source,
            'used_provider' => $provider,
            'used_model' => $model,
            'plan' => $plan,
            'warnings' => $warnings,
        ];
    }

    /**
     * 本地兜底：第一个文本/编号列当维度，第一个数字列做求和度量；没有数字列就计数。
     * 让没登录 / AI 失败时也能跑出一个基本统计，再由用户在确认页调整。
     */
    private function fallbackPlan(array $summary, string $instruction): array
    {
        $columns = (array) ($summary['columns'] ?? []);
        if ($columns === []) {
            return $this->emptyPlan(['未识别到有效列。']);
        }

        $dimension = null;
        $dateCol = null;
        $numberCol = null;
        foreach ($columns as $col) {
            $header = trim((string) ($col['header'] ?? ''));
            if ($header === '') {
                continue;
            }
            $kind = (string) ($col['kind'] ?? 'text');
            if ($kind === 'date' && $dateCol === null) {
                $dateCol = $header;
            }
            if ($kind === 'number' && $numberCol === null) {
                $numberCol = $header;
            }
            if ($dimension === null && in_array($kind, ['text', 'id'], true)) {
                $dimension = $header;
            }
        }
        if ($dimension === null) {
            $dimension = trim((string) ($columns[0]['header'] ?? '维度'));
        }

        $dimensions = [['column' => $dimension, 'label' => $dimension, 'time_bucket' => null]];
        if ($dateCol !== null) {
            $dimensions[] = ['column' => $dateCol, 'label' => $dateCol.'(年)', 'time_bucket' => 'year'];
        }

        $measures = $numberCol !== null
            ? [['column' => $numberCol, 'agg' => 'sum', 'label' => $numberCol.'合计']]
            : [['column' => '*', 'agg' => 'count', 'label' => '记录数']];

        return [
            'dimensions' => $dimensions,
            'measures' => $measures,
            'filters' => [],
            'pivot_column' => null,
            'sort' => null,
            'top_n' => null,
            'notes' => [],
        ];
    }

    private function callModel(ModelConfig $config, array $summary, string $instruction, array $fallback): array
    {
        $apiKey = Crypt::decryptString($config->api_key_encrypted);
        $endpoint = $this->chatEndpoint((string) $config->base_url);

$system = <<<'PROMPT'
你是「智能统计」软件的透视汇总规划器，只输出 JSON，不输出 Markdown。

你面对的是一张**标准表**（已经是规范的二维表，表头在第一行，下面是数据行）：
销售订单、出入库流水、客户消费、供应商供货、报表明细等。绝不假设它是某一种业务表，
不能套用固定字段（不要默认有金额 / 客户 / 日期这类字段，一切以摘要里的真实表头为准）。

用户的 Excel 原文件不会发给你。你看到的是浏览器本地算好的轻量摘要 pivot_summary：
- row_count：数据行数。
- columns 每列：header 表头文本、kind 值形态（text 文本 / id 编号 / number 数字金额 / date 日期）、
  non_empty 非空数、unique 唯一值数、samples 少量样例值。
- instruction：用户口语化的统计需求，例如「每个客户最近几年买了多少」「各供应商各品类的销量」
  「按月统计销售额」。你要据此推断分组维度和统计度量。

输出一份「透视计划」，维度/度量完全由表头 + 值形态 + 用户要求推断：

1. dimensions：分组维度数组（行维度），按输出顺序排列。每个维度：
   - column：摘要里真实出现过的表头文本。
   - label：给用户看的列名（默认就用 column；加了时间粒度时可写「下单日期(年)」这样）。
   - time_bucket：仅当该列 kind=date 且用户想按时间分组时填 year / quarter / month，否则填 null。
     用户说「最近几年 / 每年」→ year；「每季度」→ quarter；「每月 / 按月」→ month。
2. measures：统计度量数组（至少 1 个）。每个度量：
   - column：要统计的列表头；计数可用 "*"。
   - agg：sum 求和 / count 计数 / count_distinct 去重计数 / avg 平均 / max 最大 / min 最小。
     金额、数量类默认 sum；「多少个订单 / 多少种」用 count_distinct；「多少条 / 多少次」用 count。
   - label：给用户看的列名（如「销售额」「订单数」）。
3. filters：行筛选数组，可为空。每个：{column, op(in/eq/ne/gte/lte/contains), values:[...]}。
   仅在用户明确提了筛选条件（如「只看已完成的」「2024 年以后」）时给。
4. pivot_column：是否把某个维度铺成列做交叉表。填某个 dimension 的 label 表示用它当列轴
   （如行=客户、列=年份），不需要交叉表就填 null。一般用户说「交叉 / 对比 / 横着看」才设。
5. sort：排序，{by: 某个度量或维度的 label, dir: desc/asc}，不需要填 null。常按主要度量降序。
6. top_n：只要前 N 名时填数字，否则 null。
7. notes：给用户的一句话提示数组，可为空。

必须输出这个 JSON 结构：
{
  "dimensions": [
    {"column": "客户名称", "label": "客户", "time_bucket": null},
    {"column": "下单日期", "label": "年份", "time_bucket": "year"}
  ],
  "measures": [
    {"column": "金额", "agg": "sum", "label": "销售额"},
    {"column": "订单号", "agg": "count_distinct", "label": "订单数"}
  ],
  "filters": [],
  "pivot_column": null,
  "sort": {"by": "销售额", "dir": "desc"},
  "top_n": null,
  "notes": ["按客户和年份汇总销售额与订单数。"]
}

规则：
1. column 必须来自摘要里真实出现过的表头，不能凭空编造。
2. time_bucket 只能用在 kind=date 的列；非日期列一律 null。
3. agg 要符合列的形态：对 kind=text/id 的列不要用 sum/avg（除非用户明确要），计数类更合适。
4. 至少要有 1 个 measure；用户没说统计什么时，默认用「记录数」count("*")。
5. 必须返回可直接执行的计划，不要含糊建议。
PROMPT;

        $user = json_encode([
            'instruction' => $instruction,
            'pivot_summary' => $summary,
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
     * 清洗 AI 返回：维度/度量列必须是真实表头，agg / time_bucket / 筛选算子收敛到合法取值，
     * pivot_column 必须指向某个维度 label，度量为空时回退「记录数」。
     */
    private function normalizePlan(array $plan, array $summary, array $fallback): array
    {
        $validHeaders = $this->validHeaderSet($summary);
        $dateHeaders = $this->dateHeaderSet($summary);

        $dimensions = [];
        $dimLabels = [];
        foreach ((array) ($plan['dimensions'] ?? []) as $dim) {
            if (! is_array($dim)) {
                continue;
            }
            $column = $this->matchHeader((string) ($dim['column'] ?? ''), $validHeaders);
            if ($column === null) {
                continue;
            }
            $bucket = (string) ($dim['time_bucket'] ?? '');
            $bucket = (in_array($bucket, self::BUCKETS, true) && isset($dateHeaders[$this->normalizeHeader($column)]))
                ? $bucket : null;
            $label = trim((string) ($dim['label'] ?? '')) ?: ($bucket ? $column.'('.$this->bucketLabel($bucket).')' : $column);
            $label = $this->uniqueLabel($label, $dimLabels);
            $dimensions[] = ['column' => $column, 'label' => $label, 'time_bucket' => $bucket];
        }

        $measures = [];
        $measLabels = [];
        foreach ((array) ($plan['measures'] ?? []) as $meas) {
            if (! is_array($meas)) {
                continue;
            }
            $rawColumn = trim((string) ($meas['column'] ?? ''));
            $column = $rawColumn === '*' ? '*' : $this->matchHeader($rawColumn, $validHeaders);
            if ($column === null) {
                continue;
            }
            $agg = strtolower(trim((string) ($meas['agg'] ?? 'sum')));
            if (! in_array($agg, self::AGGS, true)) {
                $agg = $column === '*' ? 'count' : 'sum';
            }
            if ($column === '*' && ! in_array($agg, ['count', 'count_distinct'], true)) {
                $agg = 'count';
            }
            $label = trim((string) ($meas['label'] ?? '')) ?: $this->defaultMeasureLabel($column, $agg);
            $label = $this->uniqueLabel($label, $measLabels);
            $measures[] = ['column' => $column, 'agg' => $agg, 'label' => $label];
        }

        if ($dimensions === [] && $measures === []) {
            return $fallback;
        }
        if ($measures === []) {
            $measures[] = ['column' => '*', 'agg' => 'count', 'label' => '记录数'];
        }

        $filters = [];
        foreach ((array) ($plan['filters'] ?? []) as $filter) {
            if (! is_array($filter)) {
                continue;
            }
            $column = $this->matchHeader((string) ($filter['column'] ?? ''), $validHeaders);
            $op = strtolower(trim((string) ($filter['op'] ?? 'in')));
            if ($column === null || ! in_array($op, self::FILTER_OPS, true)) {
                continue;
            }
            $values = array_values(array_filter(
                array_map(fn ($v) => (string) $v, (array) ($filter['values'] ?? [])),
                fn (string $v): bool => $v !== '',
            ));
            if ($values === []) {
                continue;
            }
            $filters[] = ['column' => $column, 'op' => $op, 'values' => $values];
        }

        $pivotColumn = trim((string) ($plan['pivot_column'] ?? ''));
        $pivotColumn = ($pivotColumn !== '' && in_array($pivotColumn, $dimLabels, true)) ? $pivotColumn : null;
        // 交叉表至少要有一个非透视维度做行轴，否则退回长表。
        if ($pivotColumn !== null && count($dimensions) < 2) {
            $pivotColumn = null;
        }

        $sort = null;
        if (is_array($plan['sort'] ?? null)) {
            $by = trim((string) ($plan['sort']['by'] ?? ''));
            $dir = strtolower(trim((string) ($plan['sort']['dir'] ?? 'desc'))) === 'asc' ? 'asc' : 'desc';
            if ($by !== '' && (in_array($by, $dimLabels, true) || in_array($by, $measLabels, true))) {
                $sort = ['by' => $by, 'dir' => $dir];
            }
        }

        $topN = $plan['top_n'] ?? null;
        $topN = (is_numeric($topN) && (int) $topN > 0) ? (int) $topN : null;

        $notes = array_values(array_filter(
            array_map(fn ($n) => trim((string) $n), (array) ($plan['notes'] ?? [])),
            fn (string $n): bool => $n !== '',
        ));

        return [
            'dimensions' => $dimensions,
            'measures' => $measures,
            'filters' => $filters,
            'pivot_column' => $pivotColumn,
            'sort' => $sort,
            'top_n' => $topN,
            'notes' => array_slice($notes, 0, 10),
        ];
    }

    private function validHeaderSet(array $summary): array
    {
        $set = [];
        foreach ((array) ($summary['columns'] ?? []) as $col) {
            $header = trim((string) ($col['header'] ?? ''));
            if ($header !== '') {
                $set[$this->normalizeHeader($header)] = $header;
            }
        }

        return $set;
    }

    private function dateHeaderSet(array $summary): array
    {
        $set = [];
        foreach ((array) ($summary['columns'] ?? []) as $col) {
            $header = trim((string) ($col['header'] ?? ''));
            if ($header !== '' && (string) ($col['kind'] ?? '') === 'date') {
                $set[$this->normalizeHeader($header)] = $header;
            }
        }

        return $set;
    }

    private function matchHeader(string $header, array $validHeaders): ?string
    {
        $header = trim($header);
        if ($header === '') {
            return null;
        }

        return $validHeaders[$this->normalizeHeader($header)] ?? null;
    }

    private function uniqueLabel(string $label, array &$used): string
    {
        $base = $label !== '' ? $label : '列';
        $candidate = $base;
        $i = 2;
        while (in_array($candidate, $used, true)) {
            $candidate = $base.'_'.$i++;
        }
        $used[] = $candidate;

        return $candidate;
    }

    private function defaultMeasureLabel(string $column, string $agg): string
    {
        $aggLabel = [
            'sum' => '合计', 'count' => '记录数', 'count_distinct' => '去重数',
            'avg' => '平均', 'max' => '最大', 'min' => '最小',
        ][$agg] ?? $agg;

        return $column === '*' ? '记录数' : $column.$aggLabel;
    }

    private function bucketLabel(string $bucket): string
    {
        return ['year' => '年', 'quarter' => '季', 'month' => '月'][$bucket] ?? $bucket;
    }

    private function normalizeHeader(string $header): string
    {
        $text = mb_strtolower(trim($header), 'UTF-8');

        return preg_replace('/[\s_：:\-（）()\/\\\\.、，,]+/u', '', $text) ?? '';
    }

    private function emptyPlan(array $notes): array
    {
        return [
            'dimensions' => [],
            'measures' => [['column' => '*', 'agg' => 'count', 'label' => '记录数']],
            'filters' => [],
            'pivot_column' => null,
            'sort' => null,
            'top_n' => null,
            'notes' => $notes,
        ];
    }

    private function activeModelConfig(): ?ModelConfig
    {
        $apiKey = trim((string) config('ai.dashscope_api_key', ''));
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
