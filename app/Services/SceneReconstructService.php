<?php

namespace App\Services;

use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Http;
use RuntimeException;

/**
 * AI 商品主视觉 / 电商场景重构。
 *
 * 用户上传 2-6 张同一商品的参考图，两步生成一张全新的、像同一次拍摄出来的专业电商图：
 *   第一步 analyze()：视觉模型读全部图 → 结构化 JSON（识别作用、锁定商品特征、定场景方案）。
 *   第二步 render()： 把 JSON + 用户选项拼成最终绘图提示词 → 多图调百炼万相多模态端点 → 出新图。
 *
 * 复用「AI 修复」同一条阿里云 multimodal-generation 端点与 input.messages（图+文）结构，
 * 区别只是 content 里放多张参考图。模型名后台可换（ModelConfig purpose=scene_reconstruct）。
 */
class SceneReconstructService
{
    private const DASHSCOPE_BASE = 'https://dashscope.aliyuncs.com';
    private const COMPAT_BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1';
    private const IMAGE_GENERATION_ENDPOINT = '/api/v1/services/aigc/multimodal-generation/generation';
    private const FALLBACK_VISION_MODEL = 'qwen3.6-plus';
    private const FALLBACK_GEN_MODEL = 'wan2.7-image';

    public const RATIOS = ['1:1', '4:5', '3:4', '16:9', '9:16', '3:2', '2:3', '1:2'];
    public const USAGES = ['main', 'detail_header', 'scene', 'poster'];
    public const STYLES = ['auto', 'studio', 'lifestyle', 'premium', 'fresh'];
    public const STRENGTHS = ['standard', 'high'];

    /**
     * 端到端生成。
     *
     * @param  UploadedFile[]  $images  2-6 张参考图
     * @param  array  $options  ratio/usage/style/strength/copy_space/extra
     * @return array{image: string, analysis: array, prompt: string}  image 为 PNG 字节
     */
    public function generate(array $images, array $options): array
    {
        if (count($images) < 1) {
            throw new RuntimeException('请至少上传 1 张参考图。');
        }

        $dataUrls = [];
        foreach ($images as $img) {
            $dataUrls[] = $this->toDataUrl($img);
        }

        $analysis = $this->analyze($dataUrls, $options);
        $prompt = $this->buildPrompt($analysis, $options);
        $bytes = $this->render($dataUrls, $prompt, $options);

        return ['image' => $bytes, 'analysis' => $analysis, 'prompt' => $prompt];
    }

    /** 第一步：视觉模型读全部图，输出结构化分析 JSON。 */
    private function analyze(array $dataUrls, array $options): array
    {
        $content = [['type' => 'text', 'text' => $this->analyzePrompt($options)]];
        foreach ($dataUrls as $url) {
            $content[] = ['type' => 'image_url', 'image_url' => ['url' => $url]];
        }

        $response = Http::withToken($this->apiKey())
            ->timeout(120)
            ->acceptJson()
            ->post(self::COMPAT_BASE.'/chat/completions', [
                'model' => $this->visionModel(),
                'messages' => [['role' => 'user', 'content' => $content]],
                'temperature' => 0.1,
                'stream' => false,
            ]);

        $this->ensureSuccessful($response->status(), $response->body(), '商品图片分析失败');

        $text = data_get($response->json(), 'choices.0.message.content');
        if (is_array($text)) {
            $text = collect($text)->map(fn ($p) => is_array($p) ? ($p['text'] ?? '') : (string) $p)->implode('');
        }
        if (! is_string($text) || trim($text) === '') {
            throw new RuntimeException('商品图片分析返回为空。');
        }

        $data = $this->extractJson($text);
        if (! is_array($data) || $data === []) {
            // 分析失败不致命：用一个保底结构，让生成步骤仍能在「锁定商品、重构场景」原则下进行。
            $data = $this->fallbackAnalysis();
        }

        return $data;
    }

    /** 第二步：多图 + 最终提示词，调万相多模态端点生成新图，返回 PNG 字节。 */
    private function render(array $dataUrls, string $prompt, array $options): string
    {
        $content = [];
        foreach ($dataUrls as $url) {
            $content[] = ['image' => $url];
        }
        $content[] = ['text' => $prompt];

        $parameters = ['watermark' => false, 'n' => 1];
        $size = $this->ratioToSize($options['ratio'] ?? '1:1');
        if ($size !== '') {
            $parameters['size'] = $size;
        }

        $response = Http::withToken($this->apiKey())
            ->timeout(300)
            ->acceptJson()
            ->post(self::DASHSCOPE_BASE.self::IMAGE_GENERATION_ENDPOINT, [
                'model' => $this->genModel(),
                'input' => ['messages' => [['role' => 'user', 'content' => $content]]],
                'parameters' => $parameters,
            ]);

        $this->ensureSuccessful($response->status(), $response->body(), '生成商品主视觉失败');

        $resultUrl = $this->resultImageUrl($response->json() ?: []);
        $download = Http::timeout(300)->get($resultUrl);
        if (! $download->successful()) {
            throw new RuntimeException('下载生成结果失败：HTTP '.$download->status());
        }

        return $download->body();
    }

