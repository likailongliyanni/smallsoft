// 智能统计引擎无头单测：node tests/table-pivot-local.test.cjs
const assert = require('assert');
const kit = require('../public/assets/table-pivot-local.js');

let pass = 0;
function ok(name, cond) {
    assert.ok(cond, name);
    pass++;
    console.log('  ✓ ' + name);
}

// ---- detectKind ----
ok('日期列识别', kit.detectKind(['2023-05-01', '2024-01-01', '2024/3/3']) === 'date');
ok('数字列识别', kit.detectKind(['100', '50.5', '200']) === 'number');
ok('长数字按编号', kit.detectKind(['13800138000', '13900139000']) === 'id');
ok('文本列识别', kit.detectKind(['风扇', '空调', '电视']) === 'text');

// ---- 时间分桶 ----
ok('按年', kit.bucketValue('2024-03-01', 'year') === '2024');
ok('按季度', kit.bucketValue('2024-03-01', 'quarter') === '2024-Q1');
ok('按月', kit.bucketValue('2024-06-09', 'month') === '2024-06');
ok('中文日期按年', kit.bucketValue('2023年7月1日', 'year') === '2023');

// ---- runPivot：分组聚合 + 时间粒度 + 去重计数 ----
const headers = ['客户', '下单日期', '品类', '金额', '订单号'];
const rows = [
    {客户: '张三', 下单日期: '2023-05-01', 品类: '风扇', 金额: '100', 订单号: 'A1'},
    {客户: '张三', 下单日期: '2023-07-01', 品类: '风扇', 金额: '50', 订单号: 'A2'},
    {客户: '张三', 下单日期: '2024-01-01', 品类: '空调', 金额: '300', 订单号: 'A3'},
    {客户: '李四', 下单日期: '2024-03-01', 品类: '风扇', 金额: '200', 订单号: 'A4'},
    {客户: '李四', 下单日期: '2024-06-01', 品类: '风扇', 金额: '200', 订单号: 'A4'},
];
const plan = {
    dimensions: [
        {column: '客户', label: '客户', time_bucket: null},
        {column: '下单日期', label: '年份', time_bucket: 'year'},
    ],
    measures: [
        {column: '金额', agg: 'sum', label: '销售额'},
        {column: '订单号', agg: 'count_distinct', label: '订单数'},
    ],
    filters: [], pivot_column: null, sort: null, top_n: null,
};
const r = kit.runPivot(headers, rows, plan);
ok('长表表头正确', JSON.stringify(r.long.headers) === JSON.stringify(['客户', '年份', '销售额', '订单数']));
ok('分成 3 组', r.long.rows.length === 3);
const find = (cust, yr) => r.long.rows.find(row => row[0] === cust && row[1] === yr);
ok('张三/2023 销售额=150', find('张三', '2023')[2] === 150);
ok('张三/2023 订单数=2', find('张三', '2023')[3] === 2);
ok('张三/2024 销售额=300', find('张三', '2024')[2] === 300);
ok('李四/2024 销售额=400(同单不重复计金额是相加)', find('李四', '2024')[2] === 400);
ok('李四/2024 订单数=1(A4去重)', find('李四', '2024')[3] === 1);

// ---- 排序 + top_n ----
const r2 = kit.runPivot(headers, rows, {...plan, sort: {by: '销售额', dir: 'desc'}, top_n: 2});
ok('排序后取前2', r2.long.rows.length === 2);
ok('降序第一是最大销售额', r2.long.rows[0][2] >= r2.long.rows[1][2]);

// ---- 交叉表（年份铺成列）----
const r3 = kit.runPivot(headers, rows, {
    dimensions: plan.dimensions,
    measures: [{column: '金额', agg: 'sum', label: '销售额'}],
    filters: [], pivot_column: '年份', sort: null, top_n: null,
});
ok('交叉表存在', !!r3.wide);
ok('交叉表表头=客户+年份列', JSON.stringify(r3.wide.headers) === JSON.stringify(['客户', '2023', '2024']));
const wz = r3.wide.rows.find(row => row[0] === '张三');
const wl = r3.wide.rows.find(row => row[0] === '李四');
ok('张三 2023=150', wz[1] === 150);
ok('张三 2024=300', wz[2] === 300);
ok('李四 2023=空', wl[1] === '');
ok('李四 2024=400', wl[2] === 400);

// ---- 筛选 ----
const r4 = kit.runPivot(headers, rows, {
    dimensions: [{column: '客户', label: '客户', time_bucket: null}],
    measures: [{column: '金额', agg: 'sum', label: '销售额'}],
    filters: [{column: '品类', op: 'in', values: ['空调']}], pivot_column: null, sort: null, top_n: null,
});
ok('筛选只剩空调那条', r4.long.rows.length === 1 && r4.long.rows[0][0] === '张三' && r4.long.rows[0][1] === 300);

// ---- 本地兜底计划 ----
const summary = kit.buildPivotSummary(headers, rows, 'Sheet1');
const local = kit.buildLocalPlan(summary);
ok('兜底有维度', local.dimensions.length >= 1);
ok('兜底有度量', local.measures.length >= 1);

console.log(`\n全部通过：${pass} 项`);
