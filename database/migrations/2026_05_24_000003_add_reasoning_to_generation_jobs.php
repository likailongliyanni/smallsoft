<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('generation_jobs', function (Blueprint $table): void {
            $table->longText('reasoning_content')->nullable()->after('result_script');
        });
    }

    public function down(): void
    {
        Schema::table('generation_jobs', function (Blueprint $table): void {
            $table->dropColumn('reasoning_content');
        });
    }
};
