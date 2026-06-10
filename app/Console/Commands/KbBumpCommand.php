<?php

namespace App\Console\Commands;

use App\Services\KbVersionService;
use Illuminate\Console\Command;

/**
 * 命令行手动升级经验库版本号
 *
 * 用法：
 *   php artisan kb:bump "推送了下拉触发器修复"
 *   php artisan kb:bump --set=1.2.0 "重大版本升级"
 *
 * 服务器部署后调用一次，客户端"检查更新"才会发现变化
 */
class KbBumpCommand extends Command
{
    protected $signature = 'kb:bump
                            {note? : 本次变更说明（会显示给用户看）}
                            {--set= : 直接设置某个版本号，如 1.2.0}';

    protected $description = '升级 AI 经验库版本号（部署新内容后调用）';

    public function handle(KbVersionService $kb): int
    {
        $note = $this->argument('note') ?: '后台部署';
        $setVersion = $this->option('set');

        $before = $kb->current();
        $beforeV = $before['version'] ?? 'N/A';

        if ($setVersion) {
            $meta = $kb->setVersion($setVersion, $note);
            $this->info("✓ 已设置经验库版本号：{$beforeV}  →  {$meta['version']}");
        } else {
            $meta = $kb->bump($note);
            $this->info("✓ 经验库版本号已升级：{$beforeV}  →  {$meta['version']}");
        }

        $this->line('');
        $this->line('  📌 变更说明：' . ($meta['latest_change'] ?? '无'));
        $this->line('  🕐 更新时间：' . ($meta['updated_at'] ?? '无'));
        $this->line('  📦 启用的自定义经验数：' . ($meta['count'] ?? 0));
        $this->line('');
        $this->comment('用户下次启动软件 / 点「检查更新」就能拿到新经验');

        return self::SUCCESS;
    }
}
