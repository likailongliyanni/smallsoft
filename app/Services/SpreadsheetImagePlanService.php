<?php

namespace App\Services;

use App\Models\ModelConfig;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\Http;
use Throwable;

class SpreadsheetImagePlanService
{
    public function makePlan(array $summary, string $instruction, array $options = []): array
    {
        $fallback = $this->fallbackPlan($summary, $instruction);

        try {
            $config = $this->activeModelConfig();
            if (! $config) {
                return [
                    'source' => 'local-rule',
                    'used_provider' => null,
                    'used_model' => null,
                    'plan' => $fallback,
                    'warnings' => ['AI 模型未配置，已使用本地规则。'],
                ];
            }

            $aiPlan = $this->callModel($config, $summary, $instruction, $fallback);

            return [
                'source' => 'ai',
                'used_provider' => $config->provider,
                'used_model' => $config->model,
                'plan' => $this->normalizePlan($aiPlan, $fallback),
                'warnings' => [],
            ];
        } catch (Throwable $e) {
            return [
                'source' => 'local-rule',
                'used_provider' => null,
                'used_model' => null,
                'plan' => $fallback,
                'warnings' => ['AI 规则生成失败，已使用本地规则：'.$this->publicAiError($e)],
            ];
        }
    }

    private function fallbackPlan(array $summary, string $instruction): array
    {
        $barcodeKeywords = ['69码', '69 码', '条码', '条形码', '商品条码', '国际条码', 'EAN', 'ean', 'barcode', 'bar code', 'UPC', 'upc'];
        $wantsBarcode = $this->containsAny($instruction, $barcodeKeywords);
        $explicitColumn = $this->explicitColumn($instruction, $barcodeKeywords);
        $barcodeColumn = $explicitColumn ?: ($wantsBarcode ? $this->inferColumnFromSummary($summary, $barcodeKeywords, true) : null);

        $fieldColumnMap = [];
        if ($barcodeColumn) {
            $fieldColumnMap['69码'] = $barcodeColumn;
        }

        $filenameTemplate = null;
        $folderTemplate = '';

        if ($wantsBarcode) {
            $folderTemplate = '{69码}';
            $filenameTemplate = '{图片序号}';
        }

        if (! $filenameTemplate) {
            $fields = [];
            foreach ([
                '69码' => $barcodeKeywords,
                '货号' => ['货号', '款号', 'sku', 'SKU', '编码', '商品编码', 'item', 'code'],
                '颜色' => ['颜色', '色号', 'color'],
                '尺码' => ['尺码', '尺寸', 'size'],
                '品名' => ['品名', '名称', '商品名', 'title', 'name'],
                '品牌' => ['品牌', 'brand'],
                '分类' => ['分类', '类目', 'category'],
            ] as $field => $keywords) {
                if ($this->containsAny($instruction, $keywords) || $this->summaryHasField($summary, $keywords)) {
                    $fields[] = $field;
                }
            }

            if ($fields === []) {
                $fields[] = '货号';
            }
            $fields[] = '图片序号';
            $filenameTemplate = '{'.implode('}_{', $fields).'}';
        }

        if ($folderTemplate === '') {
            if ($this->containsAny($instruction, ['每个sheet', '每个 sheet', '按sheet', '按 sheet', 'sheet单独', '工作表单独'])) {
                $folderTemplate = '{sheet}';
            } elseif ($this->containsAny($instruction, ['按品牌', '品牌分', '品牌文件夹'])) {
                $folderTemplate = '{品牌}';
            } elseif ($this->containsAny($instruction, ['按分类', '按类目', '分类文件夹', '类目文件夹'])) {
                $folderTemplate = '{分类}';
            } elseif (count($summary['sheets'] ?? []) > 1) {
                $folderTemplate = '{sheet}';
            }
        }

        $resize = null;
        if (preg_match('/(\d{2,5})\s*[xX×*]\s*(\d{2,5})/u', $instruction, $m)) {
            $resize = ['width' => (int) $m[1], 'height' => (int) $m[2]];
        }

        $format = 'original';
        if ($this->containsAny($instruction, ['jpg', 'jpeg', 'JPG', 'JPEG'])) {
            $format = 'jpg';
        } elseif ($this->containsAny($instruction, ['png', 'PNG'])) {
            $format = 'png';
        }

        return [
            'sheet_mode' => 'all',
            'sheets' => [],
            'header_row_by_sheet' => [],
            'field_column_map' => $fieldColumnMap,
            'filename_template' => $filenameTemplate,
            'folder_template' => $folderTemplate,
            'image_match_rule' => 'anchor_row',
            'fallback_filename_template' => '{sheet}_{row}_{图片序号}',
            'image_processing' => [
                'crop_whitespace' => $this->containsAny($instruction, ['裁剪', '裁掉白边', '去白边', '白边']),
                'resize' => $resize,
                'enhance' => $this->containsAny($instruction, ['清晰', '清晰化', '锐化', '增强']),
                'format' => $format,
            ],
        ];
    }

