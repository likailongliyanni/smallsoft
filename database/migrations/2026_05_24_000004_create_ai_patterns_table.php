<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * ai_patterns 表 - AI 经验/学习包
 *
 * 设计目的：把"如何处理特定场景"作为知识独立存在，
 * 不写死在代码里。未来遇到新场景（如日期选择器、富文本编辑器、
 * 滑块验证、文件下载...）只需新增一条记录即可，不用改代码。
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('ai_patterns', function (Blueprint $table): void {
            $table->id();
            $table->string('code', 60)->unique();   // 'select-excel-mapping'
            $table->string('title', 120);            // '下拉菜单 + Excel 数据映射'
            $table->text('content');                 // 完整的提示词文本
            $table->boolean('enabled')->default(true)->index();
            $table->integer('priority')->default(50);  // 数字小的先拼接
            $table->text('changelog')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('ai_patterns');
    }
};
