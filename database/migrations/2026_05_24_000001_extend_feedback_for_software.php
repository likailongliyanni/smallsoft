<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('feedback_logs', function (Blueprint $table): void {
            $table->string('flow_name', 120)->nullable()->after('category');
            $table->string('source', 30)->default('manual')->after('flow_name')->index(); // manual / auto_error
            $table->text('error_message')->nullable()->after('content');
            $table->string('template_path', 255)->nullable()->after('error_message');
            $table->json('meta')->nullable()->after('template_path');
        });
    }

    public function down(): void
    {
        Schema::table('feedback_logs', function (Blueprint $table): void {
            $table->dropColumn(['flow_name', 'source', 'error_message', 'template_path', 'meta']);
        });
    }
};
