<?php

namespace App\Services;

use App\Models\ModelConfig;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\Http;
use Throwable;

/**
 * 「通用脏 Excel 结构化」规划器。
 *
 * 和 TableMergePlanService 同样的隐私口径：用户的 xlsx 不上传，后端只看到浏览器本地
 * 算好的轻量摘要（每个区域的表头候选、列形态统计 value_kind / purity / non_empty、
 * 少量样例）。本服务只产出一份「结构化计划」，真正的整理在浏览器本地执行。
 *
 * 关键约束：绝不写死任何业务字段。目标字段完全由「表头 + 列形态 + 用户自然语言」推断。
 * 这里没有 ALIAS_GROUPS 之类的业务词典——兜底也只按内容形态生成字段。
 */
class TableTidyPlanService
{
    /** 引擎认识的清洗器名（与 table-tidy-local.js 的 cleaners 一一对应）。 */
    private const KNOWN_CLEANERS = [
        'trim', 'collapseSpace', 'stripSymbols', 'unwrap', 'toHalfWidth',
        'normalizeDate', 'normalizeAmount', 'normalizeNumber', 'fillDitto', 'cnNumeralToArabic',
    ];

    /** 引擎认识的字段类型家族。 */
    private const KNOWN_TYPES = ['text', 'id', 'number', 'date', 'contact'];

    /** 行角色（可被删除的噪声角色集合）。 */
    private const DROP_ROLES = ['empty', 'separator', 'repeated_header', 'summary', 'note'];