    // ───────────────────────── 提示词 ─────────────────────────

    private function analyzePrompt(array $options): string
    {
        return <<<'PROMPT'
你是资深电商视觉策划。下面是同一个商品的多张参考图（按上传顺序）。请综合所有图片，识别商品、锁定必须保留的特征、规划一个可落地的电商摄影场景。
要求：
1. 识别每张图的作用：hero_product(商品主体)、detail(细节/侧面/独立小包装)、scene(使用场景/效果)、composition_ref(构图/光线/机位参考)。
2. 提取并锁定商品特征：包装形状与比例、主色、品牌标志、核心商品名称、商品数量与包装形式。不得更换商品、品牌或包装风格；不得编造不存在的功能、卖点或宣传文字。
3. 规划一个全新的、统一的摄影场景：商品为视觉中心，场景为辅助，统一透视、光源、色温和阴影，背景干净，预留少量文案空间。可以补充合理的桌面、托盘、杯子、原料等道具，但不能抢商品主体。
只输出一个 JSON，不要解释、不要 Markdown。严格使用以下结构：
{
  "product_identity": {"category":"","brand":"","product_name":"","packaging":"","main_colors":[],"must_preserve":[]},
  "image_roles": [{"image_index":1,"role":"","useful_elements":[]}],
  "scene_plan": {"scene_type":"","hero_subject":"","supporting_elements":[],"composition":"","lighting":"","background":"","negative_space":""},
  "avoid": []
}
PROMPT;
    }

    /** 把分析 JSON + 用户选项拼成给绘图模型的最终中文提示词。 */
    private function buildPrompt(array $analysis, array $options): string
    {
        $ratio = $this->normalizeRatio($options['ratio'] ?? '1:1');
        $usage = $this->usageText($options['usage'] ?? 'main');
        $style = $this->styleText($options['style'] ?? 'auto');
        $strength = $this->strengthText($options['strength'] ?? 'standard');
        $copySpace = ! empty($options['copy_space']);
        $extra = trim((string) ($options['extra'] ?? ''));

        $identity = $analysis['product_identity'] ?? [];
        $brand = trim((string) ($identity['brand'] ?? ''));
        $name = trim((string) ($identity['product_name'] ?? ''));
        $packaging = trim((string) ($identity['packaging'] ?? ''));
        $colors = $this->joinList($identity['main_colors'] ?? []);
        $preserve = $this->joinList($identity['must_preserve'] ?? []);

        $plan = $analysis['scene_plan'] ?? [];
        $composition = trim((string) ($plan['composition'] ?? ''));
        $lighting = trim((string) ($plan['lighting'] ?? ''));
        $background = trim((string) ($plan['background'] ?? ''));
        $support = $this->joinList($plan['supporting_elements'] ?? []);
        $avoid = $this->joinList($analysis['avoid'] ?? []);

        $lines = [];
        $lines[] = '请把以上多张参考图中的同一个商品，重新组织成一张全新的、完整的电商摄影场景图。所有商品、道具、背景、阴影和光线必须像在同一次摄影中拍摄，画面是一次真实棚拍/实拍的成片。';
        $lines[] = '【商品锁定】保持商品本体不变：'
            .($brand !== '' ? "品牌「{$brand}」；" : '')
            .($name !== '' ? "商品名「{$name}」；" : '')
            .($packaging !== '' ? "包装为{$packaging}；" : '')
            .($colors !== '' ? "主色{$colors}；" : '')
            .'必须保持包装形状与比例、品牌标志、商品名称、真实包装文字、商品数量和包装形式与参考图一致。'
            .($preserve !== '' ? "尤其保留：{$preserve}。" : '');
        $lines[] = '不得更换商品、品牌或包装风格；不得生成不存在的功能、卖点、价格、宣传文字或标签；不得把商品画成卡通或过度美颜；看不清/被遮挡的部位只做最小修补，不要脑补不存在的结构。';
        $lines[] = "【用途】{$usage}";
        $lines[] = "【画面风格】{$style}";
        $lines[] = "【商品还原强度】{$strength}";
        $lines[] = '【构图与光线】商品是画面主要视觉中心并占据主要区域，使用场景与道具作为辅助、不抢主体；统一透视、统一光源方向、统一色温、统一自然柔和阴影；背景干净高级。'
            .($composition !== '' ? "参考构图：{$composition}。" : '')
            .($lighting !== '' ? "光线：{$lighting}。" : '')
            .($background !== '' ? "背景：{$background}。" : '')
            .($support !== '' ? "可补充道具：{$support}（合理摆放、不喧宾夺主）。" : '允许补充合理的桌面、托盘、杯子、原料等道具，但不能抢商品主体。');
        $lines[] = $copySpace
            ? '在画面一侧或上下预留一块干净的文案空间（负空间），但不要在图上写任何文字。'
            : '保持画面均衡，预留少量负空间，但不要写任何文字。';
        $lines[] = '【默认规则】比例 '.$ratio.'；不要添加任何宣传文字、水印、价格、标签或角标；不要出现拼接痕迹、原图边框、多宫格或分栏；输出单张干净清晰的成片。';
        if ($avoid !== '') {
            $lines[] = "【避免】{$avoid}。";
        }
        if ($extra !== '') {
            $lines[] = "【用户补充要求】{$extra}";
        }

        return implode("\n", $lines);
    }

