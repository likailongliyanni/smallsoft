<?php

namespace App\Services;

use App\Models\ModelConfig;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\Http;
use Throwable;

/**
 * 统计分析的 AI 能力：
 *  - makePlan：根据单表列摘要（+可选一句话需求）规划「按哪些维度、用什么指标和统计方式、取前几名」。
 *  - makeInsight：根据多维度 TopN 结果给出业务洞察文本。
 * 表数据不发给 AI，只发列摘要 / 结果摘要。AI 不可用时 makePlan 有本地兜底。
 */
class StatsAnalysisService
{
    private const AGGS = ['sum', 'count', 'avg', 'distinct'];

    public function makePlan(array $summary, string $instruction): array
    {
        $fallback = $this->fallbackPlan($summary);

        try {
            $config = $this->activeModelConfig();
            if (! $config) {
                return [
                    'source' => 'local-rule',
                    'used_model' => null,
                    'analyses' => $fallback['analyses'],
                    'notes' => $fallback['notes'],
                    'warnings' => ['AI 模型未配置，已用本地规则推荐分析维度，请人工核对。'],
                ];
            }

            $system = $this->planSystemPrompt();
            $raw = $this->callJson($config, $system, [
                'instruction' => $instruction,
                'table_summary' => $summary,
                'local_fallback_plan' => $fallback,
            ]);

            return [
                'source' => 'ai',
                'used_model' => $config->model,
                'analyses' => $this->normalizeAnalyses($raw['analyses'] ?? [], $summary, $fallback['analyses']),
                'notes' => $this->cleanNotes($raw['notes'] ?? []),
                'warnings' => [],
            ];
        } catch (Throwable $e) {
            return [
                'source' => 'local-rule',
                'used_model' => null,
                'analyses' => $fallback['analyses'],
                'notes' => $fallback['notes'],
                'warnings' => ['AI 规划失败，已用本地规则：'.$this->publicAiError($e)],
            ];
        }
    }

    public function makeInsight(array $resultSummary): array
    {
        $config = $this->activeModelConfig();
        if (! $config) {
            return ['insight' => '', 'warnings' => ['AI 模型未配置，无法解读，请在服务器 .env 配置 DASHSCOPE_API_KEY。']];
        }

        try {
            $system = $this->insightSystemPrompt();
            $raw = $this->callJson($config, $system, ['analyses_result' => $resultSummary]);
            $insight = trim((string) ($raw['insight'] ?? ''));

            return ['insight' => mb_substr($insight, 0, 1200, 'UTF-8'), 'warnings' => []];
        } catch (Throwable $e) {
            return ['insight' => '', 'warnings' => ['AI 解读失败：'.$this->publicAiError($e)]];
        }
    }

    private function planSystemPrompt(): string
    {
        return <<<'PROMPT'
你是「表格统计分析」软件的规划器，只输出 JSON，不输出 Markdown。

用户的表格数据不会发给你，你只看到单表的列摘要 table_summary：
- row_count：数据行数。
- columns：每列 {name 列名, kind 'number'(数值)或 'text'(分类), unique_count 唯一值数, non_empty 非空数, samples 样例值}。

任务：决定按哪些维度分组、用什么指标和统计方式、每个维度取前几名 Top N。
- dimension（维度）：分类列，即按它分组。优先选 kind=text、或 unique_count 远小于 row_count 的列（如品类、地区、品牌、销售员、月份）。不要用唯一值几乎等于行数的列（如订单号、流水号）当维度。
- metric（指标）：数值列。
- agg（统计方式）：sum 求和 / count 计数(行数) / avg 平均 / distinct 去重计数。
  · sum、avg 需要数值 metric；count 不需要 metric（留空字符串）；distinct 的 metric 是「对哪列去重」（可为分类列，如统计各地区有多少个不同客户）。
- top_n：每个维度取前几名，默认 10。

规则：
1. 用户有 instruction 就严格照做（说了哪些维度、什么指标、前几名都要落实）；没有就自己挑 2-4 个最有分析价值的维度，配最合适的数值指标做 sum。
2. dimension 和 metric 必须是 columns 里真实存在的 name，原样照抄，不能编造或改写。
3. 同一指标可以配多个维度（如"各品类、各地区的销售额"→ 两条 analyses，都是 sum 销售额，dimension 不同）。
4. 没有任何数值列时，用 count 计数（metric 留空）。

必须输出这个 JSON 结构：
{
  "analyses": [
    {"dimension": "品类", "metric": "销售额", "agg": "sum", "top_n": 10},
    {"dimension": "地区", "metric": "销售额", "agg": "sum", "top_n": 10}
  ],
  "notes": ["用一句话说明你按什么维度、什么指标分析，可为空数组"]
}
PROMPT;
    }

    private function insightSystemPrompt(): string
    {
        return <<<'PROMPT'
你是数据分析助手，根据给定的多维度 Top N 统计结果，用简洁中文给出业务洞察。

输入 analyses_result 是若干个维度的排行：每个含 dimension(维度名)、agg(统计方式)、metric(指标名)、group_count(该维度共多少个值)、top(前几名，每条 key 维度值 / value 数值 / share 占比)。

要求：
1. 每个维度讲清楚：谁是头部主力、头部集中度（前几名占了多大比例）、有没有明显断层或异常值得注意。
2. 口语化、给老板/运营看的话，3-6 句即可；可以点名具体的维度值和占比，但不要把所有数字都罗列一遍。
3. 不编造输入里没有的数据。

只输出 JSON：{"insight": "你的分析文字"}。
PROMPT;
    }

