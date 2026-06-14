// 通用脏 Excel 结构化引擎单元测试（无浏览器依赖）：
//   node tests/table-tidy-local.test.cjs
'use strict';

const assert = require('node:assert/strict');
const kit = require('../public/assets/table-tidy-local.js');

// 用「行号 -> (列号 -> 值)」的稀疏结构构造一个 sheet，和 ExcelLocalKit 解析结果同形。
function makeSheet(name, grid) {
    const rows = new Map();
    let maxCol = 0;
    grid.forEach((cells, idx) => {
        const m = new Map();
        cells.forEach((v, i) => {
            if (v !== '' && v != null) { m.set(i + 1, String(v)); maxCol = Math.max(maxCol, i + 1); }
        });
        rows.set(idx + 1, m);
    });
    return { name, headerRow: 1, maxRow: grid.length, maxCol, rows };
}

let passed = 0;
function check(label, fn) {
    fn();
    passed++;
}

// ───────────────── 1. 类型探测（通用数据形态，不含业务字段） ─────────────────
check('detectCellType', () => {
    assert.equal(kit.detectCellType('13800138000'), 'phone');
    assert.equal(kit.detectCellType('110101199003071234'), 'idcard');
    assert.equal(kit.detectCellType('a@b.com'), 'email');
    assert.equal(kit.detectCellType('2026-06-04'), 'date');
    assert.equal(kit.detectCellType('2026/6/4 16:45'), 'datetime');
    assert.equal(kit.detectCellType('￥1,234.50'), 'amount');
    assert.equal(kit.detectCellType('12.5%'), 'percent');
    assert.equal(kit.detectCellType('JDVG05505355672'), 'code');
    assert.equal(kit.detectCellType('2062455584568901632'), 'longid');
    assert.equal(kit.detectCellType('燕子'), 'text');
    assert.equal(kit.detectCellType(''), 'empty');
});

// ───────────────── 2. 清洗模块（按语义类型，可复用） ─────────────────
check('cleaners.normalizeDate', () => {
    assert.equal(kit.cleaners.normalizeDate('2026年6月4日'), '2026-06-04');
    assert.equal(kit.cleaners.normalizeDate('2026/6/4'), '2026-06-04');
    assert.equal(kit.cleaners.normalizeDate('2026.6.4 16:45:05'), '2026-06-04 16:45:05');
    assert.equal(kit.cleaners.normalizeDate('不是日期'), '不是日期');
});
check('cleaners.normalizeAmount', () => {
    assert.equal(kit.cleaners.normalizeAmount('￥1,234.50'), '1234.50');
    assert.equal(kit.cleaners.normalizeAmount('1,234元'), '1234');
    assert.equal(kit.cleaners.normalizeAmount('-12.0'), '-12.0');
});
check('cleaners.fillDitto', () => {
    assert.equal(kit.cleaners.fillDitto('同上', '北京'), '北京');
    assert.equal(kit.cleaners.fillDitto('〃', '上海'), '上海');
    assert.equal(kit.cleaners.fillDitto('广州', '上海'), '广州');
});
check('cleaners.splitUnit', () => {
    assert.deepEqual(kit.cleaners.splitUnit('500g'), { value: '500', unit: 'g' });
    assert.deepEqual(kit.cleaners.splitUnit('3.5 kg'), { value: '3.5', unit: 'kg' });
    assert.deepEqual(kit.cleaners.splitUnit('12个'), { value: '12', unit: '个' });
});
check('cleaners.cnNumeralToArabic', () => {
    assert.equal(kit.cleaners.cnNumeralToArabic('十二'), '12');
    assert.equal(kit.cleaners.cnNumeralToArabic('三千五百'), '3500');
    assert.equal(kit.cleaners.cnNumeralToArabic('一万两千'), '12000');
    assert.equal(kit.cleaners.cnNumeralToArabic('abc'), 'abc');
});

// ───────────────── 3. 多段表头 / 区域识别（表头不在第一行 + 多区域） ─────────────────
check('detectRegions: 标题行 + 两个区域 + 表头不在第一行', () => {
    const sheet = makeSheet('混合', [
        ['2026年6月销售汇总表'],                 // 1 标题
        ['客户名称', '电话', '金额'],            // 2 区域A表头
        ['张三', '13800138000', '￥1,200.00'],   // 3
        ['李四', '13900139000', '￥3,400.50'],   // 4
        [],                                      // 5 空行分隔
        ['供应商', '联系方式', '报价'],          // 6 区域B表头（字段不同）
        ['甲公司', '13700137000', '99.9'],       // 7
        ['乙公司', '13600136000', '88.8'],       // 8
    ]);
    const regions = kit.detectRegions(sheet);
    assert.equal(regions.length, 2);
    // 区域A 表头被正确识别在第 2 行（而非标题第 1 行）。
    assert.deepEqual(regions[0].headerRows, [2]);
    assert.equal(regions[0].dataTop, 3);
    assert.equal(regions[0].dataRowCount, 2);
    assert.deepEqual(regions[0].columns.map(c => c.header), ['客户名称', '电话', '金额']);
    // 区域B 独立表头。
    assert.deepEqual(regions[1].headerRows, [6]);
    assert.deepEqual(regions[1].columns.map(c => c.header), ['供应商', '联系方式', '报价']);
});

check('detectRegions: 多行表头纵向拼接', () => {
    const sheet = makeSheet('多行表头', [
        ['基本信息', '基本信息', '联系'],        // 1 上层表头（合并单元格风格）
        ['姓名', '工号', '电话'],                // 2 下层表头
        ['张三', 'A001', '13800138000'],         // 3
        ['李四', 'A002', '13900139000'],         // 4
    ]);
    const regions = kit.detectRegions(sheet);
    assert.equal(regions.length, 1);
    assert.deepEqual(regions[0].headerRows, [1, 2]);
    assert.deepEqual(regions[0].columns.map(c => c.header), ['基本信息-姓名', '基本信息-工号', '联系-电话']);
});

