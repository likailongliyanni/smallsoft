// 合并单元格回归：纵向合并的列（仓库/日期合并若干行）必须把左上角的值
// 展开到下方空格，否则下方行该列丢值。横向合并（标题）不展开。
//   node tests/table-tidy-merge-cells.test.cjs
'use strict';

const assert = require('node:assert/strict');
const kit = require('../public/assets/table-tidy-local.js');
const {loadXlsxSheets} = require('./load-xlsx.cjs');

// ── 纯函数 expandMerges：直接验证展开规则 ──
{
    const rows = new Map([
        [1, new Map([[1, '甲仓'], [2, '货A']])],
        [2, new Map([[2, '货B']])],            // 仓库列空（合并下方）
        [3, new Map([[2, '货C']])],
    ]);
    const sheet = {name: 't', headerRow: 1, maxRow: 3, maxCol: 2, rows,
        merges: [{top: 1, bottom: 3, left: 1, right: 1}]};   // A1:A3 纵向合并
    const out = kit.expandMerges(sheet);
    assert.equal(out.rows.get(2).get(1), '甲仓', '纵向合并下方行应回填左上值');
    assert.equal(out.rows.get(3).get(1), '甲仓');
    assert.equal(sheet.rows.get(2).get(1), undefined, '原 sheet 不应被改动（返回副本）');
}
{
    // 纯横向合并（标题）不展开，避免把标题铺满整行。
    const rows = new Map([[1, new Map([[1, '总表']])]]);
    const sheet = {name: 't', headerRow: 1, maxRow: 1, maxCol: 3, rows,
        merges: [{top: 1, bottom: 1, left: 1, right: 3}]};
    const out = kit.expandMerges(sheet);
    assert.equal(out.rows.get(1).get(2), undefined, '横向合并不应展开');
}

// ── 端到端：真实合并单元格 xlsx（openpyxl 生成，纵向合并仓库列和日期列）──
const sheet = loadXlsxSheets(`${__dirname}/fixtures/merged-stock.xlsx`)[0];
assert.ok(sheet.merges && sheet.merges.length >= 4, `应读到合并区，实际 ${JSON.stringify(sheet.merges)}`);

const res = kit.tidySheet(sheet, kit.buildLocalPlan(sheet));
const col = n => res.headers.indexOf(n);

assert.deepEqual(res.headers, ['仓库', '商品名称', '规格', '数量', '盘点日期']);
assert.equal(res.rows.length, 5, `应保留 5 条库存，实际 ${res.rows.length}`);

// 合并单元格展开：一号仓 3 行、二号仓 2 行的仓库列都被填满。
const warehouses = res.rows.map(r => r[col('仓库')]);
assert.deepEqual(warehouses, ['西安一号仓', '西安一号仓', '西安一号仓', '西安二号仓', '西安二号仓'],
    `仓库列应被合并展开填满，实际 ${warehouses.join('/')}`);

// 日期列纵向合并也展开。
const dates = res.rows.map(r => r[col('盘点日期')]);
assert.deepEqual(dates, ['2026-06-01', '2026-06-01', '2026-06-01', '2026-06-02', '2026-06-02'],
    `日期列应展开并标准化，实际 ${dates.join('/')}`);

// 商品一条不少。
const products = res.rows.map(r => r[col('商品名称')]);
['螺丝M3', '螺母M3', '垫片', '电线1.5', '电线2.5'].forEach(p =>
    assert.ok(products.includes(p), `商品「${p}」丢失`));

// 标题（横向合并）和合计行被删，不混进数据。
assert.ok(res.dropped.some(d => d.role === 'summary'), '合计行应删除');
assert.ok(!warehouses.includes('2026年6月库存盘点表'), '标题不应混入数据');

console.log(`table-tidy-merge-cells.test.cjs: all checks passed (rows=${res.rows.length})`);
