<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('model_configs', function (Blueprint $table): void {
            $table->string('purpose', 30)->default('script')->after('id')->index();
        });

        DB::table('model_configs')
            ->whereNull('purpose')
            ->orWhere('purpose', '')
            ->update(['purpose' => 'script']);
    }

    public function down(): void
    {
        Schema::table('model_configs', function (Blueprint $table): void {
            $table->dropColumn('purpose');
        });
    }
};