    public function makePlan(array $summary, string $instruction): array
    {
        $fallback = $this->fallbackPlan($summary, $instruction);

        try {
            $config = $this->activeModelConfig();
            if (! $config) {
                return $this->wrap('local-rule', null, null, $fallback,
                    ['AI 模型未配置，已按内容形态本地推断字段，请人工核对。']);
            }

            $aiPlan = $this->callModel($config, $summary, $instruction, $fallback);

            return $this->wrap('ai', $config->provider, $config->model,
                $this->normalizePlan($aiPlan, $summary, $fallback), []);
        } catch (Throwable $e) {
            return $this->wrap('local-rule', null, null, $fallback,
                ['AI 结构化规划失败，已使用本地规则：'.$this->publicAiError($e)]);
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
     * 本地兜底：目标字段 = 所有区域表头的并集（归一化去重）。多段表头的乱表里每段
     * 字段都可能不同，只取主区域会把其他段的数据丢掉或错位；并集保证不丢列，
     * 同义列合并交给 AI 主路径。浏览器侧的 buildLocalPlan 同口径。
     */
    private function fallbackPlan(array $summary, string $instruction): array
    {
        $regions = (array) ($summary['regions'] ?? []);
        if ($regions === []) {
            return $this->emptyPlan(['未识别到有效数据区域。']);
        }

        $primaryIndex = 0;
        $bestRows = -1;
        foreach ($regions as $i => $region) {
            $rows = (int) ($region['data_row_count'] ?? 0);
            if ($rows > $bestRows) {
                $bestRows = $rows;
                $primaryIndex = $i;
            }
        }

        $targets = [];
        $used = [];
        foreach ($regions as $region) {
            foreach ((array) ($region['columns'] ?? []) as $column) {
                $header = trim((string) ($column['header'] ?? ''));
                $type = $this->normalizeType((string) ($column['value_kind'] ?? 'text'));
                if ($header === '' && (int) ($column['non_empty'] ?? 0) === 0) {
                    continue;
                }
                $name = $header !== '' ? $header : '列'.trim((string) ($column['column'] ?? ''));
                $norm = $this->normalizeHeader($name);
                if (isset($used[$norm])) {
                    continue;
                }
                $used[$norm] = true;
                $targets[] = [
                    'name' => $name,
                    'type' => $type,
                    'source_headers' => $header !== '' ? [$header] : [],
                    'cleaners' => $this->defaultCleanersFor($type),
                ];
            }
        }

        if ($targets === []) {
            return $this->emptyPlan(['区域里没有可用的列。']);
        }

        return [
            'primary_region_index' => $primaryIndex,
            'target_fields' => $targets,
            'row_filter' => ['drop_roles' => self::DROP_ROLES, 'min_confidence' => 0.5],
            'fill_ditto' => true,
            'dedupe' => false,
            'notes' => ['本地规则按各区域表头取并集，未合并同义列，请人工核对。'],
        ];
    }

    private function callModel(ModelConfig $config, array $summary, string $instruction, array $fallback): array
    {
        $apiKey = Crypt::decryptString($config->api_key_encrypted);
        $endpoint = $this->chatEndpoint((string) $config->base_url);

$system = <<<'PROMPT'
你是「通用表格整理」软件的结构化规划器，只输出 JSON，不输出 Markdown。

你面对的是任意乱表：订单、商品资料、供应商报价、对账单、库存、客户名单、采购清单、
财务流水、人员名单、物流明细，或用户自己随手做的表。绝不能假设它是某一种业务表，
更不能套用固定字段（不要默认有订单号 / 手机号 / 商品名称这类字段）。

用户的 Excel 原文件不会发给你。你看到的是浏览器本地提取的轻量摘要 tidy_summary：
- regions：sheet 被空行切成的若干数据区域。每个区域含 header_rows（表头所在行，可能多行）、
  data_row_count（数据行数）、columns。
- columns 每列：column 列字母、header 表头文本、value_kind 值形态
  （text 文本 / id 编号类含电话身份证 / number 数字金额 / date 日期 / contact 邮箱网址）、
  purity 形态纯度、non_empty 非空数、unique 唯一值数、samples 少量样例值。
- instruction：用户的口语化要求，可能很不专业，例如「把这个表整理一下，乱七八糟的不要，
  弄成能看的表」。你要据此推断他大概想要什么。

输出一份「目标结构 + 清洗策略」计划，字段完全由表头 + 值形态 + 用户要求推断：

1. target_fields：目标字段数组，按你认为合理的输出顺序排列。每个字段：
   - name：规范、易读的中文字段名（优先采用用户指定的叫法；用户没说就取最规范的常用叫法）。
   - type：text / id / number / date / contact 之一，取该字段对应列的主要 value_kind。
   - source_headers：能映射到该字段的原表表头文本数组（同义、近义都列上，浏览器按表头匹配列）。
     不同区域表头不同但语义相同的，全部列进来（如「电话 / 联系方式 / 手机号」）。
   - cleaners：对该字段要执行的清洗器名，从这些里选并排序：
     trim, collapseSpace, stripSymbols, unwrap, toHalfWidth, normalizeDate,
     normalizeAmount, normalizeNumber, fillDitto, cnNumeralToArabic。
     一般日期字段用 ["fillDitto","normalizeDate"]，金额 / 数字用 ["fillDitto","normalizeAmount"]，
     其余用 ["fillDitto","collapseSpace"]。用户明确要求的格式（统一日期 / 金额 / 提取手机号等）优先满足。
2. row_filter：哪些行算噪声要删。
   - drop_roles：从 empty / separator / repeated_header / summary（合计小计）/ note（备注页脚说明）里选，
     默认全删；若用户明确说「备注要保留」之类，就把对应角色从数组里去掉。
   - min_confidence：0~1，低于它的行进异常表待人工确认，默认 0.5。
3. fill_ditto：是否把「同上 / 〃」回填上一行的值，默认 true。
4. dedupe：是否整行去重，默认 false；用户说「去重 / 去掉重复」时 true。
5. primary_region_index：以哪个区域的字段为输出主结构（一般取数据行最多的那个）。
6. notes：给用户的一句话提示数组，可为空数组。

必须输出这个 JSON 结构：
{
  "primary_region_index": 0,
  "target_fields": [
    {"name": "客户名称", "type": "text", "source_headers": ["客户名称","客户","名称"], "cleaners": ["fillDitto","collapseSpace"]},
    {"name": "下单日期", "type": "date", "source_headers": ["下单日期","日期","时间"], "cleaners": ["fillDitto","normalizeDate"]}
  ],
  "row_filter": {"drop_roles": ["empty","separator","repeated_header","summary","note"], "min_confidence": 0.5},
  "fill_ditto": true,
  "dedupe": false,
  "notes": ["合计行与制表人页脚已识别为噪声并删除。"]
}

规则：
1. 字段和 source_headers 必须来自摘要里真实出现过的表头 / 形态，不能凭空编造业务字段。
2. 拿不准语义的列，宁可单列成一个字段（用它原表头当 name），也不要硬塞进别的字段。
3. type 必须取自该列实际 value_kind，不要主观臆断（表头叫「金额」但 value_kind 是 text 就按 text）。
4. 必须返回可直接执行的计划，不要含糊建议。
PROMPT;

        $user = json_encode([
            'instruction' => $instruction,
            'tidy_summary' => $summary,
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
     * 清洗 AI 返回：字段名 / 类型 / 清洗器 / 行过滤都收敛到引擎认识的取值范围；
     * 字段为空时回退本地兜底。source_headers 只保留真实出现过的表头。
     */
    private function normalizePlan(array $plan, array $summary, array $fallback): array
    {
        $validHeaders = $this->validHeaderSet($summary);

        $targets = [];
        $usedNames = [];
        foreach ((array) ($plan['target_fields'] ?? []) as $field) {
            if (! is_array($field)) {
                continue;
            }
            $name = trim((string) ($field['name'] ?? ''));
            if ($name === '') {
                continue;
            }
            $norm = $this->normalizeHeader($name);
            if (isset($usedNames[$norm])) {
                continue;
            }
            $usedNames[$norm] = true;

            $sourceHeaders = [];
            foreach ((array) ($field['source_headers'] ?? []) as $header) {
                $header = trim((string) $header);
                if ($header !== '' && isset($validHeaders[$this->normalizeHeader($header)])) {
                    $sourceHeaders[] = $header;
                }
            }
            // AI 没给来源表头时，至少用字段名自身去匹配列。
            if ($sourceHeaders === [] && isset($validHeaders[$norm])) {
                $sourceHeaders[] = $name;
            }

            $type = $this->normalizeType((string) ($field['type'] ?? 'text'));
            $cleaners = $this->normalizeCleaners((array) ($field['cleaners'] ?? []), $type);

            $targets[] = [
                'name' => $name,
                'type' => $type,
                'source_headers' => $sourceHeaders !== [] ? $sourceHeaders : [$name],
                'cleaners' => $cleaners,
            ];
        }

        if ($targets === []) {
            return $fallback;
        }

        $rowFilter = (array) ($plan['row_filter'] ?? []);
        $dropRoles = array_values(array_intersect(
            array_map('strval', (array) ($rowFilter['drop_roles'] ?? self::DROP_ROLES)),
            self::DROP_ROLES,
        ));
        $minConfidence = $rowFilter['min_confidence'] ?? 0.5;
        $minConfidence = max(0.0, min(1.0, (float) $minConfidence));

        $notes = array_values(array_filter(
            array_map(fn ($n) => trim((string) $n), (array) ($plan['notes'] ?? [])),
            fn (string $n): bool => $n !== '',
        ));

        return [
            'primary_region_index' => max(0, (int) ($plan['primary_region_index'] ?? 0)),
            'target_fields' => $targets,
            'row_filter' => [
                'drop_roles' => $dropRoles !== [] ? $dropRoles : self::DROP_ROLES,
                'min_confidence' => $minConfidence,
            ],
            'fill_ditto' => array_key_exists('fill_ditto', $plan) ? (bool) $plan['fill_ditto'] : true,
            'dedupe' => (bool) ($plan['dedupe'] ?? false),
            'notes' => array_slice($notes, 0, 10),
        ];
    }

    /** @return array<string, bool> 归一化表头集合，用于校验 AI 不编造来源列。 */
    private function validHeaderSet(array $summary): array
    {
        $set = [];
        foreach ((array) ($summary['regions'] ?? []) as $region) {
            foreach ((array) ($region['columns'] ?? []) as $column) {
                $header = trim((string) ($column['header'] ?? ''));
                if ($header !== '') {
                    $set[$this->normalizeHeader($header)] = true;
                }
            }
        }

        return $set;
    }

    private function normalizeType(string $type): string
    {
        $type = strtolower(trim($type));
        // 摘要里的细类型也归并到家族。
        $map = [
            'phone' => 'id', 'idcard' => 'id', 'longid' => 'id', 'code' => 'id',
            'amount' => 'number', 'integer' => 'number', 'decimal' => 'number', 'percent' => 'number',
            'datetime' => 'date', 'email' => 'contact', 'url' => 'contact',
        ];
        $type = $map[$type] ?? $type;

        return in_array($type, self::KNOWN_TYPES, true) ? $type : 'text';
    }

    private function normalizeCleaners(array $cleaners, string $type): array
    {
        $out = [];
        foreach ($cleaners as $name) {
            $name = trim((string) $name);
            if (in_array($name, self::KNOWN_CLEANERS, true) && ! in_array($name, $out, true)) {
                $out[] = $name;
            }
        }

        return $out !== [] ? $out : $this->defaultCleanersFor($type);
    }

    private function defaultCleanersFor(string $type): array
    {
        return match ($type) {
            'date' => ['fillDitto', 'normalizeDate'],
            'number' => ['fillDitto', 'normalizeAmount'],
            default => ['fillDitto', 'collapseSpace'],
        };
    }

    private function normalizeHeader(string $header): string
    {
        $text = mb_strtolower(trim($header), 'UTF-8');

        return preg_replace('/[\s_：:\-（）()\/\\\\.、，,]+/u', '', $text) ?? '';
    }

    private function emptyPlan(array $notes): array
    {
        return [
            'primary_region_index' => 0,
            'target_fields' => [],
            'row_filter' => ['drop_roles' => self::DROP_ROLES, 'min_confidence' => 0.5],
            'fill_ditto' => true,
            'dedupe' => false,
            'notes' => $notes,
        ];
    }

    /**
     * 取模型配置。和 TableMergePlanService 同一原则：.env 的 DASHSCOPE_API_KEY 优先，
     * 数据库 model_configs 仅作回切兜底。
     */
    private function activeModelConfig(): ?ModelConfig
    {
        // 走 config 而非 env()：config:cache 生效后 .env 不再加载，env() 会拿到空，
        // 否则这里会静默退到数据库里废弃的旧模型配置（旧 Key 已失效 → 401）。
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