    /** 本地兜底：文本列(或低基数列)当维度，第一个数值列当 sum 指标，没数值列则 count。 */
    private function fallbackPlan(array $summary): array
    {
        $columns = $this->columns($summary);
        $rowCount = (int) ($summary['row_count'] ?? 0);

        $numberCols = array_values(array_filter($columns, fn ($c) => ($c['kind'] ?? '') === 'number'));
        $dimCols = array_values(array_filter($columns, function ($c) use ($rowCount) {
            if (($c['kind'] ?? '') === 'number') {
                return false;
            }
            $unique = (int) ($c['unique_count'] ?? 0);

            return $unique === 0 || $rowCount === 0 || $unique <= max(1, (int) ($rowCount * 0.8));
        }));

        if ($dimCols === []) {
            $dimCols = array_slice($columns, 0, 1);
        }
        $dimCols = array_slice($dimCols, 0, 4);

        $metric = $numberCols[0]['name'] ?? '';
        $agg = $metric !== '' ? 'sum' : 'count';

        $analyses = [];
        foreach ($dimCols as $col) {
            $analyses[] = [
                'dimension' => $col['name'],
                'metric' => $agg === 'count' ? '' : $metric,
                'agg' => $agg,
                'top_n' => 10,
            ];
        }

        return [
            'analyses' => $analyses,
            'notes' => ['本地规则：分类列作维度'.($metric !== '' ? "，对「{$metric}」求和" : '，按行数计数').'，请人工核对。'],
        ];
    }

    private function normalizeAnalyses(array $raw, array $summary, array $fallback): array
    {
        $names = [];
        foreach ($this->columns($summary) as $col) {
            $name = trim((string) ($col['name'] ?? ''));
            if ($name !== '') {
                $names[$name] = true;
            }
        }

        $firstNumber = '';
        foreach ($this->columns($summary) as $col) {
            if (($col['kind'] ?? '') === 'number') {
                $firstNumber = (string) $col['name'];
                break;
            }
        }

        $out = [];
        $seen = [];
        foreach ($raw as $item) {
            if (! is_array($item)) {
                continue;
            }
            $dimension = trim((string) ($item['dimension'] ?? ''));
            if ($dimension === '' || ! isset($names[$dimension]) || isset($seen[$dimension])) {
                continue;
            }
            $agg = strtolower(trim((string) ($item['agg'] ?? 'sum')));
            if (! in_array($agg, self::AGGS, true)) {
                $agg = 'sum';
            }
            $metric = trim((string) ($item['metric'] ?? ''));
            if ($agg === 'count') {
                $metric = '';
            } elseif ($metric === '' || ! isset($names[$metric])) {
                $metric = $firstNumber;
                if ($metric === '') {
                    $agg = 'count';
                }
            }
            $topN = (int) ($item['top_n'] ?? 10);
            $topN = max(1, min(1000, $topN ?: 10));

            $seen[$dimension] = true;
            $out[] = ['dimension' => $dimension, 'metric' => $metric, 'agg' => $agg, 'top_n' => $topN];
        }

        return $out !== [] ? $out : $fallback;
    }

    private function cleanNotes($notes): array
    {
        return array_slice(array_values(array_filter(
            array_map(fn ($n) => trim((string) $n), (array) $notes),
            fn (string $n): bool => $n !== '',
        )), 0, 8);
    }

    /** @return array<int, array> */
    private function columns(array $summary): array
    {
        return array_values(array_filter((array) ($summary['columns'] ?? []), 'is_array'));
    }

    // ---------------- AI 调用骨架（与 TableMergePlanService 一致） ----------------

    private function callJson(ModelConfig $config, string $system, array $userPayload): array
    {
        $apiKey = Crypt::decryptString($config->api_key_encrypted);
        $endpoint = $this->chatEndpoint((string) $config->base_url);

        $body = [
            'model' => $config->model,
            'messages' => [
                ['role' => 'system', 'content' => $system],
                ['role' => 'user', 'content' => json_encode($userPayload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES)],
            ],
            'temperature' => 0.2,
            'max_tokens' => min((int) ($config->max_tokens ?: 2048), 4096),
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

        return str_ends_with($baseUrl, '/chat/completions') ? $baseUrl : $baseUrl.'/chat/completions';
    }

    private function isDeepSeek(ModelConfig $config): bool
    {
        return $config->provider === 'deepseek' || str_contains((string) $config->base_url, 'deepseek.com');
    }

    private function publicAiError(Throwable $e): string
    {
        $lower = mb_strtolower($e->getMessage(), 'UTF-8');
        if (str_contains($lower, 'invalid_api_key') || str_contains($lower, 'invalidapikey')
            || str_contains($lower, 'incorrect api key') || str_contains($lower, '401')) {
            return 'AI Key 无效，请检查服务器 .env 里的 DASHSCOPE_API_KEY。';
        }
        if (str_contains($lower, 'timeout') || str_contains($lower, 'timed out')) {
            return 'AI 请求超时，请稍后重试。';
        }

        return mb_substr($e->getMessage(), 0, 300, 'UTF-8');
    }
}
