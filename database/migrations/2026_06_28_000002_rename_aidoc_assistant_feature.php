<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        DB::table('model_configs')
            ->where('software_code', 'aidoc')
            ->where('purpose', 'assistant_chat')
            ->update(['feature_name' => 'AI 资料秘书']);
    }

    public function down(): void
    {
        DB::table('model_configs')
            ->where('software_code', 'aidoc')
            ->where('purpose', 'assistant_chat')
            ->update(['feature_name' => 'AI 资料员']);
    }
};
