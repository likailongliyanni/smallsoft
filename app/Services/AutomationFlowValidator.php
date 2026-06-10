<?php

namespace App\Services;

use Illuminate\Validation\ValidationException;

class AutomationFlowValidator
{
    private const FIELD_REQUIRED_TYPES = [
        'text_input',
        'file_upload',
    ];

    private const LOCATOR_OPTIONAL_EVENTS = [
        'wait',
        'manual',
        'manual_verify',
        'navigate',
    ];

    public function normalize(array $payload, int $stepLimit): array
    {
        $steps = $payload['steps'] ?? [];
        if (! is_array($steps) || count($steps) === 0) {
            throw ValidationException::withMessages(['steps' => '至少需要登记 1 个步骤。']);
        }

        if (count($steps) > $stepLimit) {
            throw ValidationException::withMessages([
                'steps' => "当前模式最多允许 {$stepLimit} 步，请拆成多个子流程。",
            ]);
        }

        // 如果是新版 JSON DSL 格式，跳过严格校验（client 已自己整理过）
        $isJsonDsl = ($payload['format'] ?? '') === 'json_dsl_v1';

        $warnings = [];
        $normalizedSteps = [];
        $templateFields = $this->normalizeTemplateFields($payload['template_fields'] ?? []);
        $fieldStepMap = [];

        foreach (array_values($steps) as $index => $step) {
            if (! is_array($step)) {
                throw ValidationException::withMessages(['steps' => '步骤必须是对象数组。']);
            }

            $order = (int) ($step['order'] ?? $step['step'] ?? $step['step_index'] ?? $index + 1);
            $event = $this->cleanToken($step['event'] ?? $step['action'] ?? $step['action_type'] ?? 'click');
            $type = $this->cleanToken($step['interaction_type'] ?? $step['type'] ?? $this->typeFromEvent($event));

            // 兼容多种字段名：field_name (旧) / excel_column (新)
            $fieldName = trim((string) (
                $step['field_name']
                ?? $step['excel_column']
                ?? ''
            ));

            if ($event === 'double_click') {
                $event = 'dblclick';
            }

            if ($type === 'input') {
                $type = 'text_input';
            }

            // 新版 JSON DSL 跳过"必须填写字段名"的严格校验
            // 因为新版客户端在整理页已经让用户决定（excel_column 留空 = 用录制时固定值）
            if (! $isJsonDsl
                && in_array($type, self::FIELD_REQUIRED_TYPES, true)
                && $fieldName === ''
            ) {
                throw ValidationException::withMessages([
                    'field_name' => "第 {$order} 步是需要表格数据的 {$type}，必须填写字段名称。",
                ]);
            }

            if (! $this->hasLocator($step) && ! in_array($event, self::LOCATOR_OPTIONAL_EVENTS, true)) {
                $warnings[] = "第 {$order} 步没有 xpath/css/text 定位信息，AI 只能根据描述猜测，稳定性会下降。";
            }

            if ($fieldName !== '') {
                $fieldStepMap[$fieldName][] = [
                    'order' => $order,
                    'event' => $event,
                    'interaction_type' => $type,
                ];

                if (! isset($templateFields[$fieldName])) {
                    $templateFields[$fieldName] = [
                        'field_name' => $fieldName,
                        'type' => $type === 'file_upload' ? 'file' : 'text',
                        'required' => true,
                        'description' => $step['description'] ?? '',
                    ];
                }
            }

            $normalizedSteps[] = [
                ...$step,
                'order' => $order,
                'event' => $event,
                'interaction_type' => $type,
                'field_name' => $fieldName ?: null,
            ];
        }

        // 新版 DSL 不强制要求"输入字段必须先点击"
        if (! $isJsonDsl) {
            foreach ($fieldStepMap as $fieldName => $fieldSteps) {
                $hasFocus = collect($fieldSteps)->contains(fn (array $item): bool => in_array($item['event'], ['click', 'dblclick'], true));
                $hasInput = collect($fieldSteps)->contains(fn (array $item): bool => $item['event'] === 'input' || $item['interaction_type'] === 'text_input');

                if ($hasInput && ! $hasFocus) {
                    $warnings[] = "字段「{$fieldName}」有文本输入步骤，但没有看到前置点击/双击输入框步骤。";
                }
            }
        }

        return [
            ...$payload,
            'steps' => $normalizedSteps,
            'template_fields' => array_values($templateFields),
            'warnings' => $warnings,
        ];
    }

    public function interactionTypes(): array
    {
        return [
            [
                'key' => 'single_click',
                'label' => '单击',
                'events' => ['click'],
                'requires_field_name' => false,
                'description' => '按钮、链接、普通菜单项，只记录点击动作。',
            ],
            [
                'key' => 'double_click',
                'label' => '双击',
                'events' => ['dblclick'],
                'requires_field_name' => false,
                'description' => '需要双击触发的控件。',
            ],
            [
                'key' => 'text_input',
                'label' => '文本输入',
                'events' => ['click', 'input'],
                'requires_field_name' => true,
                'description' => '先点击输入框，再登记输入动作，必须填写字段名称。',
            ],
            [
                'key' => 'select_open',
                'label' => '打开下拉',
                'events' => ['click'],
                'requires_field_name' => false,
                'description' => '点击打开下拉菜单或弹出选择层。',
            ],
            [
                'key' => 'select_option',
                'label' => '选择选项',
                'events' => ['click'],
                'requires_field_name' => false,
                'description' => '点击下拉菜单里的固定选项。',
            ],
            [
                'key' => 'file_upload',
                'label' => '本地文件上传',
                'events' => ['upload'],
                'requires_field_name' => true,
                'description' => '图片、附件、视频等本地文件路径必须来自表格字段。',
            ],
            [
                'key' => 'manual_verify',
                'label' => '人工验证',
                'events' => ['manual_verify'],
                'requires_field_name' => false,
                'description' => '验证码、短信、滑块、登录风控等由人工处理。',
            ],
            [
                'key' => 'wait',
                'label' => '等待',
                'events' => ['wait'],
                'requires_field_name' => false,
                'description' => '等待页面加载或等待某个结果出现。',
            ],
        ];
    }

    private function cleanToken(mixed $value): string
    {
        return strtolower(trim((string) $value));
    }

    private function typeFromEvent(string $event): string
    {
        return match ($event) {
            'input', 'fill', 'type' => 'text_input',
            'upload', 'set_input_files' => 'file_upload',
            'dblclick', 'double_click' => 'double_click',
            'manual', 'manual_verify' => 'manual_verify',
            default => 'single_click',
        };
    }

    private function normalizeTemplateFields(mixed $fields): array
    {
        $normalized = [];
        if (! is_array($fields)) {
            return $normalized;
        }

        foreach ($fields as $field) {
            if (! is_array($field)) {
                continue;
            }

            $name = trim((string) ($field['field_name'] ?? $field['name'] ?? ''));
            if ($name === '') {
                continue;
            }

            $normalized[$name] = [
                'field_name' => $name,
                'type' => $field['type'] ?? 'text',
                'required' => (bool) ($field['required'] ?? true),
                'description' => $field['description'] ?? '',
            ];
        }

        return $normalized;
    }

    private function hasLocator(array $step): bool
    {
        foreach (['xpath', 'css_selector', 'selector', 'text_hint', 'text'] as $key) {
            if (isset($step[$key]) && trim((string) $step[$key]) !== '') {
                return true;
            }
        }

        return false;
    }
}
