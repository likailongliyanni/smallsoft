// 表格整理本地引擎单元测试（无浏览器依赖）：
//   node tests/table-merge-local.test.cjs
'use strict';

const assert = require('node:assert/strict');

global.window = {};
require('../public/assets/table-merge-local.js');
const kit = global.window.TableMergeKit;

function makeSheet(name, headers, dataRows) {
    const rows = new Map();
    const headerMap = new Map();
    headers.forEach((h, i) => headerMap.set(i + 1, h));
    rows.set(1, headerMap);
    dataRows.forEach((r, idx) => {
        const m = new Map();
        r.forEach((v, i) => {
            if (v !== '' && v != null) m.set(i + 1, v);
        });
        rows.set(idx + 2, m);
    });
    return {name, headerRow: 1, maxRow: dataRows.length + 1, maxCol: headers.length, rows};
}

// --- normalizeKeyValue ---
assert.equal(kit.normalizeKeyValue('19983181956.0'), '19983181956');
assert.equal(kit.normalizeKeyValue('  AB12 '), 'ab12');
assert.equal(kit.normalizeKeyValue(null), '');
assert.equal(kit.normalizeKeyValue(19983181956), '19983181956');

// --- letterToColumn ---
assert.equal(kit.letterToColumn('A'), 1);
assert.equal(kit.letterToColumn('T'), 20);
assert.equal(kit.letterToColumn('AB'), 28);
assert.equal(kit.columnLetters(28), 'AB');

// --- detectValueKind ---
assert.equal(kit.detectValueKind(['13880490355', '19983181956', '15531778088']), 'phone');
assert.equal(kit.detectValueKind(['2062455584568901632', '2062440095805341696']), 'longid');
assert.equal(kit.detectValueKind(['JDVG05505355672', 'JDVG05500736999']), 'code');
assert.equal(kit.detectValueKind(['燕子', '任敏', '吴昌裕']), 'text');
assert.equal(kit.detectValueKind(['2026-06-04 16:45:05', '2026-06-04']), 'date');
assert.equal(kit.detectValueKind([]), 'empty');

// --- 测试数据：订单明细表（一单多行） + 快递表 ---
const ordersSheet = makeSheet('订单导出',
    ['线上单号', '收货人姓名', '收货人电话', '商品名称'],
    [
        ['O1', '燕子', '19983181956', '麦片'],
        ['O1', '燕子', '19983181956', '牛奶'],
        ['O2', '苑', '15531778088', '油'],
        ['O3', '无名', '13800000000', '米'],
        ['O4', '曾', '18990019072', '面'],
    ]);
const trackingSheet = makeSheet('Sheet1',
    ['姓名', '电话', '快递单号'],
    [
        ['燕子', '19983181956', 'JD001'],
        ['苑', '15531778088', 'JD002'],
        ['曾', '18990019072', 'JD003'],
        ['吴昌裕', '13877800899', 'JD999'],
    ]);

const fields = [
    {name: '线上单号', sources: [{side: 'left', col: 1}]},
    {name: '人名', sources: [{side: 'right', col: 1}]},
    {name: '电话', sources: [{side: 'left', col: 3}]},
    {name: '快递', sources: [{side: 'right', col: 3}]},
];
const keys = [{leftCol: 3, rightCol: 2}];

// --- inner join + 去重：明细级折叠成订单级 ---
{
    const result = kit.runJoinMerge({
        leftSheet: ordersSheet, rightSheet: trackingSheet,
        keys, joinType: 'inner', fields, dedupe: true,
    });
    assert.deepEqual(result.headers, ['线上单号', '人名', '电话', '快递']);
    assert.deepEqual(result.rows, [
        ['O1', '燕子', '19983181956', 'JD001'],
        ['O2', '苑', '15531778088', 'JD002'],
        ['O4', '曾', '18990019072', 'JD003'],
    ]);
    assert.equal(result.dropped, 1);
    assert.deepEqual(result.stats, {
        leftRows: 5, rightRows: 4, matchedLeft: 4, unmatchedLeft: 1,
        rightKeyCount: 4, usedRightKeys: 3, joinType: 'inner',
    });
}

