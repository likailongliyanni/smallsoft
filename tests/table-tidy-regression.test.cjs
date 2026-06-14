// 真实乱表回归测试：用用户提供的「测试原始表」验证引擎不丢行、不错位、表头识别正确。
//   node tests/table-tidy-regression.test.cjs
//
// 这个文件曾暴露三个致命缺陷（必须永远保持绿色）：
//   1. 表头识别错：两三格的「导出人/合计金额」标签行冒充表头，产生 列3~列20 垃圾字段；
//   2. 丢数据：续表行（块内表头上方的行）和整块无表头的区域被静默丢弃（共丢 6 条订单）；
//   3. 错位：表头对不上的区域按位置硬塞进第一段的字段，孙小明跑到「序号」列。
'use strict';

const assert = require('node:assert/strict');
const kit = require('../public/assets/table-tidy-local.js');
const {loadXlsxSheets} = require('./load-xlsx.cjs');

const sheet = loadXlsxSheets(`${__dirname}/fixtures/dirty-orders.xlsx`)[0];
assert.ok(sheet, 'fixture 读取失败');

// ───────────────── 区域识别：4 段表，各自表头行正确 ─────────────────
const regions = kit.detectRegions(sheet);
assert.equal(regions.length, 4, `应识别 4 个区域，实际 ${regions.length}`);
assert.deepEqual(regions.map(r => r.headerRow), [4, 13, 19, 24],
    `表头行应为 4/13/19/24，实际 ${regions.map(r => r.headerRow)}`);

// 区域1 的续表行（块2 表头上方的 8/9/10 + 小计 11 + 分隔 12）必须归回区域1，不能丢。
assert.ok([8, 9, 10].every(r => regions[0].extraRows.includes(r)),
    `第 8/9/10 行（王五/赵六订单）应并入区域1 续表，实际 extraRows=${regions[0].extraRows}`);
// 标题区 1~3 行挂在区域1 上，等待按角色记录删除。
assert.ok([1, 2, 3].every(r => regions[0].leadingRows.includes(r)),
    `标题区 1~3 应记录在 leadingRows，实际 ${regions[0].leadingRows}`);

// ───────────────── 端到端整理 ─────────────────
const plan = kit.buildLocalPlan(sheet);
const res = kit.tidySheet(sheet, plan);

// 1. 不产生「列N」垃圾表头，第一个字段是真表头。
assert.equal(res.headers[0], '序号', `首字段应为 序号，实际 ${res.headers[0]}`);
assert.ok(!res.headers.includes('列3'), '不应出现「列3」这类垃圾字段');

// 2. 一行都不能丢：原表 15 条订单全部在干净表或异常表里。
const allRows = [...res.rows, ...res.exceptions.map(e => e.values)];
const flat = allRows.map(r => r.join(''));
const orderIds = [
    'JD-20260601-0001', 'JD-20260601-0002', 'JD-20260601-0003', 'JD-20260601-0004', 'JD-20260601-0005',
    'TB-77880001', 'TB-77880002', 'TB-77880003',
    'PDD-660001', 'PDD-660002', 'PDD-660003',
    'JD-20260604-0088', 'JD-20260604-0089', 'JD-20260604-0090', 'JD-20260604-0091',
];
const missing = orderIds.filter(id => !flat.some(line => line.includes(id)));
assert.deepEqual(missing, [], `丢失订单：${missing.join(', ')}`);
assert.equal(res.stats.kept + res.stats.exceptions, 15,
    `15 条订单应全部保留（干净+异常），实际 kept=${res.stats.kept} exceptions=${res.stats.exceptions}`);

// 3. 不错位：每段的数据落在它自己的表头字段下。
const colOf = name => res.headers.indexOf(name);
const rowWith = text => res.rows.find(r => r.some(v => String(v).includes(text)));

assert.equal(rowWith('张三')[colOf('收货人/姓名')], '张三', '张三应在「收货人/姓名」列');
assert.equal(rowWith('孙小明')[colOf('客户')], '孙小明', '孙小明应在「客户」列（手工补录段）');
assert.equal(rowWith('刘强')[colOf('买家')], '刘强', '刘强应在「买家」列（平台导出段）');
assert.equal(rowWith('黄蓉')[colOf('姓名')], '黄蓉', '黄蓉应在「姓名」列（重复表头段）');
// 孙小明绝不能出现在「序号」列（曾经的错位事故）。
assert.notEqual(rowWith('孙小明')[colOf('序号')], '孙小明', '孙小明不能错位到「序号」列');

// 4. 「同上」回填：赵六第二单的地址回填上一行。
const baoWenBei = rowWith('苏泊尔保温杯');
assert.equal(baoWenBei[colOf('收货地址（有的写一起）')], '陕西省西安市未央区凤城八路99号',
    '「同上」地址应回填上一行的真实地址');

// 5. 噪声行全部有记录：标题、小计、合计、页脚、微信文本、END。
const droppedRows = new Set(res.dropped.map(d => d.row));
[1, 11, 12, 18, 30, 31, 32, 33, 34].forEach(row => {
    assert.ok(droppedRows.has(row), `第 ${row} 行（噪声）应出现在被删记录里，实际 ${[...droppedRows]}`);
});
const roleOf = row => res.dropped.find(d => d.row === row)?.role;
assert.equal(roleOf(11), 'summary', '第 11 行小计应标为 summary');
assert.equal(roleOf(18), 'summary', '第 18 行合计金额应标为 summary');

// 6. 日期 / 金额标准化抽查。
assert.equal(rowWith('张三')[colOf('单价')], '48.00', '￥48.00 应标准化为 48.00');
assert.equal(rowWith('张三')[colOf('下单时间')], '2026-06-01 09:12:00', '下单时间应标准化');

console.log(`table-tidy-regression.test.cjs: all checks passed (kept=${res.stats.kept}, exceptions=${res.stats.exceptions}, dropped=${res.dropped.length})`);
