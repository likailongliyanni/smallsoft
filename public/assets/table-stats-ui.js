(function () {
    'use strict';

    // ---------------- 纯逻辑（可无头单测） ----------------

    function parseNumber(value) {
        if (typeof value === 'number') return Number.isFinite(value) ? value : NaN;
        let s = String(value == null ? '' : value).trim();
        if (!s) return NaN;
        s = s.replace(/[,，¥￥$\s%　]/g, '');
        if (!/[0-9]/.test(s)) return NaN;
        const n = Number(s);
        return Number.isFinite(n) ? n : NaN;
    }

    const AGG_LABELS = {sum: '求和', count: '计数', avg: '平均', distinct: '去重计数'};

    // 按单个维度分组聚合，排序取 TopN。
    // dataRows: [{[colIndex]: value}], dimIndex/metricIndex: 1-based 列号
    function aggregateByDimension(dataRows, dimIndex, metricIndex, agg, topN) {
        const groups = new Map();
        for (const row of dataRows) {
            const key = String(row[dimIndex] == null ? '' : row[dimIndex]).trim();
            if (!key) continue;
            let g = groups.get(key);
            if (!g) {
                g = {key, sum: 0, count: 0, numCount: 0, set: null};
                groups.set(key, g);
            }
            g.count++;
            if (agg === 'sum' || agg === 'avg') {
                const n = parseNumber(row[metricIndex]);
                if (!Number.isNaN(n)) {
                    g.sum += n;
                    g.numCount++;
                }
            } else if (agg === 'distinct') {
                const v = String(row[metricIndex] == null ? '' : row[metricIndex]).trim();
                if (v) (g.set || (g.set = new Set())).add(v);
            }
        }

        const rows = [];
        for (const g of groups.values()) {
            let value;
            if (agg === 'sum') value = g.sum;
            else if (agg === 'count') value = g.count;
            else if (agg === 'avg') value = g.numCount ? g.sum / g.numCount : 0;
            else value = g.set ? g.set.size : 0;
            rows.push({key: g.key, value, count: g.count});
        }
        rows.sort((a, b) => b.value - a.value || a.key.localeCompare(b.key, 'zh'));

        const total = agg === 'avg' ? 0 : rows.reduce((s, r) => s + r.value, 0);
        const limit = Math.max(1, Math.min(10000, topN | 0 || 10));
        const top = rows.slice(0, limit).map((r, i) => ({
            rank: i + 1,
            key: r.key,
            value: r.value,
            count: r.count,
            share: (agg !== 'avg' && total > 0) ? r.value / total : null,
        }));
        return {top, groupCount: rows.length, total};
    }

    function readSheetTable(sheet) {
        const headerRow = sheet.headerRow || 1;
        const maxCol = sheet.maxCol || 0;
        const maxRow = sheet.maxRow || 0;
        const columns = [];
        for (let c = 1; c <= maxCol; c++) {
            const name = String(sheet.rows.get(headerRow)?.get(c) || '').trim() || colLetters(c);
            columns.push({index: c, name});
        }
        const dataRows = [];
        for (let r = headerRow + 1; r <= maxRow; r++) {
            const cells = sheet.rows.get(r);
            if (!cells) continue;
            const row = {};
            let any = false;
            for (let c = 1; c <= maxCol; c++) {
                const v = String(cells.get(c) || '').trim();
                row[c] = v;
                if (v) any = true;
            }
            if (any) dataRows.push(row);
        }
        columns.forEach(col => {
            let num = 0;
            let filled = 0;
            for (const row of dataRows) {
                const v = row[col.index];
                if (!v) continue;
                filled++;
                if (!Number.isNaN(parseNumber(v))) num++;
            }
            col.filled = filled;
            col.kind = filled > 0 && num / filled >= 0.6 ? 'number' : 'text';
        });
        return {columns, dataRows};
    }

    function formatValue(value, agg) {
        if (!Number.isFinite(value)) return '0';
        if (agg === 'count' || agg === 'distinct' || Number.isInteger(value)) {
            return Math.round(value).toLocaleString('zh-CN');
        }
        return value.toLocaleString('zh-CN', {maximumFractionDigits: 2});
    }

    function formatShare(share) {
        return share == null ? '-' : `${(share * 100).toFixed(1)}%`;
    }

    // ---------------- 多 sheet xlsx 导出（复用 ExcelLocalKit） ----------------

    function escapeXml(text) {
        return String(text)
            .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;').replaceAll("'", '&apos;');
    }

    function colLetters(col) {
        let letters = '';
        while (col > 0) {
            col--;
            letters = String.fromCharCode(65 + (col % 26)) + letters;
            col = Math.floor(col / 26);
        }
        return letters || 'A';
    }

    function sanitizeSheetName(name, fallback, used) {
        let s = String(name || '').replace(/[\\/?*\[\]:]/g, ' ').trim().slice(0, 31) || fallback;
        let candidate = s;
        let i = 2;
        while (used.has(candidate.toLowerCase())) {
            const suffix = `-${i++}`;
            candidate = s.slice(0, 31 - suffix.length) + suffix;
        }
        used.add(candidate.toLowerCase());
        return candidate;
    }

    function worksheetXml(headers, rows) {
        let xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>';
        [headers, ...rows].forEach((row, ri) => {
            const r = ri + 1;
            xml += `<row r="${r}">`;
            row.forEach((val, ci) => {
                if (val === '' || val == null) return;
                const ref = colLetters(ci + 1) + r;
                if (ri > 0 && typeof val === 'number' && Number.isFinite(val)) {
                    xml += `<c r="${ref}"><v>${val}</v></c>`;
                } else {
                    xml += `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${escapeXml(String(val))}</t></is></c>`;
                }
            });
            xml += '</row>';
        });
        xml += '</sheetData></worksheet>';
        return xml;
    }

    function buildMultiSheetXlsx(sheetDefs) {
        const kit = window.ExcelLocalKit;
        const used = new Set();
        const sheets = sheetDefs.map((def, index) => ({
            name: sanitizeSheetName(def.name, `Sheet${index + 1}`, used),
            headers: def.headers,
            rows: def.rows,
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
            + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>';
        sheets.forEach((sheet, i) => {
            workbookXml += `<sheet name="${escapeXml(sheet.name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`;
        });
        workbookXml += '</sheets></workbook>';

        let workbookRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">';
        sheets.forEach((_, i) => {
            workbookRels += `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`;
        });
        workbookRels += '</Relationships>';

        const files = [
            {name: '[Content_Types].xml', bytes: kit.utf8Bytes(contentTypes)},
            {name: '_rels/.rels', bytes: kit.utf8Bytes(rootRels)},
            {name: 'xl/workbook.xml', bytes: kit.utf8Bytes(workbookXml)},
            {name: 'xl/_rels/workbook.xml.rels', bytes: kit.utf8Bytes(workbookRels)},
        ];
        sheets.forEach((sheet, i) => {
            files.push({name: `xl/worksheets/sheet${i + 1}.xml`, bytes: kit.utf8Bytes(worksheetXml(sheet.headers, sheet.rows))});
        });

        return new Blob([kit.createStoredZip(files)], {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
    }

    const TableStatsKit = {parseNumber, aggregateByDimension, readSheetTable, buildMultiSheetXlsx, formatValue, formatShare};
    if (typeof window !== 'undefined') window.TableStatsKit = TableStatsKit;
    if (typeof module !== 'undefined' && module.exports) module.exports = TableStatsKit;

    // ---------------- UI 结线 ----------------

    if (typeof window === 'undefined') return;

    window.initTableStatsLocal = function initTableStatsLocal(deps) {
        const kit = window.ExcelLocalKit;
        if (!kit) return;
        const escapeHtml = deps.escapeHtml;
        const userApi = deps.userApi;
        const userTokenKey = deps.userTokenKey;

        const panel = document.querySelector('#tableStatsPanel');
        if (!panel) return;

        const fileInput = document.querySelector('#statsFile');
        const fileNameEl = document.querySelector('#statsFileName');
        const fileMetaEl = document.querySelector('#statsFileMeta');
        const resultMeta = document.querySelector('#statsResultMeta');
        const sheetSection = document.querySelector('#statsSheetSection');
        const sheetSelect = document.querySelector('#statsSheetSelect');
        const dimList = document.querySelector('#statsDimList');
        const aggSelect = document.querySelector('#statsAggSelect');
        const metricLabel = document.querySelector('#statsMetricLabel');
        const metricSelect = document.querySelector('#statsMetricSelect');
        const topNInput = document.querySelector('#statsTopN');
        const warningsBox = document.querySelector('#statsWarnings');
        const statusEl = document.querySelector('#statsStatus');
        const runBtn = document.querySelector('#statsRunBtn');
        const downloadBtn = document.querySelector('#statsDownloadBtn');
        const clearBtn = document.querySelector('#statsClearBtn');
        const resultSection = document.querySelector('#statsResultSection');
        const resultBody = document.querySelector('#statsResultBody');
        const instructionEl = document.querySelector('#statsInstruction');
        const aiBtn = document.querySelector('#statsAiBtn');
        const insightBtn = document.querySelector('#statsInsightBtn');
        const insightBox = document.querySelector('#statsInsight');

        let workbook = null;
        let activeTable = null;   // {columns, dataRows}
        let lastResults = null;   // [{dimName, metricLabel, agg, top}]
        let lastFileBase = 'stats';

        fileInput?.addEventListener('change', async () => {
            const file = fileInput.files?.[0];
            resetResult();
            if (!file) return;
            setStatus('正在本地读取表格...');
            try {
                workbook = await kit.parseXlsxWorkbook(file, {images: false});
                lastFileBase = file.name.replace(/\.xlsx$/i, '') || 'stats';
                fileNameEl.textContent = file.name;
                fileMetaEl.textContent = `${workbook.sheets.length} 个 sheet · ${kit.formatBytes(file.size)} · 本地读取`;
                renderSheetOptions();
                loadActiveSheet();
                setStatus('已读取，请在右侧勾选维度和统计方式。', 'success');
            } catch (error) {
                workbook = null;
                setStatus(`读取失败：${error.message}`, 'error');
            } finally {
                fileInput.value = '';
            }
        });

        sheetSelect?.addEventListener('change', loadActiveSheet);
        aggSelect?.addEventListener('change', syncMetricVisibility);

        runBtn?.addEventListener('click', () => {
            if (!activeTable) {
                setStatus('请先选择表格。', 'error');
                return;
            }
            const dims = selectedDimensions();
            if (!dims.length) {
                setStatus('请至少勾选一个维度。', 'error');
                return;
            }
            const agg = aggSelect.value;
            const metricIndex = Number(metricSelect.value) || 0;
            if (agg !== 'count' && !metricIndex) {
                setStatus('当前统计方式需要选一个指标列。', 'error');
                return;
            }
            const topN = clampTopN(topNInput.value);
            const list = dims.map(dim => ({
                dimIndex: dim.index, dimName: dim.name,
                metricIndex, metricName: columnName(metricIndex), agg, topN,
            }));
            runAnalyses(list, '统计完成');
        });

        aiBtn?.addEventListener('click', async () => {
            if (!activeTable) {
                setStatus('请先选择表格。', 'error');
                return;
            }
            if (!localStorage.getItem(userTokenKey)) {
                setStatus('AI 智能分析需要先登录。', 'error');
                return;
            }
            aiBtn.disabled = true;
            setStatus('AI 正在分析这张表...');
            try {
                const resp = await userApi('/api/excel-automation/stats/plan', {
                    method: 'POST',
                    body: {instruction: String(instructionEl?.value || '').trim(), summary: buildSummary()},
                });
                const list = mapAnalyses(Array.isArray(resp.analyses) ? resp.analyses : []);
                renderWarnings(resp.warnings || []);
                if (!list.length) {
                    setStatus('AI 没给出可用的分析方案，请在下面手动勾选维度。', 'error');
                    return;
                }
                applyToControls(list);
                runAnalyses(list, `${resp.source === 'ai' ? 'AI' : '本地规则'}分析完成`);
            } catch (error) {
                setStatus(`AI 分析失败：${error.message}`, 'error');
            } finally {
                aiBtn.disabled = false;
            }
        });

        insightBtn?.addEventListener('click', async () => {
            if (!lastResults || !lastResults.length) {
                setStatus('请先出统计结果。', 'error');
                return;
            }
            if (!localStorage.getItem(userTokenKey)) {
                setStatus('AI 解读需要先登录。', 'error');
                return;
            }
            insightBtn.disabled = true;
            const label = insightBtn.textContent;
            insightBtn.textContent = 'AI 解读中...';
            try {
                const results = lastResults.map(r => ({
                    dimension: r.dimName,
                    agg: AGG_LABELS[r.agg] || r.agg,
                    metric: r.metricName,
                    group_count: r.groupCount,
                    top: r.top.slice(0, 10).map(t => ({key: t.key, value: t.value, share: t.share})),
                }));
                const resp = await userApi('/api/excel-automation/stats/insight', {method: 'POST', body: {results}});
                const text = String(resp.insight || '').trim();
                if (insightBox) {
                    insightBox.textContent = text || (resp.warnings && resp.warnings[0]) || 'AI 没有返回解读。';
                    insightBox.classList.remove('hidden');
                }
            } catch (error) {
                if (insightBox) {
                    insightBox.textContent = `AI 解读失败：${error.message}`;
                    insightBox.classList.remove('hidden');
                }
            } finally {
                insightBtn.disabled = false;
                insightBtn.textContent = label;
            }
        });

        function clampTopN(v) {
            return Math.max(1, Math.min(10000, Number(v) || 10));
        }

        function runAnalyses(list, okPrefix) {
            try {
                lastResults = list.map(a => {
                    const out = window.TableStatsKit.aggregateByDimension(
                        activeTable.dataRows, a.dimIndex, a.metricIndex, a.agg, a.topN);
                    return {
                        dimName: a.dimName,
                        metricName: a.agg === 'count' ? '行数' : a.metricName,
                        agg: a.agg,
                        topN: a.topN,
                        top: out.top,
                        groupCount: out.groupCount,
                    };
                });
                renderResults();
                downloadBtn.classList.remove('hidden');
                if (insightBox) {
                    insightBox.classList.add('hidden');
                    insightBox.textContent = '';
                }
                if (resultMeta) resultMeta.textContent = `${list.length} 个维度 · 共 ${activeTable.dataRows.length} 行 · 本地统计`;
                setStatus(`${okPrefix}：${list.length} 个维度，每个取前 ${list[0] ? list[0].topN : 10} 名。`, 'success');
            } catch (error) {
                setStatus(`统计失败：${error.message}`, 'error');
            }
        }

        function buildSummary() {
            return {
                row_count: activeTable.dataRows.length,
                columns: activeTable.columns.map(c => {
                    const set = new Set();
                    const samples = [];
                    for (const row of activeTable.dataRows) {
                        const v = row[c.index];
                        if (!v) continue;
                        set.add(v);
                        if (samples.length < 5 && !samples.includes(v)) samples.push(String(v).slice(0, 40));
                    }
                    return {name: c.name, kind: c.kind, unique_count: set.size, non_empty: c.filled, samples};
                }),
            };
        }

        function mapAnalyses(analyses) {
            const byName = new Map(activeTable.columns.map(c => [c.name, c]));
            const out = [];
            const seen = new Set();
            for (const a of analyses) {
                const dim = byName.get(String(a.dimension || ''));
                if (!dim || seen.has(dim.index)) continue;
                const agg = ['sum', 'count', 'avg', 'distinct'].includes(a.agg) ? a.agg : 'sum';
                const metricCol = agg === 'count' ? null : byName.get(String(a.metric || ''));
                if (agg !== 'count' && !metricCol) continue;
                seen.add(dim.index);
                out.push({
                    dimIndex: dim.index, dimName: dim.name,
                    metricIndex: metricCol ? metricCol.index : 0,
                    metricName: metricCol ? metricCol.name : '',
                    agg, topN: clampTopN(a.top_n),
                });
            }
            return out;
        }

        function applyToControls(list) {
            const dimSet = new Set(list.map(a => a.dimIndex));
            dimList.querySelectorAll('input[data-dim]').forEach(input => {
                input.checked = dimSet.has(Number(input.dataset.dim));
            });
            const first = list[0];
            if (first) {
                aggSelect.value = first.agg;
                if (first.metricIndex) metricSelect.value = String(first.metricIndex);
                topNInput.value = first.topN;
                syncMetricVisibility();
            }
        }

        downloadBtn?.addEventListener('click', () => {
            if (!lastResults || !lastResults.length) return;
            const defs = lastResults.map(res => {
                const headers = ['排名', res.dimName, `${AGG_LABELS[res.agg]}·${res.metricName}`, '占比'];
                const rows = res.top.map(t => [t.rank, t.key, t.value, window.TableStatsKit.formatShare(t.share)]);
                return {name: res.dimName, headers, rows};
            });
            const blob = window.TableStatsKit.buildMultiSheetXlsx(defs);
            const stamp = new Date().toISOString().slice(0, 16).replace(/[-T:]/g, '');
            kit.saveBlob(blob, `${lastFileBase}-统计-${stamp}.xlsx`);
        });

        clearBtn?.addEventListener('click', () => {
            workbook = null;
            activeTable = null;
            fileNameEl.textContent = '请选择一个 .xlsx 文件';
            fileMetaEl.textContent = '文件只在浏览器本地读取，不上传服务器';
            dimList.innerHTML = '<p class="merge-file-empty">请先选择表格。</p>';
            metricSelect.innerHTML = '';
            sheetSelect.innerHTML = '';
            sheetSection.classList.add('hidden');
            resetResult();
            setStatus('');
        });

        function resetResult() {
            lastResults = null;
            resultSection?.classList.add('hidden');
            downloadBtn?.classList.add('hidden');
            if (resultBody) resultBody.innerHTML = '';
            if (insightBox) {
                insightBox.classList.add('hidden');
                insightBox.textContent = '';
            }
            if (resultMeta) resultMeta.textContent = '等待处理';
            renderWarnings([]);
        }

        function renderSheetOptions() {
            if (!workbook) return;
            sheetSelect.innerHTML = workbook.sheets
                .map((s, i) => `<option value="${i}">${escapeHtml(s.name)}（${s.images ? '' : ''}${(s.maxRow || 1) - 1} 行）</option>`)
                .join('');
            sheetSection.classList.toggle('hidden', workbook.sheets.length <= 1);
        }

        function loadActiveSheet() {
            if (!workbook) return;
            const index = Number(sheetSelect.value) || 0;
            const sheet = workbook.sheets[index] || workbook.sheets[0];
            activeTable = window.TableStatsKit.readSheetTable(sheet);
            resetResult();
            renderDimensions();
            renderMetricOptions();
            syncMetricVisibility();
        }

        function renderDimensions() {
            if (!activeTable || !activeTable.columns.length) {
                dimList.innerHTML = '<p class="merge-file-empty">这个表没有读到列。</p>';
                return;
            }
            dimList.innerHTML = activeTable.columns.map(col => `
                <label class="stats-dim-item">
                    <input type="checkbox" data-dim="${col.index}" ${col.kind === 'text' ? 'checked' : ''}>
                    <span class="stats-dim-name">${escapeHtml(col.name)}</span>
                    <span class="stats-dim-kind ${col.kind}">${col.kind === 'number' ? '数值' : '分类'}</span>
                </label>
            `).join('');
        }

        function renderMetricOptions() {
            if (!activeTable) return;
            const ordered = [...activeTable.columns].sort((a, b) => (a.kind === 'number' ? 0 : 1) - (b.kind === 'number' ? 0 : 1));
            metricSelect.innerHTML = ordered.map(col =>
                `<option value="${col.index}">${escapeHtml(col.name)}${col.kind === 'number' ? '（数值）' : ''}</option>`
            ).join('');
        }

        function syncMetricVisibility() {
            const isCount = aggSelect.value === 'count';
            metricLabel.classList.toggle('hidden', isCount);
        }

        function selectedDimensions() {
            const checked = dimList.querySelectorAll('input[data-dim]:checked');
            const byIndex = new Map(activeTable.columns.map(c => [c.index, c]));
            return Array.from(checked)
                .map(input => byIndex.get(Number(input.dataset.dim)))
                .filter(Boolean);
        }

        function columnName(index) {
            const col = activeTable.columns.find(c => c.index === index);
            return col ? col.name : '';
        }

        function renderResults() {
            if (!lastResults) return;
            resultSection.classList.remove('hidden');
            resultBody.innerHTML = lastResults.map(res => {
                const head = `<h3 class="stats-block-title">按「${escapeHtml(res.dimName)}」· ${AGG_LABELS[res.agg]}${escapeHtml(res.metricName)} · Top ${res.topN}
                    <small>（共 ${res.groupCount} 个${escapeHtml(res.dimName)}）</small></h3>`;
                const rows = res.top.map(t => `
                    <tr>
                        <td>${t.rank}</td>
                        <td title="${escapeHtml(t.key)}">${escapeHtml(t.key)}</td>
                        <td class="num">${window.TableStatsKit.formatValue(t.value, res.agg)}</td>
                        <td class="num">${window.TableStatsKit.formatShare(t.share)}</td>
                    </tr>`).join('');
                return `
                    <div class="stats-block">
                        ${head}
                        <div class="tool-table-wrap">
                            <table class="stats-table">
                                <thead><tr>
                                    <th>排名</th><th>${escapeHtml(res.dimName)}</th>
                                    <th class="num">${AGG_LABELS[res.agg]}·${escapeHtml(res.metricName)}</th>
                                    <th class="num">占比</th>
                                </tr></thead>
                                <tbody>${rows || '<tr><td colspan="4">无数据</td></tr>'}</tbody>
                            </table>
                        </div>
                    </div>`;
            }).join('');
        }

        function renderWarnings(list) {
            if (!warningsBox) return;
            warningsBox.classList.toggle('hidden', !list.length);
            warningsBox.textContent = list.join('\n');
        }

        function setStatus(message, type = '') {
            if (!statusEl) return;
            statusEl.textContent = message || '';
            statusEl.classList.toggle('error', type === 'error');
            statusEl.classList.toggle('success', type === 'success');
        }
    };
})();
