<?php

namespace App\Services;

use RuntimeException;

class DocumentAssistantService
{
    public function __construct(private SoftwareAiConfigService $ai) {}

    /**
     * @param  array<int, array{role?: string, content?: string}>  $history
     * @param  array<int, array<string, mixed>>  $inventory
     * @return array<string, mixed>
     */
    public function chat(string $message, array $history, array $inventory, array $options = []): array
    {
        $config = $this->ai->find('aidoc', 'assistant_chat', false);
        if (! $config) {
            throw new RuntimeException('后台还没有配置“AI 文档管理 / AI 档案秘书”。请管理员先到软件配置中保存。');
        }

        $inventory = array_values(array_slice($inventory, 0, 400));
        $validIds = collect($inventory)
            ->pluck('id')
            ->filter(fn ($id) => is_int($id) || ctype_digit((string) $id))
            ->map(fn ($id) => (int) $id)
            ->unique()
            ->values()
            ->all();

        $system = trim((string) $config->system_prompt);
        if ($system === '') {
            $system = '你是企业的 AI 档案秘书，负责档案查询、材料整理和合同/常用档案文书起草。只能选择库存中存在的文件，只输出 JSON。';
        }
        $knowledge = trim((string) $config->knowledge_base);
        $system .= "\n\n办事材料知识库：\n".($knowledge !== '' ? $knowledge : '暂无，请基于常识谨慎判断。');
        $trainingNotes = collect((array) ($options['training_notes'] ?? []))
            ->filter(fn ($note) => is_array($note) && filled($note['instruction'] ?? null))
            ->map(fn ($note) => [
                '场景' => mb_substr((string) ($note['title'] ?? ''), 0, 100),
                '触发词' => mb_substr((string) ($note['trigger_keywords'] ?? ''), 0, 500),
                '用户培训内容' => mb_substr((string) ($note['instruction'] ?? ''), 0, 12000),
            ])->values()->all();
        if ($trainingNotes !== []) {
            $system .= "\n\n本轮命中的本地培训笔记（这是用户明确教给你的业务经验，优先遵守；若与本轮需求明显无关则不要套用）：\n".
                json_encode($trainingNotes, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        }
        $templatePool = collect((array) ($options['template_pool'] ?? []))
            ->filter(fn ($item) => is_array($item) && filled($item['id'] ?? null) && filled($item['template_text'] ?? null))
            ->map(fn ($item) => [
                'id' => (int) $item['id'],
                'name' => mb_substr((string) ($item['name'] ?? ''), 0, 100),
                'document_type' => mb_substr((string) ($item['document_type'] ?? 'other'), 0, 80),
                'type_label' => mb_substr((string) ($item['type_label'] ?? ''), 0, 100),
                'source_document_id' => (int) ($item['source_document_id'] ?? 0),
                'summary' => mb_substr((string) ($item['summary'] ?? ''), 0, 500),
                'variables' => array_slice((array) ($item['variables'] ?? []), 0, 50),
                'template_text' => mb_substr((string) ($item['template_text'] ?? ''), 0, 18000),
            ])->take(16)->values()->all();
        $validTemplateIds = collect($templatePool)->pluck('id')->map(fn ($id) => (int) $id)->all();
        $system .= <<<'PROMPT'


你的岗位是“AI 档案秘书”，能力包括：
1. 查询库存档案，说明现有材料和缺失材料。
2. 按用户事项整理库存文件。
3. 根据用户要求起草合同、协议及常用档案文书。先检索“本地文书模板资源池”，存在匹配模板时优先沿用模板；没有完全匹配模板时，才参考相近模板和用户要求综合起草。缺少关键事实时先追问，不得编造。
4. 起草文书不代表必须导出库存文件；除非用户同时选择“需要整理文件”，否则 gather_ids 仍必须为空。

模板使用规则：
- 资源池模板 id 和库存资料 id 是两套编号，不得混用。
- 用户要求“其他条款不变/完全相同”时，必须选择最接近的模板，只修改用户明确指定的变量，不得自行增加标准、地址、期限、违约比例等内容。
- 没有匹配模板时，要明确说明是“综合起草”，不能谎称套用了某份模板。
- reply 中说明本次使用的模板名称，或者说明未命中模板。

当用户明确要求“按库存中的某份合同修改并生成/导出新合同”时，必须额外返回 contract_job：
- 没有明确要求生成文件时，contract_job 必须为 null。
- template_id：本地文书模板资源池中的合同模板 id，必须来自本轮模板资源池且类型为 contract。
- supplier_name：新合同乙方全称。没有可靠名称时先追问，不得编造。
- supporting_ids：用于读取新供应商营业执照、开户/税务资料的库存 id；只放确实相关的文件。
- line_items：新商品明细数组，每项包含 name、specification、quantity、unit、unit_price、remark。数量或单价不明确时先追问，不生成任务。
- delivery_address：用户明确指定的新交付地点；未要求修改时返回空字符串。
- delivery_deadline：用户明确指定的新交货时间，必须保留用户原意；未要求修改时返回空字符串。
- payment_terms：用户明确指定的新付款条件，必须写成可直接放入合同的完整句子；未要求修改时返回空字符串。
- preserve_other_terms 固定为 true，表示桌面端只替换上述明确字段、乙方、乙方收款资料和商品表，其余原合同条款逐字保留。
- output_name：简洁的新合同文件名，不带路径；建议以商品名结尾。
- 用户说“只要一个合同”时，gather_ids 必须为空，不要再附带模板原件或供应商资质；生成件由 contract_job 单独输出。
- 绝不能声称已经修改库存 PDF。只有返回完整 contract_job 后，桌面端才会真正生成新文件。

当用户明确要求生成/导出授权书、证明、声明、申请书等非合同文书，或者没有可安全套用的合同模板但用户仍明确要求综合生成文件时，返回 document_job：
- 未明确要求生成文件时必须为 null。
- template_id：命中资源池时填模板 id；综合起草时填 0。
- document_type、title、output_name：文书类型、标题、文件名。
- content：完整可直接落地的正文，不能只给提纲；必须遵守用户明确要求。
- 综合生成合同但没有安全模板时，document_type 必须填 contract，桌面端会直接生成 PDF；不能只在 reply 里口头说已生成。
- 生成合同时若已经返回 contract_job，则 document_job 必须为 null，避免生成两个文件。
- reply 只能说“准备生成/将生成”；桌面端成功写出文件后才会追加“已生成”。

本系统还支持“按需整理”和“导出水印”：
1. 用户未选择整理时，gather_ids 必须返回空数组，只回答问题，不触发文件导出。
2. 用户选择整理时，才返回需要整理的库存 id。
3. 用户选择水印时，根据本轮事项给出简洁稳妥的 watermark_text，例如“仅供XX项目投标使用，再次复印无效”；不要加入未知公司名或敏感信息。
4. watermark_text 最长 60 个汉字，用户可以在导出前修改。
5. 始终只返回一个 JSON 对象，至少包含 reply、gather_ids、need_follow_up、missing_materials、selection_reasons、watermark_text、contract_job、document_job。
PROMPT;

        $messages = [['role' => 'system', 'content' => $system]];
        foreach (array_slice($history, -12) as $item) {
            $role = ($item['role'] ?? '') === 'assistant' ? 'assistant' : 'user';
            $content = trim((string) ($item['content'] ?? ''));
            if ($content !== '') {
                $messages[] = ['role' => $role, 'content' => mb_substr($content, 0, 2000)];
            }
        }
        $messages[] = [
            'role' => 'user',
            'content' => "用户本轮需求：\n{$message}\n\n用户导出选择：\n".
                '- 需要整理文件：'.(! empty($options['need_organize']) ? '是' : '否')."\n".
                '- 导出文件加水印：'.(! empty($options['use_watermark']) ? '是' : '否')."\n".
                '- 用户预填水印：'.trim((string) ($options['watermark_text'] ?? ''))."\n\n".
                "当前库存清单（只可使用这里的 id）：\n".
                json_encode($inventory, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES)."\n\n".
                "本地文书模板资源池（生成文书优先使用；template_id 只可使用这里的 id）：\n".
                ($templatePool !== []
                    ? json_encode($templatePool, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES)
                    : '当前资源池为空，可按用户要求综合起草，但不得声称使用了现有模板。'),
        ];

        $raw = $this->ai->chat($config, $messages);
        $content = data_get($raw, 'choices.0.message.content');
        if (is_array($content)) {
            $content = collect($content)
                ->map(fn ($part) => is_array($part) ? ($part['text'] ?? '') : (string) $part)
                ->implode('');
        }
        $data = $this->extractJson((string) $content);
        if ($data === []) {
            throw new RuntimeException('AI 档案秘书没有返回有效 JSON，请在后台检查提示词或更换模型。');
        }

        $ids = collect((array) ($data['gather_ids'] ?? []))
            ->filter(fn ($id) => is_int($id) || ctype_digit((string) $id))
            ->map(fn ($id) => (int) $id)
            ->filter(fn (int $id) => in_array($id, $validIds, true))
            ->unique()
            ->take(100)
            ->values()
            ->all();

        $reasons = collect((array) ($data['selection_reasons'] ?? []))
            ->filter(fn ($reason, $id) => in_array((int) $id, $ids, true) && is_string($reason))
            ->mapWithKeys(fn ($reason, $id) => [(string) ((int) $id) => mb_substr($reason, 0, 200)])
            ->all();

        $contractJob = null;
        $rawJob = $data['contract_job'] ?? null;
        if (is_array($rawJob)) {
            $templateId = (int) ($rawJob['template_id'] ?? 0);
            $template = collect($templatePool)->first(
                fn ($item) => (int) ($item['id'] ?? 0) === $templateId
                    && (string) ($item['document_type'] ?? '') === 'contract'
            );
            $supplierName = mb_substr(trim((string) ($rawJob['supplier_name'] ?? '')), 0, 200);
            $lineItems = collect((array) ($rawJob['line_items'] ?? []))
                ->filter(fn ($item) => is_array($item) && filled($item['name'] ?? null))
                ->map(fn ($item) => [
                    'name' => mb_substr(trim((string) ($item['name'] ?? '')), 0, 200),
                    'specification' => mb_substr(trim((string) ($item['specification'] ?? '')), 0, 200),
                    'quantity' => (float) ($item['quantity'] ?? 0),
                    'unit' => mb_substr(trim((string) ($item['unit'] ?? '')), 0, 20),
                    'unit_price' => (float) ($item['unit_price'] ?? 0),
                    'remark' => mb_substr(trim((string) ($item['remark'] ?? '')), 0, 200),
                ])
                ->filter(fn ($item) => $item['quantity'] > 0 && $item['unit_price'] >= 0)
                ->take(30)->values()->all();
            if ($template && $supplierName !== '' && $lineItems !== []) {
                $supportingIds = collect((array) ($rawJob['supporting_ids'] ?? []))
                    ->filter(fn ($id) => is_int($id) || ctype_digit((string) $id))
                    ->map(fn ($id) => (int) $id)
                    ->filter(fn ($id) => in_array($id, $validIds, true))
                    ->unique()->take(20)->values()->all();
                $contractJob = [
                    'template_id' => $templateId,
                    'supplier_name' => $supplierName,
                    'supporting_ids' => $supportingIds,
                    'line_items' => $lineItems,
                    'delivery_address' => mb_substr(trim((string) ($rawJob['delivery_address'] ?? '')), 0, 300),
                    'delivery_deadline' => mb_substr(trim((string) ($rawJob['delivery_deadline'] ?? '')), 0, 300),
                    'payment_terms' => mb_substr(trim((string) ($rawJob['payment_terms'] ?? '')), 0, 500),
                    'preserve_other_terms' => true,
                    'output_name' => mb_substr(trim((string) ($rawJob['output_name'] ?? '新合同')), 0, 100),
                ];
            }
        }
        $documentJob = null;
        $rawDocumentJob = $data['document_job'] ?? null;
        if (! $contractJob && is_array($rawDocumentJob)) {
            $documentTemplateId = (int) ($rawDocumentJob['template_id'] ?? 0);
            $templateValid = $documentTemplateId === 0 || in_array($documentTemplateId, $validTemplateIds, true);
            $title = mb_substr(trim((string) ($rawDocumentJob['title'] ?? '')), 0, 100);
            $body = mb_substr(trim((string) ($rawDocumentJob['content'] ?? '')), 0, 80000);
            if ($templateValid && $title !== '' && mb_strlen($body) >= 20) {
                $documentJob = [
                    'template_id' => $documentTemplateId,
                    'document_type' => mb_substr(trim((string) ($rawDocumentJob['document_type'] ?? 'other')), 0, 80),
                    'title' => $title,
                    'content' => $body,
                    'output_name' => mb_substr(trim((string) ($rawDocumentJob['output_name'] ?? $title)), 0, 100),
                ];
            }
        }
        if ($contractJob && preg_match('/只要.{0,8}合同|仅.{0,8}合同|不需要.{0,8}(资料|附件)/u', $message)) {
            $ids = [];
        }

        $reply = mb_substr(trim((string) ($data['reply'] ?? '我已经按你的要求核对了库存。')), 0, 8000);
        if (! $contractJob && ! $documentJob && preg_match('/已(?:经)?(?:生成|导出|制作).{0,40}(?:合同|文件|文书|PDF|DOCX)/iu', $reply)) {
            $reply .= "\n\n系统核验：本轮没有收到可执行的文件生成任务，因此尚未生成本地文件。请补充关键信息，并明确要求“生成并导出 PDF”。";
        }

        return [
            'reply' => $reply,
            'gather_ids' => $ids,
            'need_follow_up' => (bool) ($data['need_follow_up'] ?? false),
            'missing_materials' => collect((array) ($data['missing_materials'] ?? []))
                ->filter(fn ($item) => is_string($item) && trim($item) !== '')
                ->map(fn ($item) => mb_substr(trim($item), 0, 100))
                ->unique()->take(50)->values()->all(),
            'selection_reasons' => $reasons,
            'watermark_text' => mb_substr(trim((string) ($data['watermark_text'] ?? '')), 0, 60),
            'contract_job' => $contractJob,
            'document_job' => $documentJob,
            'model' => $config->model,
            'usage' => data_get($raw, 'usage'),
        ];
    }

    private function extractJson(string $content): array
    {
        $content = trim($content);
        if (preg_match('/```(?:json)?\s*(.*?)\s*```/s', $content, $match)) {
            $content = trim($match[1]);
        }
        $decoded = json_decode($content, true);
        if (is_array($decoded)) {
            return $decoded;
        }
        if (preg_match('/\{.*\}/s', $content, $match)) {
            $decoded = json_decode($match[0], true);
            return is_array($decoded) ? $decoded : [];
        }

        return [];
    }
}
