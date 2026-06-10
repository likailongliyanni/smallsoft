<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('model_configs', function (Blueprint $table): void {
            $table->decimal('temperature', 3, 2)->default(0.20)->after('enabled');
            $table->unsignedInteger('max_tokens')->nullable()->after('temperature');
            $table->boolean('thinking_enabled')->default(true)->after('max_tokens');
            $table->string('reasoning_effort', 20)->default('high')->after('thinking_enabled');
            $table->unsignedInteger('request_timeout')->default(180)->after('reasoning_effort');
            $table->json('last_usage')->nullable()->after('last_test_message');
        });

        Schema::table('generation_jobs', function (Blueprint $table): void {
            $table->json('warnings')->nullable()->after('error_message');
            $table->json('usage')->nullable()->after('used_model');
            $table->unsignedInteger('duration_ms')->nullable()->after('usage');
        });
    }

    public function down(): void
    {
        Schema::table('generation_jobs', function (Blueprint $table): void {
            $table->dropColumn(['warnings', 'usage', 'duration_ms']);
        });

        Schema::table('model_configs', function (Blueprint $table): void {
            $table->dropColumn([
                'temperature',
                'max_tokens',
                'thinking_enabled',
                'reasoning_effort',
                'request_timeout',
                'last_usage',
            ]);
        });
    }
};