    private function callModel(ModelConfig $config, array $summary, string $instruction, array $fallback): array
    {
        $apiKey = Crypt::decryptString($config->api_key_encrypted);
        $endpoint = $this->chatEndpoint((string) $config->base_url);

$system = <<<'PROMPT'
你是 EXCEL 自动化软件的自然语言规则规划器，只输出 JSON，不输出 Markdown。

用户的 Excel 原文件和图片不会发给你。你只能看到浏览器本地提取出的轻量摘要：sheet 名、候选表头、样例行、图片锚点行列、最大行列数。你的任务是根据用户自然语言和摘要生成浏览器可执行规则，帮助处理不规则表格。

你的核心价值不是提取图片，而是把用户不规范、不完整、口语化的描述理解成精确结果：
- 识别用户真正想按什么字段建文件夹、按什么字段命名图片。
- 把“69码”“条码”“商品码”“EAN”“京东码附近那列”等说法归一成可执行字段。
- 结合 column_samples、headers、sample_rows 推断字段所在列；如果用户明确说列字母，优先使用用户指定列。
- 把“一行多图放 1.jpg、2.jpg”“每个商品一个文件夹”“多个 sheet 都处理”等说法落到 folder_template、filename_template、sheet_mode。
- 不要返回模糊建议，必须返回浏览器可以直接执行的规则。

必须输出这个 JSON 结构：
{
  "sheet_mode": "all",
  "sheets": [],
  "header_row_by_sheet": {"Sheet1": 2},
  "field_column_map": {},
  "filename_template": "{图片序号}",
  "folder_template": "{69码}",
  "image_match_rule": "anchor_row",
  "fallback_filename_template": "{sheet}_{row}_{图片序号}",
  "image_processing": {
    "crop_whitespace": false,
    "resize": null,
    "enhance": false,
    "format": "original"
  }
}

规则：
1. field_column_map 必须根据当前 workbook_summary 动态判断，不能把任何列字母写死。J、B、AA 等都只是某一张表里的可能结果。
2. 如果用户明确说“J列的69码”“J列为条码”，这一次才可以写 {"69码":"J"}；换一张表必须重新判断。
3. 如果用户说“用69码给图片文件夹命名/按69码建文件夹”，folder_template 用 "{69码}"，filename_template 通常用 "{图片序号}"。
4. field_column_map 的值必须是列字母，如 "A"、"J"、"AA"。
5. 如果用户没有明确列字母，但摘要中某列 header 或样例值明显对应字段，应在 field_column_map 中写出推断列；例如某列样例值是 13 位且以 69 开头，通常可推断该列为 "69码"，但列字母要取摘要中的真实列。
6. 不确定时优先保守，尽量使用用户明确指定的列和摘要中能证明的列，不要凭空编造字段。
7. 图片匹配默认按图片锚点所在行或附近有数据的行，image_match_rule 固定输出 "anchor_row"。
PROMPT;

        $user = json_encode([
            'instruction' => $instruction,
            'workbook_summary' => $summary,
            'local_fallback_plan' => $fallback,
        ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);

        $body = [
            'model' => $config->model,
            'messages' => [
                ['role' => 'system', 'content' => $system],
                ['role' => 'user', 'content' => $user],
            ],
            'temperature' => 0.1,
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

    private function normalizePlan(array $plan, array $fallback): array
    {
        $processing = is_array($plan['image_processing'] ?? null) ? $plan['image_processing'] : [];
        $resize = $processing['resize'] ?? data_get($fallback, 'image_processing.resize');
        if (is_string($resize) && preg_match('/(\d{2,5})\s*[xX×*]\s*(\d{2,5})/u', $resize, $m)) {
            $resize = ['width' => (int) $m[1], 'height' => (int) $m[2]];
        }
        if (! is_array($resize) || empty($resize['width']) || empty($resize['height'])) {
            $resize = null;
        }

        $fieldColumnMap = [];
        foreach ((array) ($plan['field_column_map'] ?? []) as $field => $column) {
            $field = trim((string) $field);
            $column = strtoupper(trim((string) $column));
            if ($field !== '' && preg_match('/^[A-Z]{1,3}$/', $column)) {
                $fieldColumnMap[$field] = $column;
            }
        }

        $format = strtolower((string) ($processing['format'] ?? data_get($fallback, 'image_processing.format', 'original')));
        if (! in_array($format, ['original', 'jpg', 'jpeg', 'png'], true)) {
            $format = 'original';
        }
        if ($format === 'jpeg') {
            $format = 'jpg';
        }

        return [
            'sheet_mode' => in_array(($plan['sheet_mode'] ?? 'all'), ['all', 'selected'], true) ? $plan['sheet_mode'] : 'all',
            'sheets' => array_values(array_filter((array) ($plan['sheets'] ?? []), 'is_string')),
            'header_row_by_sheet' => is_array($plan['header_row_by_sheet'] ?? null) ? $plan['header_row_by_sheet'] : [],
            'field_column_map' => $fieldColumnMap,
            'filename_template' => trim((string) ($plan['filename_template'] ?? $fallback['filename_template'])),
            'folder_template' => trim((string) ($plan['folder_template'] ?? $fallback['folder_template'] ?? '')),
            'image_match_rule' => 'anchor_row',
            'fallback_filename_template' => trim((string) ($plan['fallback_filename_template'] ?? $fallback['fallback_filename_template'])),
            'image_processing' => [
                'crop_whitespace' => (bool) ($processing['crop_whitespace'] ?? data_get($fallback, 'image_processing.crop_whitespace', false)),
                'resize' => $resize,
                'enhance' => (bool) ($processing['enhance'] ?? data_get($fallback, 'image_processing.enhance', false)),
                'format' => $format,
            ],
        ];
    }

    private function activeModelConfig(): ?ModelConfig
    {
        $config = ModelConfig::query()
            ->where('enabled', true)
            ->where('purpose', 'script')
            ->latest('id')
            ->first();

        if ($config && $config->base_url && $config->model && $config->api_key_encrypted) {
            return $config;
        }

        $provider = config('ai.default_provider', 'aliyun');
        $providerConfig = config("ai.providers.{$provider}", config('ai.providers.aliyun', []));
        $apiKeyEnv = $providerConfig['api_key_env'] ?? match ($provider) {
            'deepseek' => 'DEEPSEEK_API_KEY',
            'openai-compatible' => 'OPENAI_COMPATIBLE_API_KEY',
            default => 'DASHSCOPE_API_KEY',
        };

        $apiKey = trim((string) env($apiKeyEnv, ''));
        if ($apiKey === '' && $provider === 'aliyun') {
            $apiKey = trim((string) env('ALIYUN_API_KEY', ''));
        }
        if ($apiKey === '') {
            return null;
        }

        $defaults = config('ai.defaults.script', []);
        $config = new ModelConfig();
        $config->provider = $provider;
        $config->base_url = $defaults['base_url'] ?? ($providerConfig['base_url'] ?? null);
        $config->model = $defaults['model'] ?? ($providerConfig['model'] ?? null);
        $config->api_key_encrypted = Crypt::encryptString($apiKey);
        $config->temperature = $defaults['temperature'] ?? config('ai.temperature', 0.2);
        $config->max_tokens = $defaults['max_tokens'] ?? config('ai.max_tokens', 8192);
        $config->request_timeout = $defaults['request_timeout'] ?? config('ai.request_timeout', 180);

        return $config->base_url && $config->model ? $config : null;
    }

    private function explicitColumn(string $instruction, array $keywords): ?string
    {
        $keyword = '(?:'.implode('|', array_map(fn (string $v): string => preg_quote($v, '/'), $keywords)).')';
        if (preg_match('/\b([A-Z]{1,3})\s*列[^，。；;]*'.$keyword.'/iu', $instruction, $m)) {
            return strtoupper($m[1]);
        }
        if (preg_match('/'.$keyword.'[^，。；;]*\b([A-Z]{1,3})\s*列/iu', $instruction, $m)) {
            return strtoupper($m[1]);
        }

        return null;
    }

    private function summaryHasField(array $summary, array $keywords): bool
    {
        foreach (($summary['sheets'] ?? []) as $sheet) {
            foreach (($sheet['headers'] ?? []) as $header) {
                if ($this->containsAny((string) $header, $keywords)) {
                    return true;
                }
            }
        }

        return false;
    }

    private function containsAny(string $text, array $needles): bool
    {
        $haystack = mb_strtolower($text, 'UTF-8');
        foreach ($needles as $needle) {
            if ($needle !== '' && str_contains($haystack, mb_strtolower((string) $needle, 'UTF-8'))) {
                return true;
            }
        }

        return false;
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

    private function inferColumnFromSummary(array $summary, array $keywords, bool $barcode = false): ?string
    {
        $bestColumn = null;
        $bestScore = 0;

        foreach (($summary['sheets'] ?? []) as $sheet) {
            foreach (($sheet['column_samples'] ?? []) as $columnInfo) {
                $column = strtoupper(trim((string) ($columnInfo['column'] ?? '')));
                if (! preg_match('/^[A-Z]{1,3}$/', $column)) {
                    continue;
                }

                $score = 0;
                $header = (string) ($columnInfo['header'] ?? '');
                if ($this->containsAny($header, $keywords)) {
                    $score += 100;
                }

                foreach (($columnInfo['samples'] ?? []) as $sample) {
                    $value = is_array($sample) ? (string) ($sample['value'] ?? '') : (string) $sample;
                    if ($this->containsAny($value, $keywords)) {
                        $score += 30;
                    }
                    if ($barcode && $this->looksLikeBarcode($value)) {
                        $score += 80;
                    }
                }

                if ($score > $bestScore) {
                    $bestScore = $score;
                    $bestColumn = $column;
                }
            }
        }

        return $bestScore > 0 ? $bestColumn : null;
    }

    private function looksLikeBarcode(string $value): bool
    {
        return preg_match('/69\d{11}/', preg_replace('/\s+/', '', $value)) === 1;
    }

    private function publicAiError(Throwable $e): string
    {
        $message = $e->getMessage();
        $lower = mb_strtolower($message, 'UTF-8');

        if (str_contains($lower, 'invalid_api_key')
            || str_contains($lower, 'incorrect api key')
            || str_contains($lower, '401')) {
            return 'AI Key 无效，请在后台模型配置中更新阿里云 API Key。';
        }

        if (str_contains($lower, 'timeout') || str_contains($lower, 'timed out')) {
            return 'AI 请求超时，请稍后重试。';
        }

        return mb_substr($message, 0, 300, 'UTF-8');
    }
}
