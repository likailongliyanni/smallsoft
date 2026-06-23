// 「智能统计（透视汇总）」：标准表的分组聚合 + 时间粒度 + 交叉表，全部浏览器本地执行。
// 纯引擎挂在 window.TablePivotKit（Node 里 module.exports 同一对象，便于无头单测）；
// DOM 结线在 initTablePivotLocal。隐私口径同其它模块：只把列摘要发给 AI，原表不上传。
(function () {
    'use strict';

    // ───────────────────────── 纯引擎 ─────────────────────────

    const AGGS = ['sum', 'count', 'count_distinct', 'avg', 'max', 'min'];
    const BUCKETS = ['year', 'quarter', 'month'];

    function toNumber(value) {
        if (value === null || value === undefined) return null;
        let text = String(value).trim();
        if (text === '') return null;
        text = text.replace(/[¥$￥,，\s%]/g, '');
        if (!/^-?\d*\.?\d+$/.test(text)) return null;
        const n = Number(text);
        return Number.isFinite(n) ? n : null;
    }

    // 解析日期 -> {y, m(1-12)}；支持 2024-01-03 / 2024/1/3 / 2024年1月 / 20240103 / Excel 序列号。
    function parseDateParts(value) {
        if (value === null || value === undefined) return null;
        const text = String(value).trim();
        if (text === '') return null;

        let match = text.match(/^(\d{4})[-/.年](\d{1,2})/);
        if (match) return {y: Number(match[1]), m: clampMonth(Number(match[2]))};

        match = text.match(/^(\d{4})(\d{2})(\d{2})$/);
        if (match) return {y: Number(match[1]), m: clampMonth(Number(match[2]))};

        // 纯数字且在合理范围内当 Excel 日期序列号（1900 系统，约 1900-2100）。
        if (/^\d{4,6}$/.test(text)) {
            const serial = Number(text);
            if (serial >= 1 && serial <= 80000) {
                const ms = Date.UTC(1899, 11, 30) + serial * 86400000;
                const d = new Date(ms);
                if (!Number.isNaN(d.getTime())) return {y: d.getUTCFullYear(), m: d.getUTCMonth() + 1};
            }
        }
        return null;
    }

    function clampMonth(m) {
        return Math.min(12, Math.max(1, m || 1));
    }

    function bucketValue(value, bucket) {
        const parts = parseDateParts(value);
        if (!parts) return String(value ?? '').trim() || '(空)';
        if (bucket === 'year') return String(parts.y);
        if (bucket === 'quarter') return `${parts.y}-Q${Math.ceil(parts.m / 3)}`;
        if (bucket === 'month') return `${parts.y}-${String(parts.m).padStart(2, '0')}`;
        return String(parts.y);
    }

    function detectKind(samples) {
        const vals = (samples || []).map(v => String(v ?? '').trim()).filter(v => v !== '');
        if (!vals.length) return 'text';
        let num = 0, date = 0, longId = 0;
        vals.forEach(v => {
            if (parseDateParts(v) && /[-/年]/.test(v)) date++;
            if (toNumber(v) !== null) num++;
            if (/^\d{11,}$/.test(v.replace(/[\s-]/g, ''))) longId++;
        });
        const n = vals.length;
        if (date / n >= 0.6) return 'date';
        if (longId / n >= 0.6) return 'id';           // 电话/条码/身份证等长数字按编号
        if (num / n >= 0.8) return 'number';
        return 'text';
    }

    // headers: [str]；rows: [{header: value}]。
    function buildPivotSummary(headers, rows, sheetName) {
        const columns = headers.map(header => {
            const samples = [];
            const seen = new Set();
            let nonEmpty = 0;
            for (const row of rows) {
                const v = String(row[header] ?? '').trim();
                if (v === '') continue;
                nonEmpty++;
                if (!seen.has(v)) {
                    seen.add(v);
                    if (samples.length < 8) samples.push(v);
                }
                if (seen.size > 5000) break;            // 唯一值上限，避免大表卡顿
            }
            return {
                header,
                kind: detectKind(samples),
                non_empty: nonEmpty,
                unique: seen.size,
                samples,
            };
        });
        return {sheet_name: sheetName || '', row_count: rows.length, columns};
    }

    // 本地兜底计划：与 TablePivotPlanService::fallbackPlan 同口径。
    function buildLocalPlan(summary) {
        const cols = (summary.columns || []);
        if (!cols.length) {
            return {dimensions: [], measures: [{column: '*', agg: 'count', label: '记录数'}],
                filters: [], pivot_column: null, sort: null, top_n: null, notes: []};
        }
        let dimension = null, dateCol = null, numberCol = null;
        cols.forEach(col => {
            if (col.kind === 'date' && !dateCol) dateCol = col.header;
            if (col.kind === 'number' && !numberCol) numberCol = col.header;
            if (!dimension && (col.kind === 'text' || col.kind === 'id')) dimension = col.header;
        });
        if (!dimension) dimension = cols[0].header;

        const dimensions = [{column: dimension, label: dimension, time_bucket: null}];
        if (dateCol) dimensions.push({column: dateCol, label: `${dateCol}(年)`, time_bucket: 'year'});

        const measures = numberCol
            ? [{column: numberCol, agg: 'sum', label: `${numberCol}合计`}]
            : [{column: '*', agg: 'count', label: '记录数'}];

        return {dimensions, measures, filters: [], pivot_column: null, sort: null, top_n: null, notes: []};
    }

    function passFilters(row, filters) {
        for (const f of (filters || [])) {
            const cell = String(row[f.column] ?? '').trim();
            const values = f.values || [];
            if (f.op === 'in' && !values.includes(cell)) return false;
            if (f.op === 'eq' && cell !== values[0]) return false;
            if (f.op === 'ne' && cell === values[0]) return false;
            if (f.op === 'contains' && !cell.includes(values[0])) return false;
            if (f.op === 'gte' || f.op === 'lte') {
                const a = toNumber(cell), b = toNumber(values[0]);
                const cmp = (a !== null && b !== null) ? (a - b) : cell.localeCompare(values[0]);
                if (f.op === 'gte' && cmp < 0) return false;
                if (f.op === 'lte' && cmp > 0) return false;
            }
        }
        return true;
    }

    function dimKeyPart(row, dim) {
        const raw = row[dim.column];
        if (dim.time_bucket && BUCKETS.includes(dim.time_bucket)) return bucketValue(raw, dim.time_bucket);
        const v = String(raw ?? '').trim();
        return v === '' ? '(空)' : v;
    }

    function newAcc(measures) {
        return measures.map(m => {
            if (m.agg === 'count') return {n: 0};
            if (m.agg === 'count_distinct') return {set: new Set()};
            if (m.agg === 'avg') return {sum: 0, n: 0};
            if (m.agg === 'max') return {v: null};
            if (m.agg === 'min') return {v: null};
            return {sum: 0};                            // sum
        });
    }

    function accumulate(acc, measures, row) {
        measures.forEach((m, i) => {
            const a = acc[i];
            if (m.agg === 'count') { a.n++; return; }
            const cell = row[m.column];
            if (m.agg === 'count_distinct') {
                const v = String(cell ?? '').trim();
                if (v !== '') a.set.add(v);
                return;
            }
            const num = toNumber(cell);
            if (m.agg === 'sum') { if (num !== null) a.sum += num; return; }
            if (m.agg === 'avg') { if (num !== null) { a.sum += num; a.n++; } return; }
            if (m.agg === 'max') { if (num !== null) a.v = (a.v === null ? num : Math.max(a.v, num)); return; }
            if (m.agg === 'min') { if (num !== null) a.v = (a.v === null ? num : Math.min(a.v, num)); return; }
        });
    }

    function finalize(acc, measures) {
        return measures.map((m, i) => {
            const a = acc[i];
            if (m.agg === 'count') return a.n;
            if (m.agg === 'count_distinct') return a.set.size;
            if (m.agg === 'avg') return a.n ? round2(a.sum / a.n) : 0;
            if (m.agg === 'max' || m.agg === 'min') return a.v === null ? '' : round2(a.v);
            return round2(a.sum);                       // sum
        });
    }

    function round2(n) {
        if (typeof n !== 'number' || !Number.isFinite(n)) return n;
        return Math.round(n * 100) / 100;
    }

    function runPivot(headers, rows, plan) {
        const dims = (plan.dimensions || []).filter(d => d && d.column);
        const measures = (plan.measures || []).filter(m => m && (m.column === '*' || m.column));
        if (!measures.length) measures.push({column: '*', agg: 'count', label: '记录数'});

        const groups = new Map();                       // key -> {parts, acc}
        let scanned = 0;
        for (const row of rows) {
            if (!passFilters(row, plan.filters)) continue;
            scanned++;
            const parts = dims.map(d => dimKeyPart(row, d));
            const key = parts.join('');
            let g = groups.get(key);
            if (!g) { g = {parts, acc: newAcc(measures)}; groups.set(key, g); }
            accumulate(g.acc, measures, row);
        }

        const dimLabels = dims.map(d => d.label || d.column);
        const measLabels = measures.map(m => m.label || m.column);
        let longRows = [...groups.values()].map(g => [...g.parts, ...finalize(g.acc, measures)]);

        // 排序
        if (plan.sort && plan.sort.by) {
            const allLabels = [...dimLabels, ...measLabels];
            const idx = allLabels.indexOf(plan.sort.by);
            if (idx >= 0) {
                const dir = plan.sort.dir === 'asc' ? 1 : -1;
                const numeric = idx >= dimLabels.length;
                longRows.sort((a, b) => {
                    const x = a[idx], y = b[idx];
                    if (numeric) return (Number(x) - Number(y)) * dir;
                    return String(x).localeCompare(String(y)) * dir;
                });
            }
        }
        if (plan.top_n && plan.top_n > 0) longRows = longRows.slice(0, plan.top_n);

        const long = {headers: [...dimLabels, ...measLabels], rows: longRows};

        // 交叉表（宽表）
        let wide = null;
        const pivotIdx = plan.pivot_column ? dimLabels.indexOf(plan.pivot_column) : -1;
        if (pivotIdx >= 0 && dims.length >= 2) {
            wide = buildWide(groups, measures, dimLabels, measLabels, pivotIdx);
        }

        return {long, wide, stats: {groups: groups.size, rowsScanned: scanned}};
    }

    function buildWide(groups, measures, dimLabels, measLabels, pivotIdx) {
        const rowDimIdx = dimLabels.map((_, i) => i).filter(i => i !== pivotIdx);
        const rowDimLabels = rowDimIdx.map(i => dimLabels[i]);
        const pivotValues = new Set();
        const cells = new Map();                        // rowKey -> {pivotVal -> [measureValues]}
        const rowKeyParts = new Map();

        groups.forEach(g => {
            const vals = finalize(g.acc, measures);
            const pivotVal = g.parts[pivotIdx];
            pivotValues.add(pivotVal);
            const rowParts = rowDimIdx.map(i => g.parts[i]);
            const rowKey = rowParts.join('');
            if (!rowKeyParts.has(rowKey)) rowKeyParts.set(rowKey, rowParts);
            if (!cells.has(rowKey)) cells.set(rowKey, {});
            cells.get(rowKey)[pivotVal] = vals;
        });

        const pivotList = [...pivotValues].sort((a, b) => String(a).localeCompare(String(b)));
        const multi = measures.length > 1;
        const colDefs = [];
        pivotList.forEach(pv => {
            measures.forEach((m, mi) => {
                colDefs.push({pivotVal: pv, mi, label: multi ? `${pv}·${measLabels[mi]}` : String(pv)});
            });
        });

        const headers = [...rowDimLabels, ...colDefs.map(c => c.label)];
        const rows = [...rowKeyParts.entries()].map(([rowKey, parts]) => {
            const cellMap = cells.get(rowKey) || {};
            const out = [...parts];
            colDefs.forEach(c => {
                const v = cellMap[c.pivotVal];
                out.push(v ? v[c.mi] : '');
            });
            return out;
        });
        return {headers, rows};
    }

    const TablePivotKit = {
        toNumber, parseDateParts, bucketValue, detectKind,
        buildPivotSummary, buildLocalPlan, runPivot,
    };
    if (typeof module !== 'undefined' && module.exports) module.exports = TablePivotKit;
    if (typeof window !== 'undefined') window.TablePivotKit = TablePivotKit;

    // ───────────────────────── 导出 xlsx（多 sheet） ─────────────────────────

    function escapeXml(text) {
        return String(text)
            .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;').replaceAll("'", '&apos;');
    }
    function colLetters(col) {
        let s = '';
        while (col > 0) { col--; s = String.fromCharCode(65 + (col % 26)) + s; col = Math.floor(col / 26); }
        return s || 'A';
    }
    function isPlainNumber(text) {
        if (!/^-?\d{1,11}(\.\d{1,6})?$/.test(text)) return false;
        if (/^0\d/.test(text)) return false;
        return true;
    }
    function worksheetXml(headers, rows) {
        const allRows = [headers, ...rows];
        let xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + `<dimension ref="A1:${colLetters(Math.max(1, headers.length))}${Math.max(1, allRows.length)}"/>`
            + '<sheetData>';
        allRows.forEach((row, rowIndex) => {
            const r = rowIndex + 1;
            let rowXml = `<row r="${r}">`;
            row.forEach((value, colIndex) => {
                const ref = `${colLetters(colIndex + 1)}${r}`;
                const text = String(value ?? '');
                if (text === '') return;
                if (rowIndex > 0 && isPlainNumber(text)) {
                    rowXml += `<c r="${ref}"><v>${text}</v></c>`;
                } else {
                    rowXml += `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${escapeXml(text)}</t></is></c>`;
                }
            });
            xml += rowXml + '</row>';
        });
        return xml + '</sheetData></worksheet>';
    }
    function sanitizeSheetName(name, fallback, used) {
        let text = String(name || '').replace(/[\\/?*\[\]:']+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 28);
        if (!text) text = fallback || 'Sheet';
        let candidate = text, index = 2;
        while (used && used.has(candidate.toLowerCase())) candidate = `${text.slice(0, 25)}_${index++}`;
        if (used) used.add(candidate.toLowerCase());
        return candidate;
    }
    function buildMultiSheetXlsx(sheetDefs) {
        const kit = window.ExcelLocalKit;
        const used = new Set();
        const sheets = sheetDefs.map((def, i) => ({
            name: sanitizeSheetName(def.name, `Sheet${i + 1}`, used), headers: def.headers, rows: def.rows,
        }));
        let contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            + '<Default Extension="xml" ContentType="application/xml"/>'
            + '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>';
        sheets.forEach((_, i) => {
            contentTypes += `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`;
        });
        contentTypes += '</Types>';
        const rootRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            + '</Relationships>';
        let workbookXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            + '<sheets>';
        sheets.forEach((sheet, i) => { workbookXml += `<sheet name="${escapeXml(sheet.name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`; });
        workbookXml += '</sheets></workbook>';
        let workbookRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">';
        sheets.forEach((_, i) => { workbookRels += `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`; });
        workbookRels += '</Relationships>';
        const files = [
            {name: '[Content_Types].xml', bytes: kit.utf8Bytes(contentTypes)},
            {name: '_rels/.rels', bytes: kit.utf8Bytes(rootRels)},
            {name: 'xl/workbook.xml', bytes: kit.utf8Bytes(workbookXml)},
            {name: 'xl/_rels/workbook.xml.rels', bytes: kit.utf8Bytes(workbookRels)},
        ];
        sheets.forEach((sheet, i) => { files.push({name: `xl/worksheets/sheet${i + 1}.xml`, bytes: kit.utf8Bytes(worksheetXml(sheet.headers, sheet.rows))}); });
        return new Blob([kit.createStoredZip(files)], {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
    }

    // 把 parseXlsxWorkbook 的 sheet（rows: Map 行->Map 列->值）转成 {headers, rows[]}。
    // 标准表：取第一行有 >=2 个非空单元格的行做表头，其后为数据行。
    function sheetToTable(sheet) {
        const maxRow = sheet.maxRow || 0;
        const maxCol = sheet.maxCol || 0;
        const cell = (r, c) => String(sheet.rows.get(r)?.get(c) ?? '').trim();

        let headerRow = 0;
        for (let r = 1; r <= maxRow; r++) {
            let nonEmpty = 0;
            for (let c = 1; c <= maxCol; c++) if (cell(r, c) !== '') nonEmpty++;
            if (nonEmpty >= 2) { headerRow = r; break; }
            if (nonEmpty >= 1 && headerRow === 0) headerRow = r;     // 兜底：单列表
        }
        if (headerRow === 0) return {headers: [], rows: []};

        const headers = [];
        const colKeys = [];
        const usedHeaders = new Set();
        for (let c = 1; c <= maxCol; c++) {
            let h = cell(headerRow, c);
            if (h === '') continue;                                   // 跳过无表头的空列
            let key = h, i = 2;
            while (usedHeaders.has(key)) key = `${h}_${i++}`;
            usedHeaders.add(key);
            headers.push(key);
            colKeys.push(c);
        }

        const rows = [];
        for (let r = headerRow + 1; r <= maxRow; r++) {
            const obj = {};
            let any = false;
            colKeys.forEach((c, idx) => {
                const v = cell(r, c);
                obj[headers[idx]] = v;
                if (v !== '') any = true;
            });
            if (any) rows.push(obj);
        }
        return {headers, rows};
    }

    // ───────────────────────── DOM 结线 ─────────────────────────

    const initTablePivotLocal = function initTablePivotLocal(deps) {
        const kit = window.ExcelLocalKit;
        const pivot = window.TablePivotKit;
        if (!kit || !pivot) return;

        const userApi = deps.userApi;
        const escapeHtml = deps.escapeHtml;
        const userTokenKey = deps.userTokenKey;

        const panel = document.querySelector('#tablePivotPanel');
        if (!panel) return;

        const fileInput = document.querySelector('#pivotFile');
        const fileNameEl = document.querySelector('#pivotFileName');
        const fileMetaEl = document.querySelector('#pivotFileMeta');
        const sheetSelect = document.querySelector('#pivotSheetSelect');
        const instructionEl = document.querySelector('#pivotInstruction');
        const planBtn = document.querySelector('#pivotPlanBtn');
        const runBtn = document.querySelector('#pivotRunBtn');
        const downloadBtn = document.querySelector('#pivotDownloadBtn');
        const clearBtn = document.querySelector('#pivotClearBtn');
        const statusEl = document.querySelector('#pivotStatus');
        const warningsBox = document.querySelector('#pivotWarnings');
        const planSection = document.querySelector('#pivotPlanSection');
        const dimsBox = document.querySelector('#pivotDims');
        const measBox = document.querySelector('#pivotMeasures');
        const pivotColSelect = document.querySelector('#pivotPivotCol');
        const addDimBtn = document.querySelector('#pivotAddDim');
        const addMeasBtn = document.querySelector('#pivotAddMeasure');
        const resultSection = document.querySelector('#pivotResultSection');
        const resultBody = document.querySelector('#pivotResultBody');

        let workbook = null;
        let table = null;          // {headers, rows}
        let summary = null;
        let lastResult = null;     // {long, wide, stats}

        const AGG_LABELS = {sum: '求和', count: '计数', count_distinct: '去重计数', avg: '平均', max: '最大', min: '最小'};
        const BUCKET_LABELS = {'': '不分时间', year: '按年', quarter: '按季度', month: '按月'};

        fileInput?.addEventListener('change', async () => {
            const file = fileInput.files?.[0];
            if (!file) return;
            setStatus('正在本地读取表格...');
            try {
                workbook = await kit.parseXlsxWorkbook(file, {images: false});
                if (fileNameEl) fileNameEl.textContent = file.name;
                if (fileMetaEl) fileMetaEl.textContent = `${workbook.sheets.length} 个 sheet · ${kit.formatBytes(file.size)} · 不上传服务器`;
                renderSheetOptions();
                loadSelectedSheet();
                resetPlan();
                resetResult();
                setStatus('已本地读取，请用自然语言描述要统计什么，再点「AI 规划统计」。', 'success');
            } catch (error) {
                setStatus(`读取失败：${error.message}`, 'error');
            } finally {
                fileInput.value = '';
            }
        });

        sheetSelect?.addEventListener('change', () => {
            loadSelectedSheet();
            resetPlan();
            resetResult();
        });

        planBtn?.addEventListener('click', buildPlan);
        runBtn?.addEventListener('click', runStats);
        addDimBtn?.addEventListener('click', () => { addDimRow(); });
        addMeasBtn?.addEventListener('click', () => { addMeasRow(); });

        downloadBtn?.addEventListener('click', () => {
            if (!lastResult) return;
            const defs = [{name: '汇总', headers: lastResult.long.headers, rows: lastResult.long.rows}];
            if (lastResult.wide) defs.push({name: '交叉表', headers: lastResult.wide.headers, rows: lastResult.wide.rows});
            const stamp = new Date().toISOString().slice(0, 16).replace(/[-T:]/g, '');
            kit.saveBlob(buildMultiSheetXlsx(defs), `智能统计-${stamp}.xlsx`);
        });

        clearBtn?.addEventListener('click', () => {
            workbook = null; table = null; summary = null;
            if (fileNameEl) fileNameEl.textContent = '请选择一个 .xlsx 文件';
            if (fileMetaEl) fileMetaEl.textContent = '文件只在浏览器本地读取，不上传服务器';
            if (sheetSelect) { sheetSelect.innerHTML = ''; sheetSelect.classList.add('hidden'); }
            resetPlan();
            resetResult();
            setStatus('');
        });

        function renderSheetOptions() {
            if (!sheetSelect) return;
            sheetSelect.innerHTML = workbook.sheets.map((s, i) => `<option value="${i}">${escapeHtml(s.name)}</option>`).join('');
            sheetSelect.classList.toggle('hidden', workbook.sheets.length <= 1);
        }

        function loadSelectedSheet() {
            if (!workbook) return;
            const idx = Number(sheetSelect?.value || 0) || 0;
            const sheet = workbook.sheets[idx] || workbook.sheets[0];
            table = sheetToTable(sheet);
            summary = pivot.buildPivotSummary(table.headers, table.rows, sheet.name);
            if (fileMetaEl && table) {
                fileMetaEl.textContent = `${table.headers.length} 列 · ${table.rows.length} 行 · 不上传服务器`;
            }
        }

        async function buildPlan() {
            if (!table || !table.headers.length) {
                setStatus('请先选择一张标准表（带表头的二维表）。', 'error');
                return;
            }
            planBtn.disabled = true;
            const warnings = [];
            const token = localStorage.getItem(userTokenKey);
            const instruction = String(instructionEl?.value || '').trim();
            let plan;
            try {
                if (!token || typeof userApi !== 'function') {
                    plan = pivot.buildLocalPlan(summary);
                    warnings.push('未登录，已用本地规则推断维度和度量；登录后 AI 按你的描述规划更准。');
                } else {
                    setStatus('正在调用 AI 规划统计...');
                    try {
                        const response = await userApi('/api/excel-automation/table-pivot/plan', {
                            method: 'POST', body: {instruction, summary},
                        });
                        plan = response.plan || pivot.buildLocalPlan(summary);
                        (Array.isArray(response.warnings) ? response.warnings : []).forEach(w => warnings.push(w));
                    } catch (error) {
                        plan = pivot.buildLocalPlan(summary);
                        warnings.push(`AI 规划失败，已用本地规则：${error.message}`);
                    }
                }
                renderPlan(plan);
                renderWarnings(warnings);
                setStatus('已生成统计方案，请核对维度和度量后点「开始统计」。', 'success');
            } finally {
                planBtn.disabled = false;
            }
        }

        function renderPlan(plan) {
            planSection?.classList.remove('hidden');
            if (dimsBox) dimsBox.innerHTML = '';
            if (measBox) measBox.innerHTML = '';
            (plan.dimensions || []).forEach(d => addDimRow(d));
            if (!(plan.dimensions || []).length) addDimRow();
            (plan.measures || []).forEach(m => addMeasRow(m));
            if (!(plan.measures || []).length) addMeasRow();
            refreshPivotColOptions(plan.pivot_column);
        }

        function columnOptions(selected, includeStar) {
            const opts = (includeStar ? ['<option value="*">记录数(计数)</option>'] : []);
            (table?.headers || []).forEach(h => {
                opts.push(`<option value="${escapeHtml(h)}"${h === selected ? ' selected' : ''}>${escapeHtml(h)}</option>`);
            });
            return opts.join('');
        }

        function kindOf(header) {
            const col = (summary?.columns || []).find(c => c.header === header);
            return col ? col.kind : 'text';
        }

        function addDimRow(dim) {
            if (!dimsBox) return;
            const d = dim || {column: table.headers[0], label: '', time_bucket: ''};
            const row = document.createElement('div');
            row.className = 'pivot-row';
            row.innerHTML = `
                <select class="pivot-col">${columnOptions(d.column, false)}</select>
                <select class="pivot-bucket">${Object.entries(BUCKET_LABELS).map(([v, t]) =>
                    `<option value="${v}"${(d.time_bucket || '') === v ? ' selected' : ''}>${t}</option>`).join('')}</select>
                <input class="pivot-label" placeholder="显示名(可选)" value="${escapeHtml(d.label || '')}">
                <button type="button" class="excel-text-btn pivot-del">删除</button>`;
            dimsBox.appendChild(row);
            const colSel = row.querySelector('.pivot-col');
            const bucketSel = row.querySelector('.pivot-bucket');
            const toggleBucket = () => { bucketSel.disabled = kindOf(colSel.value) !== 'date'; };
            toggleBucket();
            colSel.addEventListener('change', toggleBucket);
            row.querySelector('.pivot-del').addEventListener('click', () => { row.remove(); refreshPivotColOptions(); });
            colSel.addEventListener('change', () => refreshPivotColOptions());
            row.querySelector('.pivot-label').addEventListener('input', () => refreshPivotColOptions());
        }

        function addMeasRow(meas) {
            if (!measBox) return;
            const m = meas || {column: '*', agg: 'count', label: ''};
            const row = document.createElement('div');
            row.className = 'pivot-row';
            row.innerHTML = `
                <select class="pivot-col">${columnOptions(m.column, true)}</select>
                <select class="pivot-agg">${AGGS.map(a =>
                    `<option value="${a}"${m.agg === a ? ' selected' : ''}>${AGG_LABELS[a]}</option>`).join('')}</select>
                <input class="pivot-label" placeholder="显示名(可选)" value="${escapeHtml(m.label || '')}">
                <button type="button" class="excel-text-btn pivot-del">删除</button>`;
            if (row.querySelector('.pivot-col').value !== m.column && m.column === '*') {
                row.querySelector('.pivot-col').value = '*';
            }
            measBox.appendChild(row);
            row.querySelector('.pivot-del').addEventListener('click', () => row.remove());
        }

        function refreshPivotColOptions(selected) {
            if (!pivotColSelect) return;
            const current = selected !== undefined ? selected : pivotColSelect.value;
            const labels = readDimLabels();
            pivotColSelect.innerHTML = '<option value="">不做交叉表（长表）</option>'
                + labels.map(l => `<option value="${escapeHtml(l)}"${l === current ? ' selected' : ''}>${escapeHtml(l)}</option>`).join('');
        }

        function readDimLabels() {
            const labels = [];
            dimsBox?.querySelectorAll('.pivot-row').forEach(row => {
                const col = row.querySelector('.pivot-col').value;
                const bucket = row.querySelector('.pivot-bucket');
                const label = row.querySelector('.pivot-label').value.trim()
                    || (bucket && !bucket.disabled && bucket.value ? `${col}(${BUCKET_LABELS[bucket.value].replace('按', '')})` : col);
                labels.push(label);
            });
            return labels;
        }

        function collectPlan() {
            const dimSeen = new Set();
            const dimensions = [];
            dimsBox?.querySelectorAll('.pivot-row').forEach(row => {
                const column = row.querySelector('.pivot-col').value;
                const bucketSel = row.querySelector('.pivot-bucket');
                const bucket = (bucketSel && !bucketSel.disabled) ? bucketSel.value : '';
                let label = row.querySelector('.pivot-label').value.trim()
                    || (bucket ? `${column}(${BUCKET_LABELS[bucket].replace('按', '')})` : column);
                while (dimSeen.has(label)) label += '_';
                dimSeen.add(label);
                dimensions.push({column, label, time_bucket: bucket || null});
            });

            const measSeen = new Set();
            const measures = [];
            measBox?.querySelectorAll('.pivot-row').forEach(row => {
                const column = row.querySelector('.pivot-col').value;
                const agg = row.querySelector('.pivot-agg').value;
                let label = row.querySelector('.pivot-label').value.trim()
                    || (column === '*' ? '记录数' : `${column}${AGG_LABELS[agg]}`);
                while (measSeen.has(label)) label += '_';
                measSeen.add(label);
                measures.push({column, agg, label});
            });

            const pivotCol = pivotColSelect?.value || null;
            return {dimensions, measures, filters: [], pivot_column: pivotCol || null, sort: null, top_n: null};
        }

        function runStats() {
            if (!table || !table.headers.length) {
                setStatus('请先选择一张标准表。', 'error');
                return;
            }
            if (!planSection || planSection.classList.contains('hidden')) {
                setStatus('请先点「AI 规划统计」生成方案。', 'error');
                return;
            }
            const plan = collectPlan();
            if (!plan.measures.length) { setStatus('至少要有一个统计度量。', 'error'); return; }
            try {
                lastResult = pivot.runPivot(table.headers, table.rows, plan);
                renderResult(lastResult);
                downloadBtn?.classList.remove('hidden');
                setStatus(`统计完成：${lastResult.stats.groups} 组，扫描 ${lastResult.stats.rowsScanned} 行。`, 'success');
            } catch (error) {
                setStatus(`统计失败：${error.message}`, 'error');
            }
        }

        function renderResult(result) {
            resultSection?.classList.remove('hidden');
            if (!resultBody) return;
            let html = `<h3>汇总表（${result.long.rows.length} 行）</h3>${tableHtml(result.long, 100)}`;
            if (result.wide) html += `<h3 style="margin-top:16px">交叉表（${result.wide.rows.length} 行）</h3>${tableHtml(result.wide, 100)}`;
            resultBody.innerHTML = html;
        }

        function tableHtml(data, limit) {
            const head = `<tr>${data.headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr>`;
            const rows = data.rows.slice(0, limit).map(r =>
                `<tr>${r.map(c => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`).join('');
            const more = data.rows.length > limit ? `<p class="excel-meta">仅预览前 ${limit} 行，下载可见全部。</p>` : '';
            return `<div class="tool-table-wrap"><table>${head}${rows}</table></div>${more}`;
        }

        function renderWarnings(warnings) {
            if (!warningsBox) return;
            if (!warnings || !warnings.length) { warningsBox.classList.add('hidden'); warningsBox.innerHTML = ''; return; }
            warningsBox.classList.remove('hidden');
            warningsBox.innerHTML = warnings.map(w => `<p>${escapeHtml(w)}</p>`).join('');
        }

        function resetPlan() {
            planSection?.classList.add('hidden');
            if (dimsBox) dimsBox.innerHTML = '';
            if (measBox) measBox.innerHTML = '';
            renderWarnings([]);
        }

        function resetResult() {
            lastResult = null;
            resultSection?.classList.add('hidden');
            if (resultBody) resultBody.innerHTML = '';
            downloadBtn?.classList.add('hidden');
        }

        function setStatus(text, type) {
            if (!statusEl) return;
            statusEl.textContent = text || '';
            statusEl.classList.toggle('error', type === 'error');
            statusEl.classList.toggle('success', type === 'success');
        }
    };

    if (typeof window !== 'undefined') window.initTablePivotLocal = initTablePivotLocal;
})();
