<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('model_configs', function (Blueprint $table): void {
            $table->id();
            $table->string('provider', 50)->default('openai-compatible');
            $table->string('base_url', 255)->nullable();
            $table->string('model', 120)->nullable();
            $table->text('api_key_encrypted')->nullable();
            $table->longText('system_prompt')->nullable();
            $table->boolean('enabled')->default(false)->index();
            $table->timestamp('last_tested_at')->nullable();
            $table->string('last_test_status', 30)->nullable();
            $table->text('last_test_message')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('model_configs');
    }
};
