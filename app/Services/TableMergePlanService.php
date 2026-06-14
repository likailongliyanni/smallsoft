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
        ['姓名', '人名', '收货人姓名', '收件人姓名', '收件人', '联系人'],
        ['电话', '手机号', '手机号码', '电话号码', '联系电话', '收货人电话', '收件人电话', '买家手机号', 'phone', 'mobile', 'tel'],
        ['快递单号', '快递', '快递号', '物流单号', '运单号', '运单编号', '商品发货物流单号', 'tracking no', 'tracking number'],
        ['线上单号', '订单号', '订单编号', '线上订单号', 'order no', 'order id'],
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
     * 本地兜底：浏览器上报的 key_overlaps 显示两表存在高重合键列且有模板时，
     * 推断「按键匹配」；否则按「归一化表头相同」+「同义词典」聚成目标字段堆叠。
     */
    private function fallbackPlan(array $summary): array
    {
        $columns = $this->flattenColumns($summary);
        $templateFields = $this->templateFields($summary);

        $inferred = $this->inferJoinFromOverlaps($summary);
        if ($inferred !== null && $templateFields !== []) {
            $join = $inferred['join'];
            $allowedSheets = [
                $this->sheetKey($join['left']['file_index'], $join['left']['sheet']) => true,
                $this->sheetKey($join['right']['file_index'], $join['right']['sheet']) => true,
            ];

            $targets = [];
            foreach ($templateFields as $field) {
                $pool = array_filter(
                    $columns,
                    fn (array $column): bool => isset($allowedSheets[$this->sheetKey($column['file_index'], $column['sheet'])]),
                );
                $targets[] = ['name' => $field, 'sources' => $this->templateFieldSources($field, $pool)];
            }

            return [
                'operation' => 'join',
                'join' => $join,
                'dedupe' => true,
                'include_source' => false,
                'target_fields' => $targets,
                'notes' => [$inferred['note'], '本地规则按模板字段名匹配，请人工核对匹配键和未匹配的列。'],
            ];
        }

        if ($templateFields !== []) {
            $targets = [];
            foreach ($templateFields as $field) {
                $targets[] = ['name' => $field, 'sources' => $this->templateFieldSources($field, $columns)];
            }

            return $this->unionPlan($targets, false, ['本地规则按模板字段名匹配，请人工核对未匹配的列。']);
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

        return $this->unionPlan($targets, true, ['本地规则按表头同义词归类，请人工核对。']);
    }

    /**
     * 模板字段的来源列：表头与字段名完全一致的排最前。
     * 合并取每行第一个非空来源，例如模板「线上单号」同时命中「线上单号」「订单编号」
     * 两列时必须优先用前者（订单编号可能是父单号，粒度不同）。
     */
    private function templateFieldSources(string $field, iterable $columns): array
    {
        $exact = [];
        $grouped = [];
        foreach ($columns as $column) {
            if (! $this->sameField($field, $column['header'])) {
                continue;
            }
            if ($this->normalizeHeader($column['header']) === $this->normalizeHeader($field)) {
                $exact[] = $this->sourceRef($column);
            } else {
                $grouped[] = $this->sourceRef($column);
            }
        }

        return array_merge($exact, $grouped);
    }

    /** @param array<int, array{name: string, sources: array}> $targets */
    private function unionPlan(array $targets, bool $includeSource, array $notes): array
    {
        return [
            'operation' => 'union',
            'join' => null,
            'dedupe' => false,
            'include_source' => $includeSource,
            'target_fields' => $targets,
            'notes' => $notes,
        ];
    }

    /**
     * 用浏览器本地算好的跨表值交集挑匹配键：取覆盖率最高且足够可信的列对，
     * 行数多的一侧作为主表（left）。返回 null 表示证据不足。
     *
     * @return array{join: array, note: string}|null
     */
    private function inferJoinFromOverlaps(array $summary): ?array
    {
        $rowCounts = [];
        foreach ((array) ($summary['files'] ?? []) as $fileIndex => $file) {
            foreach ((array) ($file['sheets'] ?? []) as $sheet) {
                $name = trim((string) ($sheet['name'] ?? ''));
                $rows = max(0, (int) ($sheet['max_row'] ?? 0) - (int) ($sheet['header_row'] ?? 0));
                $rowCounts[$this->sheetKey((int) $fileIndex, $name)] = $rows;
            }
        }

        $best = null;
        foreach ((array) ($summary['key_overlaps'] ?? []) as $pair) {
            if (! is_array($pair)) {
                continue;
            }
            $overlap = (int) ($pair['overlap'] ?? 0);
            $coverage = (float) ($pair['coverage'] ?? 0);
            if ($overlap < 3 || $coverage < 0.5) {
                continue;
            }
            if (! $best || $coverage > (float) ($best['coverage'] ?? 0)) {
                $best = $pair;
            }
        }
        if (! $best) {
            return null;
        }

        $a = (array) ($best['a'] ?? []);
        $b = (array) ($best['b'] ?? []);
        foreach ([$a, $b] as $side) {
            if (trim((string) ($side['sheet'] ?? '')) === '' || trim((string) ($side['column'] ?? '')) === '') {
                return null;
            }
        }

        $aRows = $rowCounts[$this->sheetKey((int) ($a['file_index'] ?? 0), (string) $a['sheet'])] ?? 0;
        $bRows = $rowCounts[$this->sheetKey((int) ($b['file_index'] ?? 0), (string) $b['sheet'])] ?? 0;
        [$left, $right] = $aRows >= $bRows ? [$a, $b] : [$b, $a];

        return [
            'join' => [
                'left' => ['file_index' => (int) ($left['file_index'] ?? 0), 'sheet' => (string) $left['sheet']],
                'right' => ['file_index' => (int) ($right['file_index'] ?? 0), 'sheet' => (string) $right['sheet']],
                'keys' => [[
                    'left_column' => strtoupper((string) $left['column']),
                    'right_column' => strtoupper((string) $right['column']),
                ]],
                'type' => 'inner',
            ],
            'note' => sprintf(
                '本地规则按值重合推断匹配键：「%s」=「%s」（重合 %d 个值）。',
                (string) ($left['header'] ?? $left['column']),
                (string) ($right['header'] ?? $right['column']),
                (int) ($best['overlap'] ?? 0),
            ),
        ];
    }

    private function sheetKey(int $fileIndex, string $sheet): string
    {
        return $fileIndex.'#'.$sheet;
    }

    private function callModel(ModelConfig $config, array $summary, string $instruction, array $fallback): array
    {
        $apiKey = Crypt::decryptString($config->api_key_encrypted);
        $endpoint = $this->chatEndpoint((string) $config->base_url);

$system = <<<'PROMPT'
你是「表格整理」软件的合并规划器，只输出 JSON，不输出 Markdown。

用户的 Excel 原文件不会发给你。你能看到的是浏览器本地提取的轻量摘要：
- tables_summary.files：每个文件每个 sheet 的表头、每列样例值和列统计（value_kind 值形态、unique_count 唯一值数、non_empty 非空数），以及 header_row / max_row（可估算行数）。
- tables_summary.template：可选的模板表字段列表。
- tables_summary.key_overlaps：浏览器本地算好的「跨表同值列」证据。每条是两张表的一对列及其值交集统计：overlap 交集个数，coverage 占较小一侧唯一值的比例。
- instruction：用户的口语化要求。普通用户描述不精确甚至有错，例如说「按订单号匹配」但另一张表根本没有订单号列。哪两列能当匹配键，以 key_overlaps 的实际证据为准，不以用户用词为准。

第一步：判断合并方式 operation。
- "union"（堆叠）：多个来源表是同一种清单，行上下拼接、同义列归并。没有跨表匹配需求时的默认方式。
- "join"（按键匹配）：用户想把一张表的信息按某个键带到另一张表的行上（描述里常见「匹配 / 对应 / 关联 / 补上 / 查」），或 key_overlaps 显示两张表存在高重合键列。典型：订单表 + 快递单号表，按电话把快递单号接到订单行上。

join 的规则：
1. left 是主表（通常行数多、信息全的明细表），right 是被查的表（码表 / 汇总表）。
2. keys 从 key_overlaps 里挑覆盖率高的列对，可以多个（如 姓名+电话）；不要凭表头猜没有数据证据的键。
3. type："inner" 只保留匹配上的行，"left" 保留主表全部行。用户说「只要对上的」「其他都不要」时用 inner。
4. 主表是明细级（同一单据多行）而输出字段是单据级时，合并后会出现整行重复，这时 dedupe 设 true。
5. notes 第一条必须用一句用户能懂的话说明实际用的匹配键和原因，例如「快递表里没有订单号列，实际按 收货人电话=电话 匹配（两表重合 33 个号码）」。

字段归类规则（两种方式都适用）：
1. 表头语义相同或高度相近的归为一组，例如「商品名称 / 名称 / 品名」；表头不同但样例值形态一致也可归为一组（表头叫「货号」但样例全是 13 位 69 开头的数字，应归入 69码）。
2. 拿不准的不要硬归，宁可不映射，让用户人工决定。
3. 提供了 template_fields 时，target_fields 必须与模板字段完全一致（名称和顺序都不能改）；映射不上的模板字段 sources 留空数组。
4. 没有模板时，目标字段名选组内最规范、最常用的叫法（优先中文规范叫法）。
5. 用户的自然语言要求优先级最高：只要哪些字段、怎么命名、哪些 sheet 不要，都必须照做；但匹配键必须有数据证据。
6. join 模式下 sources 只能来自 left / right 这两个 sheet。
7. 有模板、或用户表示「其他信息都不要」时，include_source 设 false（不附加来源文件列）。

必须输出这个 JSON 结构（file_index 是摘要里 files 数组的下标，column 是列字母；operation 为 "union" 时 join 填 null）：
{
  "operation": "join",
  "join": {
    "left": {"file_index": 0, "sheet": "订单导出"},
    "right": {"file_index": 1, "sheet": "Sheet1"},
    "keys": [{"left_column": "T", "right_column": "B"}],
    "type": "inner"
  },
  "dedupe": true,
  "include_source": false,
  "target_fields": [
    {
      "name": "线上单号",
      "sources": [
        {"file_index": 0, "sheet": "订单导出", "column": "B"}
      ]
    }
  ],
  "notes": ["对用户有用的简短提示，可为空数组"]
}

规则：
1. sources 和 keys 里的 file_index / sheet / column 必须取自摘要中真实存在的列，不能编造。
2. 同一个来源列只能出现在一个目标字段里；匹配键列可以同时再作为某个目标字段的来源。
3. 同一字段有多个来源列时，sources 的先后就是取值优先级（每行取第一个非空）。表头与目标字段名完全一致的列必须排最前；警惕名字相近但粒度不同的列（如「订单编号」可能是父单号、「线上单号」是子单号，unique_count 不同就是粒度不同的信号）。
4. 不要返回模糊建议，必须返回可直接执行的计划。
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
     * 清洗 AI 返回：join 配置必须指向真实的 sheet 和列（非法则回退堆叠）；
     * 来源列必须真实存在、不能重复占用；join 模式下来源列限制在左右两表内；
     * 模板字段强制对齐。
     */
    private function normalizePlan(array $plan, array $summary, array $fallback): array
    {
        $validColumns = [];
        $sheetColumns = [];
        foreach ($this->flattenColumns($summary) as $column) {
            $validColumns[$this->columnKey($column['file_index'], $column['sheet'], $column['column'])] = true;
            $sheetColumns[$this->sheetKey($column['file_index'], $column['sheet'])][$column['column']] = true;
        }

        $templateFields = $this->templateFields($summary);

        $notes = array_values(array_filter(
            array_map(fn ($note) => trim((string) $note), (array) ($plan['notes'] ?? [])),
            fn (string $note): bool => $note !== '',
        ));

        $operation = strtolower(trim((string) ($plan['operation'] ?? 'union'))) === 'join' ? 'join' : 'union';
        $join = null;
        if ($operation === 'join') {
            $join = $this->normalizeJoin((array) ($plan['join'] ?? []), $sheetColumns);
            if ($join === null) {
                $operation = 'union';
                $notes[] = 'AI 给出的按键匹配配置无效，已回退为堆叠合并，请人工检查。';
            }
        }

        $allowedSheets = null;
        if ($join !== null) {
            $allowedSheets = [
                $this->sheetKey($join['left']['file_index'], $join['left']['sheet']) => true,
                $this->sheetKey($join['right']['file_index'], $join['right']['sheet']) => true,
            ];
        }

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
                if ($allowedSheets !== null && ! isset($allowedSheets[$this->sheetKey($fileIndex, $sheet)])) {
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

        return [
            'operation' => $operation,
            'join' => $join,
            'dedupe' => (bool) ($plan['dedupe'] ?? false),
            'include_source' => array_key_exists('include_source', $plan)
                ? (bool) $plan['include_source']
                : ($templateFields === []),
            'target_fields' => $targets,
            'notes' => array_slice($notes, 0, 10),
        ];
    }

    /**
     * @param array<string, array<string, bool>> $sheetColumns "fileIndex#sheet" => [列字母 => true]
     */
    private function normalizeJoin(array $join, array $sheetColumns): ?array
    {
        $left = (array) ($join['left'] ?? []);
        $right = (array) ($join['right'] ?? []);
        $leftIndex = (int) ($left['file_index'] ?? -1);
        $rightIndex = (int) ($right['file_index'] ?? -1);
        $leftSheet = trim((string) ($left['sheet'] ?? ''));
        $rightSheet = trim((string) ($right['sheet'] ?? ''));
        $leftKey = $this->sheetKey($leftIndex, $leftSheet);
        $rightKey = $this->sheetKey($rightIndex, $rightSheet);

        if ($leftKey === $rightKey || ! isset($sheetColumns[$leftKey]) || ! isset($sheetColumns[$rightKey])) {
            return null;
        }

        $keys = [];
        foreach ((array) ($join['keys'] ?? []) as $pair) {
            if (! is_array($pair)) {
                continue;
            }
            $leftColumn = strtoupper(trim((string) ($pair['left_column'] ?? '')));
            $rightColumn = strtoupper(trim((string) ($pair['right_column'] ?? '')));
            if (isset($sheetColumns[$leftKey][$leftColumn]) && isset($sheetColumns[$rightKey][$rightColumn])) {
                $keys[] = ['left_column' => $leftColumn, 'right_column' => $rightColumn];
            }
        }
        if ($keys === []) {
            return null;
        }

        return [
            'left' => ['file_index' => $leftIndex, 'sheet' => $leftSheet],
            'right' => ['file_index' => $rightIndex, 'sheet' => $rightSheet],
            'keys' => array_slice($keys, 0, 3),
            'type' => strtolower(trim((string) ($join['type'] ?? 'inner'))) === 'left' ? 'left' : 'inner',
        ];
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
