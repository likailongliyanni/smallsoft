<?php

namespace App\Services;

use App\Models\ModelConfig;
use RuntimeException;

/**
 * 桌面「AI 档案管理」证件识别。
 *
 * 桌面端把证据（有文字层的正文 / 扫描件渲染出的页图 base64）+ 识别提示词发上来，
 * 这里调阿里云视觉/文本模型（复用「AI 商品主视觉」同一条 compatible-mode 端点与
 * input.messages 图+文结构），让模型判断证件类型并提取结构化字段，回 JSON 文本。
 *
 * 服务器只做「证据 -> 模型 -> JSON 文本」，不落库；归一化/合并/入库都在桌面本地。
 */
class DocumentRecognizeService
{
    private const COMPAT_BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1';
    private const FALLBACK_MODEL = 'qwen3.6-plus';

    public function __construct(private SoftwareAiConfigService $ai) {}

    /**
     * @param  string  $mode  'vision'（页图）| 'text'（正文）
     * @param  string  $text  文字证据（text 模式）
     * @param  string[]  $imagesB64  PNG 的 base64（vision 模式，不含 data: 前缀），最多用前 4 张
     * @param  string  $instruction  识别提示词（桌面 docintel.extraction_instruction 生成）
     * @return array{content: string, fields: array}  content 为模型原始 JSON 文本，fields 为服务器侧解析结果
     */
    public function recognize(string $mode, string $text, array $imagesB64, string $instruction): array
    {
        $instruction = trim($instruction) !== '' ? trim($instruction) : '你是供应商资料库的文档管理员，请判断证件类型并提取结构化字段，只输出 JSON。';

        $content = [];
        if ($mode === 'vision') {
            $images = array_values(array_filter($imagesB64, fn ($b) => is_string($b) && $b !== ''));
            if ($images === []) {
                throw new RuntimeException('没有可识别的证件图片。');
            }
            $content[] = ['type' => 'text', 'text' => $instruction."\n\n下面是同一份证件的页面图片，请识别并只输出 JSON。"];
            foreach (array_slice($images, 0, 4) as $b64) {
                $content[] = ['type' => 'image_url', 'image_url' => ['url' => 'data:image/png;base64,'.$b64]];
            }
        } else {
            $body = trim($text);
            if ($body === '') {
                throw new RuntimeException('没有可识别的文字内容。');
            }
            $content[] = ['type' => 'text', 'text' => $instruction."\n\n证件正文如下，请识别并只输出 JSON：\n".mb_substr($body, 0, 16000, 'UTF-8')];
        }

        $config = $this->modelConfig();
        $messages = [];
        if (filled($config->system_prompt)) {
            $messages[] = ['role' => 'system', 'content' => (string) $config->system_prompt];
        }
        $messages[] = ['role' => 'user', 'content' => $content];
        $response = $this->ai->chat(
            $config,
            $messages,
            ['temperature' => (float) ($config->temperature ?? 0.1)],
        );

        $out = data_get($response, 'choices.0.message.content');
        if (is_array($out)) {
            $out = collect($out)->map(fn ($p) => is_array($p) ? ($p['text'] ?? '') : (string) $p)->implode('');
        }
        $out = is_string($out) ? trim($out) : '';
        if ($out === '') {
            throw new RuntimeException('证件识别返回为空。');
        }

        return ['content' => $out, 'fields' => $this->extractJson($out)];
    }

    /** 后台按软件读取完整配置；未迁移时仍使用原来的阿里云默认值。 */
    private function modelConfig(): ModelConfig
    {
        $config = $this->ai->find('aidoc', 'document_recognize', false);
        if ($config) {
            return $config;
        }

        return new ModelConfig([
            'software_code' => 'aidoc',
            'purpose' => 'document_recognize',
            'provider' => 'aliyun',
            'base_url' => self::COMPAT_BASE,
            'model' => trim((string) config('ai.defaults.vision.model', self::FALLBACK_MODEL)) ?: self::FALLBACK_MODEL,
            'enabled' => true,
            'temperature' => 0.1,
            'max_tokens' => 4096,
            'request_timeout' => 180,
        ]);
    }

    private function extractJson(string $content): array
    {
        $content = trim($content);
        if (preg_match('/```(?:json)?\s*(.*?)\s*```/s', $content, $m)) {
            $content = trim($m[1]);
        }
        if (preg_match('/\{.*\}/s', $content, $m)) {
            $data = json_decode($m[0], true);

            return is_array($data) ? $data : [];
        }

        return [];
    }
}
