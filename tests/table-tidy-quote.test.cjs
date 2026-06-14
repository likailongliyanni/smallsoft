// 真实乱表回归 #2：商品报价表（.NET OpenXML 生成，带 x: 命名空间前缀 + 重复表头续表）。
//   node tests/table-tidy-quote.test.cjs
//
// 曾暴露的缺陷（必须永远绿）：第二段以「重复表头」开头的续表块，重复表头被跳过后，
// 紧跟的第一条数据行（陕西优品办公/A4复印纸…）被误当成多行表头，吃掉整行数据
// 并产生「供应商-陕西优品办公」这类垃圾列。
'use strict';

const assert = require('node:assert/strict');
const kit = require('../public/assets/table-tidy-local.js');
const {loadXlsxSheets} = require('./load-xlsx.cjs');

const sheet = loadXlsxSheets(`${__dirname}/fixtures/quote.xlsx`)[0];
assert.ok(sheet && sheet.maxRow >= 16, 'fixture sheet1 读取失败（命名空间前缀解析）');

const res = kit.tidySheet(sheet, kit.buildLocalPlan(sheet));

// 两段同表头合并成 1 个区域、9 个干净字段，没有「供应商-…」垃圾列。
assert.deepEqual(res.headers, ['供应商', '商品名称', '规格型号', '单位', '单价', '是否含税', '起订量', '交期', '备注'],
    `字段应为原表 9 列，实际 ${res.headers.join('/')}`);
assert.ok(!res.headers.some(h => h.includes('-')), '不应出现多行表头误拼的「列-值」垃圾字段');

// 7 条商品一条都不能少（A4复印纸曾被吃进表头）。
assert.equal(res.rows.length, 7, `应保留 7 条商品，实际 ${res.rows.length}`);
const col = name => res.headers.indexOf(name);
const products = res.rows.map(r => r[col('商品名称')]);
['抽纸', '卷纸', '洗手液', 'A4复印纸', '中性笔', '保温杯', '雨伞'].forEach(p => {
    assert.ok(products.includes(p), `商品「${p}」丢失，实际 ${products.join('/')}`);
});

// 「同上」正确回填供应商（跨段也不串）。
const supOf = product => res.rows.find(r => r[col('商品名称')] === product)[col('供应商')];
assert.equal(supOf('卷纸'), '西安晨光商贸', '卷纸供应商应回填西安晨光商贸');
assert.equal(supOf('A4复印纸'), '陕西优品办公', 'A4复印纸供应商应为陕西优品办公');
assert.equal(supOf('中性笔'), '陕西优品办公', '中性笔「同上」应回填陕西优品办公');
assert.equal(supOf('雨伞'), '西安礼品工厂', '雨伞「同上」应回填西安礼品工厂');

// 单价标准化：去掉 ¥/￥/元，保留数值（含小数）。
const priceOf = product => res.rows.find(r => r[col('商品名称')] === product)[col('单价')];
assert.equal(priceOf('抽纸'), '185', '¥185 → 185');
assert.equal(priceOf('卷纸'), '168', '168元 → 168');
assert.equal(priceOf('A4复印纸'), '178.50', '￥178.50 → 178.50');
assert.equal(priceOf('雨伞'), '22.8', '22.8元 → 22.8');

// 噪声行全部删除并标对角色。
const dropRole = row => res.dropped.find(d => d.row === row)?.role;
assert.equal(dropRole(1), 'note', 'r1 标题');
assert.equal(dropRole(2), 'note', 'r2 说明');
assert.equal(dropRole(8), 'summary', 'r8 小计');
assert.equal(dropRole(10), 'repeated_header', 'r10 重复表头');
assert.equal(dropRole(15), 'summary', 'r15 合计');
assert.equal(dropRole(16), 'note', 'r16 END');

assert.equal(res.exceptions.length, 0, `不应有异常行，实际 ${res.exceptions.length}`);
assert.equal(res.stats.regions, 1, `两段同表头应合并为 1 个区域，实际 ${res.stats.regions}`);

console.log(`table-tidy-quote.test.cjs: all checks passed (rows=${res.rows.length}, dropped=${res.dropped.length})`);