// --- left join：匹配不上的主表行保留，右侧字段留空 ---
{
    const result = kit.runJoinMerge({
        leftSheet: ordersSheet, rightSheet: trackingSheet,
        keys, joinType: 'left', fields, dedupe: true,
    });
    assert.equal(result.rows.length, 4);
    assert.deepEqual(result.rows[2], ['O3', '', '13800000000', '']);
}

// --- 一对多：右表同键多行时主表行展开 ---
{
    const dupTracking = makeSheet('Sheet1',
        ['姓名', '电话', '快递单号'],
        [
            ['苑', '15531778088', 'JD002A'],
            ['苑', '15531778088', 'JD002B'],
        ]);
    const result = kit.runJoinMerge({
        leftSheet: makeSheet('订单', ['单号', '姓名', '电话'], [['O2', '苑', '15531778088']]),
        rightSheet: dupTracking,
        keys: [{leftCol: 3, rightCol: 2}],
        joinType: 'inner',
        fields: [
            {name: '单号', sources: [{side: 'left', col: 1}]},
            {name: '快递', sources: [{side: 'right', col: 3}]},
        ],
        dedupe: false,
    });
    assert.deepEqual(result.rows, [['O2', 'JD002A'], ['O2', 'JD002B']]);
}

// --- 多键：任一键部分为空的行不参与匹配（不会「空=空」误配） ---
{
    const left = makeSheet('L', ['姓名', '电话'], [['燕子', ''], ['苑', '15531778088']]);
    const right = makeSheet('R', ['姓名', '电话', '快递'], [['燕子', '', 'JDX'], ['苑', '15531778088', 'JD002']]);
    const result = kit.runJoinMerge({
        leftSheet: left, rightSheet: right,
        keys: [{leftCol: 1, rightCol: 1}, {leftCol: 2, rightCol: 2}],
        joinType: 'inner',
        fields: [{name: '快递', sources: [{side: 'right', col: 3}]}],
        dedupe: false,
    });
    assert.deepEqual(result.rows, [['JD002']]);
}

// --- computeJoinStats 与 runJoinMerge 口径一致 ---
{
    const stats = kit.computeJoinStats({leftSheet: ordersSheet, rightSheet: trackingSheet, keys});
    assert.deepEqual(stats, {leftRows: 5, rightRows: 4, matchedLeft: 4, rightKeyCount: 4, usedRightKeys: 3});
}

// --- collectColumnValues + computeKeyOverlaps：电话列被识别为跨表键 ---
{
    const a = kit.collectColumnValues(ordersSheet, 3);
    const b = kit.collectColumnValues(trackingSheet, 2);
    assert.equal(a.nonEmpty, 5);
    assert.equal(a.set.size, 4);
    assert.equal(b.set.size, 4);

    const overlaps = kit.computeKeyOverlaps([
        {ref: {file_index: 0, sheet: '订单导出', column: 'C', header: '收货人电话'}, sheetId: '0#订单导出', set: a.set},
        {ref: {file_index: 1, sheet: 'Sheet1', column: 'B', header: '电话'}, sheetId: '1#Sheet1', set: b.set},
    ]);
    assert.equal(overlaps.length, 1);
    assert.equal(overlaps[0].overlap, 3);
    assert.equal(overlaps[0].coverage, 0.75);
    assert.equal(overlaps[0].a.header, '收货人电话');
}

// --- 同 sheet 内列对不参与交集 ---
{
    const a = kit.collectColumnValues(ordersSheet, 3);
    const overlaps = kit.computeKeyOverlaps([
        {ref: {file_index: 0, sheet: '订单导出', column: 'C', header: '收货人电话'}, sheetId: '0#订单导出', set: a.set},
        {ref: {file_index: 0, sheet: '订单导出', column: 'E', header: '电话副本'}, sheetId: '0#订单导出', set: a.set},
    ]);
    assert.equal(overlaps.length, 0);
}

console.log('table-merge-local.test.cjs: all tests passed');
