<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->string('software_code', 20)->nullable()->index()->after('username');
        });

        // 历史：截图/图片软件的设备用户归到 pic，并把编号加上 -pic 后缀，
        // 与新逻辑（username = 编号-软件代码）保持一致，使现有客户端无需更新也能对上。
        $rows = DB::table('users')
            ->where('name', 'like', '智能截图软件%')
            ->whereNull('software_code')
            ->get(['id', 'username']);

        foreach ($rows as $row) {
            $username = (string) $row->username;
            if (! str_ends_with($username, '-pic')) {
                $username .= '-pic';
            }
            DB::table('users')->where('id', $row->id)->update([
                'software_code' => 'pic',
                'username' => $username,
            ]);
        }
    }

    public function down(): void
    {
        // 还原 username 后缀
        $rows = DB::table('users')->where('software_code', 'pic')
            ->where('username', 'like', '%-pic')->get(['id', 'username']);
        foreach ($rows as $row) {
            DB::table('users')->where('id', $row->id)
                ->update(['username' => substr((string) $row->username, 0, -4)]);
        }
        Schema::table('users', function (Blueprint $table) {
            $table->dropColumn('software_code');
        });
    }
};