// ───────────────── 4. 行角色分类（合计 / 重复表头 / 说明 / 分隔线） ─────────────────
check('classifyRow', () => {
    const headerSig = kit.headerSignature(['客户', '电话', '金额']);
    const ctx = { colCount: 3, headerSignature: headerSig };
    const row = arr => { const m = new Map(); arr.forEach((v, i) => { if (v !== '') m.set(i + 1, v); }); return m; };

    assert.equal(kit.classifyRow(row(['', '', '']), ctx).role, 'empty');
    assert.equal(kit.classifyRow(row(['---', '', '']), ctx).role, 'separator');
    assert.equal(kit.classifyRow(row(['客户', '电话', '金额']), ctx).role, 'repeated_header');
    assert.equal(kit.classifyRow(row(['合计', '', '4600.50']), ctx).role, 'summary');
    assert.equal(kit.classifyRow(row(['制表人：王五', '', '']), ctx).role, 'note');
    assert.equal(kit.classifyRow(row(['张三', '13800138000', '1200']), ctx).role, 'data');
});

// ───────────────── 5. 非结构化文本解析（微信粘贴整段） ─────────────────
check('extractEntities', () => {
    const r = kit.extractEntities('张三 13800138000 北京市朝阳区建国路1号院2栋301室 球鞋 ¥299 备注收货后联系');
    assert.equal(r.fields.phone, '13800138000');
    assert.equal(r.fields.name, '张三');
    assert.equal(r.fields.amount, '299');
    assert.ok(r.fields.address.includes('朝阳区'));
    assert.ok(r.confidence > 0);
});

// ───────────────── 6. 端到端：脏表 -> 干净表 + 异常 + 被删行 + 置信度 ─────────────────
check('tidySheet: 端到端整理', () => {
    const sheet = makeSheet('脏订单', [
        ['客户订单明细'],                                   // 1 标题（被识别为非表头）
        ['客户名称', '联系电话', '下单日期', '金额'],        // 2 表头
        ['张三', '13800138000', '2026年6月4日', '￥1,200.00'], // 3 正常
        ['李四', '13900139000', '2026/6/5', '3,400.5'],      // 4 正常
        ['同上', '13900139000', '2026/6/6', '500'],          // 5 同上回填客户
        ['', '', '', ''],                                    // 6 空行
        ['合计', '', '', '5100.5'],                          // 7 合计行 -> 删除
        ['制表人：王五  导出时间 2026-06-12', '', '', ''],   // 8 页脚 -> 删除
    ]);

    const res = kit.tidySheet(sheet);

    // 字段名由内容推断（取表头），不写死。
    assert.deepEqual(res.headers, ['客户名称', '联系电话', '下单日期', '金额']);

    // 3 行有效数据，日期 / 金额被标准化，「同上」被回填。
    assert.equal(res.rows.length, 3);
    assert.deepEqual(res.rows[0], ['张三', '13800138000', '2026-06-04', '1200.00']);
    assert.deepEqual(res.rows[1], ['李四', '13900139000', '2026-06-05', '3400.5']);
    assert.equal(res.rows[2][0], '李四'); // 「同上」回填为上一行客户

    // 合计行、页脚行进入被删记录，并带原因。
    const roles = res.dropped.map(d => d.role);
    assert.ok(roles.includes('summary'));
    assert.ok(roles.includes('note'));

    // 输出结构齐全：日志 / 字段映射 / 统计。
    assert.ok(res.log.length >= 1);
    assert.equal(res.fieldMap.length, 4);
    assert.equal(res.stats.kept, 3);
});

check('tidySheet: 低置信度行进入异常表', () => {
    const sheet = makeSheet('错位', [
        ['姓名', '电话'],
        ['张三', '13800138000'],          // 正常
        ['13700137000', '不是电话也不是姓名规律'], // 电话列放了文本 -> 该列打分低
    ]);
    // 强制电话字段期望 phone 类型，文本值会被判低置信。
    const plan = {
        regions: kit.detectRegions(sheet),
        targetFields: [
            { name: '姓名', type: 'text', sourceHeaders: ['姓名'], cleaners: ['collapseSpace'] },
            { name: '电话', type: 'phone', sourceHeaders: ['电话'], cleaners: ['collapseSpace'] },
        ],
        rowFilter: { dropRoles: ['empty', 'separator', 'repeated_header', 'summary', 'note'], minConfidence: 0.7 },
    };
    const res = kit.tidySheet(sheet, plan);
    assert.equal(res.rows.length, 1);
    assert.equal(res.exceptions.length, 1);
    assert.ok(res.exceptions[0]._confidence < 0.7);
    assert.ok(res.exceptions[0]._reason.length > 0);
});

// ───────────────── 7. 摘要构造（隐私：只上报统计 + 少量样例） ─────────────────
check('buildTidySummary', () => {
    const sheet = makeSheet('s', [
        ['名称', '电话'],
        ['甲', '13800138000'],
        ['乙', '13900139000'],
    ]);
    const summary = kit.buildTidySummary(sheet);
    assert.equal(summary.regions.length, 1);
    const cols = summary.regions[0].columns;
    assert.equal(cols[0].header, '名称');
    assert.equal(cols[1].value_kind, 'id'); // phone 归入 id 家族
    assert.ok(cols[1].samples.length <= 5);
});

console.log(`table-tidy-local.test.cjs: all ${passed} checks passed`);
