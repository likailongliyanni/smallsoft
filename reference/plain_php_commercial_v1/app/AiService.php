<?php
class AiService
{
    public static function generate(array $modelConfig, array $workflow, array $excelSchema): string
    {
        if (!self::isReady($modelConfig)) {
            return self::fallbackScript($workflow, $excelSchema);
        }
        $prompt = self::buildPrompt($workflow, $excelSchema);
        $data = self::chat($modelConfig, [
            ['role' => 'system', 'content' => self::systemPrompt()],
            ['role' => 'user', 'content' => $prompt],
        ], 0.1, 4000);
        $content = $data['choices'][0]['message']['content'] ?? '';
        if (!is_string($content) || trim($content) === '') {
            throw new RuntimeException('empty model response');
        }
        return self::stripCodeFence($content);
    }

    public static function test(array $modelConfig): string
    {
        if (!self::isReady($modelConfig)) {
            throw new RuntimeException('model config is incomplete');
        }
        $data = self::chat($modelConfig, [
            ['role' => 'system', 'content' => '你是接口连通性测试助手。'],
            ['role' => 'user', 'content' => '只回复 OK'],
        ], 0, 20);
        return trim((string)($data['choices'][0]['message']['content'] ?? 'OK'));
    }

    public static function isReady(array $modelConfig): bool
    {
        return trim((string)($modelConfig['base_url'] ?? '')) !== ''
            && trim((string)($modelConfig['model_name'] ?? '')) !== ''
            && trim((string)($modelConfig['api_key'] ?? '')) !== '';
    }

    private static function chat(array $modelConfig, array $messages, float $temperature, int $maxTokens): array
    {
        $url = rtrim((string)$modelConfig['base_url'], '/');
        if (!str_ends_with($url, '/chat/completions')) {
            $url .= '/chat/completions';
        }
        $payload = json_encode([
            'model' => $modelConfig['model_name'],
            'messages' => $messages,
            'temperature' => $temperature,
            'max_tokens' => $maxTokens,
        ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);

        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_POST => true,
            CURLOPT_HTTPHEADER => [
                'Content-Type: application/json',
                'Authorization: Bearer ' . $modelConfig['api_key'],
            ],
            CURLOPT_POSTFIELDS => $payload,
            CURLOPT_TIMEOUT => 120,
        ]);
        $body = curl_exec($ch);
        $errno = curl_errno($ch);
        $error = curl_error($ch);
        $status = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        if ($errno) {
            throw new RuntimeException('model request failed: ' . $error);
        }
        if ($status < 200 || $status >= 300) {
            throw new RuntimeException('model http error ' . $status . ': ' . mb_substr((string)$body, 0, 500, 'UTF-8'));
        }
        $data = json_decode((string)$body, true);
        if (!is_array($data)) {
            throw new RuntimeException('invalid model json response');
        }
        return $data;
    }

    private static function buildPrompt(array $workflow, array $excelSchema): string
    {
        $steps = [];
        foreach (($workflow['steps'] ?? []) as $index => $step) {
            $selectors = $step['selectors'] ?? [];
            $steps[] = [
                'index' => $index + 1,
                'trigger' => $step['trigger'] ?? '',
                'control_type' => $step['control_type'] ?? '',
                'action' => $step['action'] ?? '',
                'exec_mode' => $step['exec_mode'] ?? '',
                'name' => $step['name'] ?? '',
                'column' => $step['column'] ?? '',
                'note' => $step['note'] ?? '',
                'selectors' => [
                    'label' => $selectors['label'] ?? '',
                    'placeholder' => $selectors['placeholder'] ?? '',
                    'text' => mb_substr((string)($selectors['text'] ?? ''), 0, 120, 'UTF-8'),
                    'css' => $selectors['css'] ?? '',
                    'xpath' => $selectors['xpath'] ?? '',
                    'id' => $selectors['id'] ?? '',
                    'name' => $selectors['name'] ?? '',
                ],
            ];
        }
        return "根据下面的流程协议生成 Python Playwright 自动化脚本，只输出代码：\n" . json_encode([
            'target_url' => $workflow['url'] ?? '',
            'version' => $workflow['version'] ?? '',
            'steps' => $steps,
            'excel_schema' => $excelSchema,
        ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
    }

    private static function systemPrompt(): string
    {
        return '你是网页批量自动化脚本生成器。只输出可以运行的 Python Playwright 脚本。脚本必须读取本地 workflow JSON 和 Excel。登录、验证码、短信、人机验证必须暂停让用户手动处理。不要写入真实账号密码。遇到低质量选择器时，用字段名、label、placeholder、按钮文本做兜底定位。';
    }

    private static function fallbackScript(array $workflow, array $excelSchema): string
    {
        $url = $workflow['url'] ?? '';
        $columns = $excelSchema['columns'] ?? [];
        $columnsText = implode(', ', array_map('strval', $columns));
        return "# -*- coding: utf-8 -*-\n"
            . "\"\"\"模型未配置时返回的商业版占位脚本。\n"
            . "目标网址：{$url}\n"
            . "Excel字段：{$columnsText}\n"
            . "\"\"\"\n\n"
            . "print('后台大模型未配置，当前是占位脚本。')\n"
            . "print('目标网址:', " . var_export($url, true) . ")\n"
            . "print('Excel字段:', " . var_export($columns, true) . ")\n";
    }

    private static function stripCodeFence(string $text): string
    {
        $text = trim($text);
        if (str_starts_with($text, '```')) {
            $lines = preg_split('/\R/', $text);
            array_shift($lines);
            if ($lines && trim((string)end($lines)) === '```') {
                array_pop($lines);
            }
            return trim(implode("\n", $lines)) . "\n";
        }
        return $text;
    }
}
