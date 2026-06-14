// 测试用 xlsx 读取器：把 xlsx 解析成引擎需要的 sheet 结构
// {name, headerRow: 1, maxRow, maxCol, rows: Map<row, Map<col, string>>}
// 属性顺序无关的健壮解析（Excel/WPS 写出的 <c> 属性顺序不固定）。
'use strict';
const fs = require('node:fs');
const zlib = require('node:zlib');

function readZip(buf) {
    const entries = new Map();
    let i = buf.length - 22;
    while (i >= 0 && buf.readUInt32LE(i) !== 0x06054b50) i--;
    if (i < 0) throw new Error('not a zip');
    let offset = buf.readUInt32LE(i + 16);
    const total = buf.readUInt16LE(i + 10);
    for (let n = 0; n < total; n++) {
        const method = buf.readUInt16LE(offset + 10);
        const csize = buf.readUInt32LE(offset + 20);
        const nameLen = buf.readUInt16LE(offset + 28);
        const extraLen = buf.readUInt16LE(offset + 30);
        const commentLen = buf.readUInt16LE(offset + 32);
        const localOff = buf.readUInt32LE(offset + 42);
        const name = buf.slice(offset + 46, offset + 46 + nameLen).toString('utf8');
        entries.set(name, {method, csize, localOff});
        offset += 46 + nameLen + extraLen + commentLen;
    }
    return name => {
        const e = entries.get(name);
        if (!e) return null;
        const nameLen2 = buf.readUInt16LE(e.localOff + 26);
        const extraLen2 = buf.readUInt16LE(e.localOff + 28);
        const start = e.localOff + 30 + nameLen2 + extraLen2;
        const data = buf.slice(start, start + e.csize);
        return e.method === 0 ? data : zlib.inflateRawSync(data);
    };
}

function decode(s) {
    return String(s)
        .replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&quot;', '"')
        .replaceAll('&apos;', "'").replaceAll('&#10;', '\n').replaceAll('&amp;', '&');
}

function attr(attrs, name) {
    const m = attrs.match(new RegExp(`(?:^|\\s)${name}="([^"]*)"`));
    return m ? m[1] : '';
}

function colNum(ref) {
    const m = String(ref).match(/^([A-Z]+)/);
    if (!m) return 0;
    return m[1].split('').reduce((n, c) => n * 26 + c.charCodeAt(0) - 64, 0);
}

function loadXlsxSheets(filePath) {
    const buf = fs.readFileSync(filePath);
    const get = readZip(buf);

    // 部分库（.NET OpenXML SDK 等）会给标签加命名空间前缀（<x:sheet>/<x:row>）。
    // 正则一律允许可选的 \w+: 前缀，和浏览器端 getElementsByTagNameNS('*') 同效。
    const shared = [];
    const ss = get('xl/sharedStrings.xml');
    if (ss) {
        ss.toString('utf8').split(/<(?:\w+:)?si[ >]/).slice(1).forEach(si => {
            const ts = [...si.matchAll(/<(?:\w+:)?t[^>]*>([\s\S]*?)<\/(?:\w+:)?t>/g)].map(m => decode(m[1]));
            shared.push(ts.join(''));
        });
    }

    const wb = get('xl/workbook.xml').toString('utf8');
    const relsXml = get('xl/_rels/workbook.xml.rels').toString('utf8');
    const relMap = {};
    for (const m of relsXml.matchAll(/<(?:\w+:)?Relationship\b([^>]*?)\/?>/g)) {
        const id = attr(m[1], 'Id');
        let target = attr(m[1], 'Target').replace(/^\//, '');
        if (!target.startsWith('xl/')) target = 'xl/' + target;
        relMap[id] = target;
    }

    const sheets = [];
    for (const m of wb.matchAll(/<(?:\w+:)?sheet\b([^>]*?)\/?>/g)) {
        const name = decode(attr(m[1], 'name'));
        const rid = attr(m[1], 'r:id');
        const xmlBuf = get(relMap[rid]);
        if (!xmlBuf) continue;
        const text = xmlBuf.toString('utf8');

        const rows = new Map();
        let maxRow = 0;
        let maxCol = 0;
        for (const rm of text.matchAll(/<(?:\w+:)?row\b([^>]*)>([\s\S]*?)<\/(?:\w+:)?row>/g)) {
            const rowNum = Number(attr(rm[1], 'r')) || 0;
            if (!rowNum) continue;
            const cells = new Map();
            for (const cm of rm[2].matchAll(/<(?:\w+:)?c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/(?:\w+:)?c>)/g)) {
                const ref = attr(cm[1], 'r');
                const type = attr(cm[1], 't');
                const inner = cm[2] || '';
                let value = '';
                if (type === 's') {
                    value = shared[Number((inner.match(/<(?:\w+:)?v>([\s\S]*?)<\/(?:\w+:)?v>/) || [])[1])] ?? '';
                } else if (type === 'inlineStr') {
                    value = [...inner.matchAll(/<(?:\w+:)?t[^>]*>([\s\S]*?)<\/(?:\w+:)?t>/g)].map(x => decode(x[1])).join('');
                } else {
                    value = decode((inner.match(/<(?:\w+:)?v>([\s\S]*?)<\/(?:\w+:)?v>/) || [])[1] || '');
                }
                value = String(value).trim();
                if (value === '') continue;
                const col = colNum(ref);
                cells.set(col, value);
                maxCol = Math.max(maxCol, col);
            }
            rows.set(rowNum, cells);
            maxRow = Math.max(maxRow, rowNum);
        }

        const merges = [];
        for (const mm of text.matchAll(/<(?:\w+:)?mergeCell\b([^>]*?)\/?>/g)) {
            const ref = attr(mm[1], 'ref');
            const [a, b] = ref.split(':');
            if (!b) continue;
            const c1 = colNum(a);
            const c2 = colNum(b);
            const r1 = Number((a.match(/\d+/) || [])[0]);
            const r2 = Number((b.match(/\d+/) || [])[0]);
            if (!c1 || !c2 || !r1 || !r2) continue;
            merges.push({top: Math.min(r1, r2), bottom: Math.max(r1, r2), left: Math.min(c1, c2), right: Math.max(c1, c2)});
        }

        sheets.push({name, headerRow: 1, maxRow, maxCol, rows, merges});
    }
    return sheets;
}

module.exports = {loadXlsxSheets};
