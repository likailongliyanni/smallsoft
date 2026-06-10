<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table): void {
            $table->string('nickname', 40)->nullable()->after('name')->index();
            $table->integer('nickname_edit_count')->default(0)->after('nickname');
        });
    }

    public function down(): void
    {
        Schema::table('users', function (Blueprint $table): void {
            $table->dropColumn(['nickname', 'nickname_edit_count']);
        });
    }
};