    // ───────────────────────── 选项文案 ─────────────────────────

    private function usageText(string $usage): string
    {
        return match ($usage) {
            'detail_header' => '电商详情页头图：构图可稍宽、有氛围，承接详情页第一屏。',
            'scene' => '使用场景图：商品自然融入真实使用场景，体现使用方式或效果。',
            'poster' => '宣传海报：海报式构图，视觉冲击强，预留较多文案空间。',
            default => '电商商品主图：商品占画面主体，背景干净，适合平台首图上架。',
        };
    }

    private function styleText(string $style): string
    {
        return match ($style) {
            'studio' => '纯净棚拍：浅色/无缝纯色背景，柔和影棚光，商品居中干净。',
            'lifestyle' => '生活方式：真实生活场景（桌面、厨房、户外等），自然光，有使用氛围。',
            'premium' => '高级简约：高级质感、大量留白、克制配色，冷暖平衡，质感道具。',
            'fresh' => '清新自然：明亮通透，自然光，木质/植物等清新道具，柔和色调。',
            default => '由你根据商品品类自动选择最合适、最高级的电商摄影风格。',
        };
    }

    private function strengthText(string $strength): string
    {
        return $strength === 'high'
            ? '高：最大限度还原商品包装、颜色、品牌标志和包装文字的真实细节，几乎不改变商品本体外观，只重构背景与场景。'
            : '标准：在保持商品主体特征（外形、颜色、logo、文字）的前提下，允许对场景、道具和氛围做合理再创作。';
    }

    private function normalizeRatio(string $ratio): string
    {
        return in_array($ratio, self::RATIOS, true) ? $ratio : '1:1';
    }

    /** 比例 → 万相 size 像素串（短边 1024 左右，保证清晰）。 */
    private function ratioToSize(string $ratio): string
    {
        $configured = trim((string) config('ai.scene_reconstruct.size', ''));
        if ($configured !== '') {
            return $configured;
        }

        return match ($this->normalizeRatio($ratio)) {
            '4:5' => '1024*1280',
            '3:4' => '960*1280',
            '16:9' => '1280*720',
            '9:16' => '720*1280',
            '3:2' => '1248*832',
            '2:3' => '832*1248',
            '1:2' => '720*1440',
            default => '1024*1024',
        };
    }

    private function joinList($value): string
    {
        if (! is_array($value)) {
            return trim((string) $value);
        }

        return collect($value)
            ->map(fn ($v) => trim((string) (is_array($v) ? implode('', $v) : $v)))
            ->filter()
            ->implode('、');
    }

    private function fallbackAnalysis(): array
    {
        return [
            'product_identity' => [
                'category' => '', 'brand' => '', 'product_name' => '', 'packaging' => '',
                'main_colors' => [], 'must_preserve' => ['参考图中的包装形状、颜色、品牌标志、商品名称和数量'],
            ],
            'image_roles' => [],
            'scene_plan' => [
                'scene_type' => '电商主图', 'hero_subject' => '参考图中的商品',
                'supporting_elements' => [], 'composition' => '', 'lighting' => '', 'background' => '干净背景', 'negative_space' => '',
            ],
            'avoid' => ['拼接痕迹', '多宫格', '新增文字'],
        ];
    }

