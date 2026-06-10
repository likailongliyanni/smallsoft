<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('announcements', function (Blueprint $table): void {
            $table->id();
            $table->string('content', 500);     // 单条公告内容
            $table->boolean('enabled')->default(true)->index();
            $table->integer('priority')->default(50);  // 数字小的先显示
            $table->timestamp('expires_at')->nullable();  // 可选过期时间
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('announcements');
    }
};
