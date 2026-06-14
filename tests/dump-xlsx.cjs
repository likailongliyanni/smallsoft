// 调试工具：把 xlsx 的所有 sheet 内容倒成文本。 node tests/dump-xlsx.cjs <file> [maxRows]
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
        if (buf.readUInt32LE(offset) !== 0x02014b50) throw new Error('bad central dir');
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

function parseSharedStrings(xml) {
    if (!xml) return [];
    const out = [];
    const sis = xml.toString('utf8').split(/<si[ >]/).slice(1);
    for (const si of sis) {
        const ts = [...si.matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)].map(m => decode(m[1]));
        out.push(ts.join(''));
    }
    return out;
}

function decode(s) {
    return s.replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&quot;', '"')
        .replaceAll('&apos;', "'").replaceAll('&amp;', '&');
}

function colNum(ref) {
    const m = ref.match(/^([A-Z]+)/);
    if (!m) return 0;
    return m[1].split('').reduce((n, c) => n * 26 + c.charCodeAt(0) - 64, 0);
}

const file = process.argv[2];
const maxRows = Number(process.argv[3] || 80);
const buf = fs.readFileSync(file);
const get = readZip(buf);
const shared = parseSharedStrings(get('xl/sharedStrings.xml'));

const wb = get('xl/workbook.xml').toString('utf8');
const rels = get('xl/_rels/workbook.xml.rels').toString('utf8');
const relMap = {};
for (const m of rels.matchAll(/<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"/g)) {
    relMap[m[1]] = m[2].replace(/^\//, '').startsWith('xl/') ? m[2].replace(/^\//, '') : 'xl/' + m[2];
}
const sheets = [...wb.matchAll(/<sheet[^>]*name="([^"]+)"[^>]*r:id="([^"]+)"/g)]
    .map(m => ({name: decode(m[1]), path: relMap[m[2]]}));

console.log(`=== ${file.split(/[\\/]/).pop()} : ${sheets.length} sheets ===`);
for (const s of sheets) {
    const xml = get(s.path);
    if (!xml) { console.log(`-- sheet ${s.name}: missing ${s.path}`); continue; }
    const text = xml.toString('utf8');
    // 合并单元格
    const merges = [...text.matchAll(/<mergeCell ref="([^"]+)"/g)].map(m => m[1]);
    const rows = [];
    for (const rm of text.matchAll(/<row[^>]*r="(\d+)"[^>]*>([\s\S]*?)<\/row>/g)) {
        const rowNum = Number(rm[1]);
        const cells = {};
        for (const cm of rm[2].matchAll(/<c r="([A-Z]+\d+)"([^>]*)>([\s\S]*?)<\/c>/g)) {
            const attrs = cm[2];
            const inner = cm[3];
            let v = '';
            const t = (attrs.match(/t="([^"]+)"/) || [])[1] || '';
            if (t === 's') {
                const idx = Number((inner.match(/<v>(\d+)<\/v>/) || [])[1]);
                v = shared[idx] ?? '';
            } else if (t === 'inlineStr') {
                v = [...inner.matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)].map(m => decode(m[1])).join('');
            } else {
                v = decode((inner.match(/<v>([\s\S]*?)<\/v>/) || [])[1] || '');
            }
            if (v !== '') cells[colNum(cm[1])] = v;
        }
        rows.push({rowNum, cells});
    }
    console.log(`\n-- sheet「${s.name}」 rows=${rows.length} merges=${merges.length}${merges.length ? ' [' + merges.slice(0, 20).join(',') + ']' : ''}`);
    rows.slice(0, maxRows).forEach(({rowNum, cells}) => {
        const maxCol = Math.max(0, ...Object.keys(cells).map(Number));
        const vals = [];
        for (let c = 1; c <= maxCol; c++) vals.push(cells[c] ?? '');
        console.log(`r${String(rowNum).padStart(3)} | ${vals.map(v => String(v).slice(0, 22)).join(' | ')}`);
    });
    if (rows.length > maxRows) console.log(`... (${rows.length - maxRows} more rows)`);
}
