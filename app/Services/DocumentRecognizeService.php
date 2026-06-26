<?php

namespace App\Services;

use App\Models\ModelConfig;
use Illuminate\Support\Facades\Http;
use RuntimeException;
use Throwable;

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

        $response = Http::withToken($this->apiKey())
            ->timeout(180)
            ->acceptJson()
            ->post(self::COMPAT_BASE.'/chat/completions', [
                'model' => $this->model(),
                'messages' => [['role' => 'user', 'content' => $content]],
                'temperature' => 0.1,
                'stream' => false,
            ]);

        $this->ensureSuccessful($response->status(), $response->body());

        $out = data_get($response->json(), 'choices.0.message.content');
        if (is_array($out)) {
            $out = collect($out)->map(fn ($p) => is_array($p) ? ($p['text'] ?? '') : (string) $p)->implode('');
        }
        $out = is_string($out) ? trim($out) : '';
        if ($out === '') {
            throw new RuntimeException('证件识别返回为空。');
        }

        return ['content' => $out, 'fields' => $this->extractJson($out)];
    }

    private function apiKey(): string
    {
        $key = trim((string) config('ai.dashscope_api_key', ''));
        if ($key === '') {
            throw new RuntimeException('服务器未配置 DASHSCOPE_API_KEY。');
        }

        return $key;
    }

    /** 后台可单独给「证件识别」配模型(purpose=document_recognize)；否则复用通用视觉模型。 */
    private function model(): string
    {
        try {
            $admin = trim((string) ModelConfig::query()
                ->where('purpose', 'document_recognize')
                ->where('enabled', true)
                ->value('model'));
            if ($admin !== '') {
                return $admin;
            }
        } catch (Throwable $e) {
            // 忽略，走配置兜底
        }

        return trim((string) config('ai.defaults.vision.model', self::FALLBACK_MODEL)) ?: self::FALLBACK_MODEL;
    }

    private function ensureSuccessful(int $status, string $body): void
    {
        if ($status >= 200 && $status < 300) {
            return;
        }
        $json = json_decode($body, true);
        $code = (string) data_get($json, 'error.code', data_get($json, 'code', $status));
        $message = (string) data_get($json, 'error.message', data_get($json, 'message', mb_substr($body, 0, 300)));
        $text = strtolower($code.' '.$message);

        if (str_contains($text, 'invalidapikey') || str_contains($text, 'invalid_api_key') || str_contains($text, 'incorrect api key')) {
            throw new RuntimeException('证件识别失败：阿里云 API Key 无效，请检查服务器 .env 的 DASHSCOPE_API_KEY。');
        }
        if (str_contains($text, 'access_denied') || str_contains($text, 'model not exist') || str_contains($text, 'modelnotfound')) {
            throw new RuntimeException('证件识别失败：当前 Key 无权调用视觉模型（'.$this->model().'），请在百炼开通，或在后台配置 document_recognize 模型。');
        }
        if (str_contains($text, 'arrearage')) {
            throw new RuntimeException('证件识别失败：阿里云账户欠费，请到百炼控制台充值。');
        }
        if (str_contains($text, 'throttling') || str_contains($text, 'ratelimit') || str_contains($text, 'rate limit')) {
            throw new RuntimeException('证件识别失败：阿里云接口被限流，请稍后重试。');
        }

        throw new RuntimeException('证件识别失败：'.mb_substr($code.'：'.$message, 0, 300, 'UTF-8'));
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
