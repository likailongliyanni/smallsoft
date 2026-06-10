<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('generation_jobs', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->string('flow_name', 120);
            $table->string('status', 30)->default('pending')->index();
            $table->unsignedInteger('step_count')->default(0);
            $table->json('request_payload')->nullable();
            $table->longText('result_script')->nullable();
            $table->text('error_message')->nullable();
            $table->string('used_provider', 50)->nullable();
            $table->string('used_model', 120)->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('generation_jobs');
    }
};
