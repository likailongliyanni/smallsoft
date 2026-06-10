<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('ai_patterns', function (Blueprint $table): void {
            $table->string('category', 30)->default('browser')->after('code')->index();
        });
    }

    public function down(): void
    {
        Schema::table('ai_patterns', function (Blueprint $table): void {
            $table->dropColumn('category');
        });
    }
};
