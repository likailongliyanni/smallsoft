// 数据清洗 UI 纯函数单元测试（无浏览器依赖）：
//   node tests/table-tidy-ui.test.cjs
'use strict';

const assert = require('node:assert/strict');

global.window = {};
require('../public/assets/excel-automation-local.js'); // 提供 window.ExcelLocalKit（createStoredZip 等）
const ui = require('../public/assets/table-tidy-ui.js');

// ───────────────── adaptAiPlan：后端计划 -> 引擎计划 ─────────────────
{
    const plan = ui.adaptAiPlan({
        primary_region_index: 1,
        target_fields: [
            {name: '客户名称', type: 'text', source_headers: ['客户名称', '客户'], cleaners: ['fillDitto', 'collapseSpace']},
            {name: '金额', type: 'number', source_headers: ['金额'], cleaners: []},   // 空 cleaners -> 按类型补默认
            {name: '', type: 'date'},                                                  // 空名 -> 丢弃
            {name: '日期', type: 'bogus-type'},                                        // 非法类型 -> text
        ],
        row_filter: {drop_roles: ['summary', 'note', 'bogus-role'], min_confidence: 0.7},
        fill_ditto: false,
        dedupe: true,
        notes: ['提示1'],
    });
    assert.equal(plan.targetFields.length, 3);
    assert.deepEqual(plan.targetFields[0].cleaners, ['collapseSpace']);          // fill_ditto=false 去掉回填
    assert.deepEqual(plan.targetFields[1].cleaners, ['normalizeAmount']);        // number 默认（含 fillDitto 被关掉）
    assert.equal(plan.targetFields[2].type, 'text');                             // 非法类型回退
    assert.deepEqual(plan.rowFilter.dropRoles, ['summary', 'note']);             // 非法角色被过滤
    assert.equal(plan.rowFilter.minConfidence, 0.7);
    assert.equal(plan.primaryRegionIndex, 1);
    assert.equal(plan.dedupe, true);
    assert.deepEqual(plan.notes, ['提示1']);
}

// 空/坏输入不抛错，给出可执行的空计划骨架。
{
    const plan = ui.adaptAiPlan(null);
    assert.deepEqual(plan.targetFields, []);
    assert.deepEqual(plan.rowFilter.dropRoles, ['empty', 'separator', 'repeated_header', 'summary', 'note']);
    assert.equal(plan.rowFilter.minConfidence, 0.5);
}

// ───────────────── sanitizeSheetName：Excel sheet 名约束 ─────────────────
{
    const used = new Set();
    assert.equal(ui.sanitizeSheetName('订单/明细[1]', 'Sheet1', used), '订单 明细 1');
    assert.equal(ui.sanitizeSheetName('订单/明细[1]', 'Sheet2', used), '订单 明细 1_2'); // 去重
    assert.equal(ui.sanitizeSheetName('', 'Sheet3', used), 'Sheet3');                     // 空名回退
    assert.ok(ui.sanitizeSheetName('很长'.repeat(40), 'S', new Set()).length <= 28);      // 截断
}

// ───────────────── isPlainNumber：13 位条码保持文本 ─────────────────
{
    assert.equal(ui.isPlainNumber('123.45'), true);
    assert.equal(ui.isPlainNumber('6901234567890'), false); // 13 位 -> 文本
    assert.equal(ui.isPlainNumber('007'), false);           // 前导零 -> 文本
}

// ───────────────── buildMultiSheetXlsx：多 sheet 工作簿结构 ─────────────────
(async () => {
    const blob = ui.buildMultiSheetXlsx([
        {name: '干净表', headers: ['名称', '金额'], rows: [['甲', '12.5'], ['乙', '6901234567890']]},
        {name: '异常待确认', headers: ['行号', '原因'], rows: [['3', '置信度低']]},
        {name: '干净表', headers: ['x'], rows: [['1']]}, // 同名 -> 自动改名
    ]);
    const buf = Buffer.from(await blob.arrayBuffer());
    const ascii = buf.toString('latin1');   // stored zip 无压缩，结构可直接检索
    const utf8 = buf.toString('utf8');

    assert.ok(ascii.includes('xl/worksheets/sheet1.xml'));
    assert.ok(ascii.includes('xl/worksheets/sheet2.xml'));
    assert.ok(ascii.includes('xl/worksheets/sheet3.xml'));
    assert.ok(utf8.includes('name="干净表"'));
    assert.ok(utf8.includes('name="干净表_2"'));          // 同名去重
    assert.ok(utf8.includes('name="异常待确认"'));
    assert.ok(utf8.includes('6901234567890'));            // 条码在内容里
    assert.ok(/t="inlineStr"><is><t[^>]*>6901234567890/.test(utf8)); // 且是文本不是数字
    assert.ok(/<c r="B2"><v>12\.5<\/v><\/c>/.test(utf8)); // 普通小数是数字单元格

    console.log('table-tidy-ui.test.cjs: all checks passed');
})();