    // ───────────────────────── 阿里云调用通用件（与 WatermarkAiService 一致） ─────────────────────────

    private function toDataUrl(UploadedFile $image): string
    {
        $bytes = (string) file_get_contents($image->getRealPath());
        if ($bytes === '') {
            throw new RuntimeException('有一张参考图为空，无法生成。');
        }
        $mime = $image->getMimeType() ?: 'image/jpeg';

        return 'data:'.$mime.';base64,'.base64_encode($bytes);
    }

    private function apiKey(): string
    {
        $key = trim((string) config('ai.dashscope_api_key', ''));
        if ($key === '') {
            throw new RuntimeException('服务器未配置 DASHSCOPE_API_KEY。');
        }

        return $key;
    }

    private function visionModel(): string
    {
        return $this->adminModel('scene_vision')
            ?: ($this->adminModel('image_detect')
            ?: (trim((string) config('ai.defaults.vision.model', self::FALLBACK_VISION_MODEL)) ?: self::FALLBACK_VISION_MODEL));
    }

    private function genModel(): string
    {
        // 后台可单独给「场景重构」配更强的多图模型；没配则复用图片修复模型；再兜底常量。
        return $this->adminModel('scene_reconstruct')
            ?: ($this->adminModel('image_repair')
            ?: (trim((string) config('ai.scene_reconstruct.model', config('ai.image_repair.model', self::FALLBACK_GEN_MODEL))) ?: self::FALLBACK_GEN_MODEL));
    }

    private function adminModel(string $purpose): string
    {
        try {
            $model = \App\Models\ModelConfig::query()
                ->where('purpose', $purpose)
                ->where('enabled', true)
                ->value('model');

            return trim((string) $model);
        } catch (\Throwable $e) {
            return '';
        }
    }

    private function resultImageUrl(array $payload): string
    {
        $content = data_get($payload, 'output.choices.0.message.content', []);
        if (is_array($content)) {
            foreach ($content as $part) {
                $url = is_array($part) ? trim((string) ($part['image'] ?? '')) : '';
                if ($url !== '') {
                    return $url;
                }
            }
        }

        foreach (['output.results.0.url', 'output.images.0.url', 'output.image_url', 'data.0.url', 'url'] as $path) {
            $url = trim((string) data_get($payload, $path, ''));
            if ($url !== '') {
                return $url;
            }
        }

        throw new RuntimeException('生成成功但没有返回结果图链接。');
    }

    private function ensureSuccessful(int $status, string $body, string $prefix): void
    {
        if ($status >= 200 && $status < 300) {
            return;
        }

        $json = json_decode($body, true);
        $code = (string) data_get($json, 'error.code', data_get($json, 'code', $status));
        $message = (string) data_get($json, 'error.message', data_get($json, 'message', mb_substr($body, 0, 300)));

        throw new RuntimeException($prefix.'：'.$this->friendlyError($code, $message));
    }

    private function friendlyError(string $code, string $message): string
    {
        $text = strtolower($code.' '.$message);
        if (str_contains($text, 'invalidapikey') || str_contains($text, 'invalid_api_key') || str_contains($text, 'incorrect api key')) {
            return '阿里云 API Key 无效，请检查服务器 .env 的 DASHSCOPE_API_KEY。';
        }
        if (str_contains($text, 'access_denied') || str_contains($text, 'access denied') || str_contains($text, 'model not exist') || str_contains($text, 'modelnotfound')) {
            return '阿里云模型权限不足：当前 Key 无权调用生成模型（'.$this->genModel().'），请在百炼开通对应模型，或在后台把「场景重构」模型改成已开通的多图生成/编辑模型。';
        }
        if (str_contains($text, 'arrearage')) {
            return '阿里云账户欠费，请到百炼控制台充值。';
        }
        if (str_contains($text, 'throttling') || str_contains($text, 'ratelimit') || str_contains($text, 'rate limit')) {
            return '阿里云接口被限流，请稍后重试。';
        }
        if (str_contains($text, 'datainspection') || str_contains($text, 'inappropriate') || str_contains($text, 'green')) {
            return '图片未通过内容审核，已跳过。';
        }

        return mb_substr($code.'：'.$message, 0, 300);
    }

    private function extractJson(string $content): array
    {
        $content = trim($content);
        if (preg_match('/```(?:json)?\s*(.*?)\s*```/s', $content, $matches)) {
            $content = trim($matches[1]);
        }
        if (preg_match('/\{.*\}/s', $content, $matches)) {
            $data = json_decode($matches[0], true);

            return is_array($data) ? $data : [];
        }

        return [];
    }
}
