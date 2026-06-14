// 「数据清洗」面板 DOM 结线 + 多 sheet xlsx 导出。
// 引擎逻辑全部在 table-tidy-local.js（纯函数）；本文件只做界面编排和计划适配。
// 纯函数部分挂在 window.TableTidyUiKit，便于 Node 无头单测。
(function () {
    'use strict';

    const TYPE_LABELS = {text: '文本', id: '编号/电话', number: '数字/金额', date: '日期', contact: '邮箱/网址'};
    const ROLE_LABELS = {summary: '合计/小计', note: '说明/页脚', repeated_header: '重复表头', separator: '分隔线', empty: '空行'};
    const CLEANER_LABELS = {
        trim: '去首尾空格', collapseSpace: '去多余空格', stripSymbols: '去特殊符号', unwrap: '去换行',
        toHalfWidth: '全角转半角', normalizeDate: '日期标准化', normalizeAmount: '金额/数字标准化',
        normalizeNumber: '数字标准化', fillDitto: '「同上」回填', cnNumeralToArabic: '中文数字转阿拉伯',
    };
    const DROP_ROLES_DEFAULT = ['empty', 'separator', 'repeated_header', 'summary', 'note'];

    function defaultCleanersFor(type) {
        if (type === 'date') return ['fillDitto', 'normalizeDate'];
        if (type === 'number') return ['fillDitto', 'normalizeAmount'];
        return ['fillDitto', 'collapseSpace'];
    }

    function clamp01(value, fallback) {
        const n = Number(value);
        if (!Number.isFinite(n)) return fallback;
        return Math.max(0, Math.min(1, n));
    }

    // 后端计划（snake_case）-> 引擎计划（camelCase）。regions 留空让引擎对每个 sheet 自检。
    function adaptAiPlan(aiPlan) {
        const input = (aiPlan && typeof aiPlan === 'object') ? aiPlan : {};
        const targetFields = (Array.isArray(input.target_fields) ? input.target_fields : [])
            .map(field => {
                const name = String(field?.name || '').trim();
                const type = TYPE_LABELS[field?.type] ? String(field.type) : 'text';
                return {
                    name,
                    type,
                    sourceHeaders: Array.isArray(field?.source_headers) && field.source_headers.length
                        ? field.source_headers.map(h => String(h))
                        : [name],
                    cleaners: Array.isArray(field?.cleaners) && field.cleaners.length
                        ? field.cleaners.map(c => String(c))
                        : defaultCleanersFor(type),
                };
            })
            .filter(field => field.name);
        if (input.fill_ditto === false) {
            targetFields.forEach(field => {
                field.cleaners = field.cleaners.filter(name => name !== 'fillDitto');
            });
        }
        const rowFilter = (input.row_filter && typeof input.row_filter === 'object') ? input.row_filter : {};
        const dropRoles = Array.isArray(rowFilter.drop_roles)
            ? rowFilter.drop_roles.map(String).filter(role => DROP_ROLES_DEFAULT.includes(role))
            : [];
        return {
            source: 'ai',
            primaryRegionIndex: Math.max(0, Number(input.primary_region_index) || 0),
            targetFields,
            rowFilter: {
                dropRoles: dropRoles.length ? dropRoles : DROP_ROLES_DEFAULT.slice(),
                minConfidence: clamp01(rowFilter.min_confidence, 0.5),
            },
            dedupe: Boolean(input.dedupe),
            notes: Array.isArray(input.notes) ? input.notes.map(String) : [],
        };
    }

    // Excel sheet 名限制：去非法字符、31 字符内、不重名。
    function sanitizeSheetName(name, fallback, used) {
        let text = String(name || '').replace(/[\\/?*\[\]:']+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 28);
        if (!text) text = fallback || 'Sheet';
        let candidate = text;
        let index = 2;
        while (used && used.has(candidate.toLowerCase())) {
            candidate = `${text.slice(0, 25)}_${index++}`;
        }
        if (used) used.add(candidate.toLowerCase());
        return candidate;
    }

    // 13 位条码等长数字保留为文本（与 table-merge-local.js 同口径）。
    function isPlainNumber(text) {
        if (!/^-?\d{1,11}(\.\d{1,6})?$/.test(text)) return false;
        if (/^0\d/.test(text)) return false;
        return true;
    }

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
            rowXml += '</row>';
            xml += rowXml;
        });
        return xml + '</sheetData></worksheet>';
    }

    // 多 sheet xlsx：sheetDefs = [{name, headers, rows}]。
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
            + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            + '<sheets>';
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

    function roleLabel(role) {
        return ROLE_LABELS[role] || role;
    }

    // ───────────────────────────── DOM 结线 ─────────────────────────────

    window.initTableTidyLocal = function initTableTidyLocal(deps) {
        const kit = window.ExcelLocalKit;
        const tidy = window.TableTidyKit;
        if (!kit || !tidy) return;

        const userApi = deps.userApi;
        const escapeHtml = deps.escapeHtml;
        const userTokenKey = deps.userTokenKey;

        const panel = document.querySelector('#tableTidyPanel');
        if (!panel) return;

        const fileInput = document.querySelector('#tidyFiles');
        const fileListEl = document.querySelector('#tidyFileList');
        const metaEl = document.querySelector('#tidyResultMeta');
        const instructionEl = document.querySelector('#tidyInstruction');
        const planBtn = document.querySelector('#tidyPlanBtn');
        const runBtn = document.querySelector('#tidyRunBtn');
        const downloadBtn = document.querySelector('#tidyDownloadBtn');
        const clearBtn = document.querySelector('#tidyClearBtn');
        const statusEl = document.querySelector('#tidyStatus');
        const warningsBox = document.querySelector('#tidyWarnings');
        const planSection = document.querySelector('#tidyPlanSection');
        const planBody = document.querySelector('#tidyPlanBody');
        const resultSection = document.querySelector('#tidyResultSection');
        const resultBody = document.querySelector('#tidyResultBody');
        const dedupeOpt = document.querySelector('#tidyDedupeOpt');

        let sourceFiles = [];
        let plans = new Map();          // key fileIndex#sheetName -> {fileName, sheetName, sheetRef, source, plan}
        let currentPlanList = [];       // 渲染顺序，供事件按下标定位
        let results = [];
        let warnings = [];

        fileInput?.addEventListener('change', async () => {
            const files = Array.from(fileInput.files || []);
            if (!files.length) return;
            setStatus('正在本地读取乱表...');
            planBtn.disabled = true;
            try {
                for (const file of files) {
                    if (sourceFiles.length >= 10) {
                        setStatus('最多支持 10 个文件。', 'error');
                        break;
                    }
                    const workbook = await kit.parseXlsxWorkbook(file, {images: false});
                    sourceFiles.push({fileName: file.name, size: file.size, sheets: workbook.sheets});
                }
                resetPlans();
                renderFileList();
                setStatus(`已本地读取 ${sourceFiles.length} 个文件，文件不会上传服务器。`, 'success');
            } catch (error) {
                setStatus(`读取失败：${error.message}`, 'error');
            } finally {
                planBtn.disabled = false;
                fileInput.value = '';
            }
        });

        planBtn?.addEventListener('click', async () => {
            if (!sourceFiles.length) {
                setStatus('请先选择至少一个乱表。', 'error');
                return;
            }
            await buildPlans();
        });

        async function buildPlans() {
            planBtn.disabled = true;
            warnings = [];
            plans = new Map();
            const sheets = listSheets();
            const token = localStorage.getItem(userTokenKey);
            const instruction = String(instructionEl?.value || '').trim();
            try {
                if (!token || typeof userApi !== 'function') {
                    sheets.forEach(item => {
                        plans.set(item.key, {...item, source: 'local-rule', plan: tidy.buildLocalPlan(item.sheetRef)});
                    });
                    warnings.push('未登录，已用本地规则按内容形态推断字段；登录后 AI 推断更准、字段名更规范。');
                } else {
                    const capped = sheets.slice(0, 10);
                    if (sheets.length > capped.length) {
                        warnings.push(`Sheet 较多，仅对前 ${capped.length} 个调用 AI，其余走本地规则。`);
                    }
                    let done = 0;
                    for (const item of capped) {
                        done++;
                        setStatus(`正在调用 AI 规划（${done}/${capped.length}）：${item.sheetName}...`);
                        try {
                            const response = await userApi('/api/excel-automation/table-tidy/plan', {
                                method: 'POST',
                                body: {instruction, summary: tidy.buildTidySummary(item.sheetRef)},
                            });
                            const adapted = adaptAiPlan(response.plan);
                            if (!adapted.targetFields.length) {
                                throw new Error('AI 没有返回有效字段');
                            }
                            (Array.isArray(response.warnings) ? response.warnings : []).forEach(w => warnings.push(w));
                            plans.set(item.key, {...item, source: response.source || 'ai', plan: adapted});
                        } catch (error) {
                            warnings.push(`「${item.sheetName}」AI 规划失败，已用本地规则：${error.message}`);
                            plans.set(item.key, {...item, source: 'local-rule', plan: tidy.buildLocalPlan(item.sheetRef)});
                        }
                    }
                    sheets.slice(capped.length).forEach(item => {
                        plans.set(item.key, {...item, source: 'local-rule', plan: tidy.buildLocalPlan(item.sheetRef)});
                    });
                }

                if (dedupeOpt) {
                    dedupeOpt.checked = [...plans.values()].some(entry => entry.plan.dedupe);
                }
                renderPlanSection();
                renderWarnings();
                const aiCount = [...plans.values()].filter(entry => entry.source !== 'local-rule').length;
                setStatus(aiCount
                    ? `AI 规划完成（${aiCount}/${plans.size} 个 sheet），请核对目标字段后点「开始整理」。`
                    : '本地规则规划完成，请核对目标字段后点「开始整理」。', 'success');
            } finally {
                planBtn.disabled = false;
            }
        }

        runBtn?.addEventListener('click', async () => {
            if (!sourceFiles.length) {
                setStatus('请先选择至少一个乱表。', 'error');
                return;
            }
            // 没规划过就自动先规划：登录时走 AI（避免直接点「开始整理」漏掉 AI 的
            // 同义字段合并），未登录自动落到本地规则并提示。
            if (!plans.size) {
                await buildPlans();
            }
            try {
                results = [];
                let kept = 0, exceptions = 0, droppedRows = 0, droppedDup = 0;
                listSheets().forEach(item => {
                    const stored = plans.get(item.key);
                    const plan = stored ? stored.plan : tidy.buildLocalPlan(item.sheetRef);
                    plan.dedupe = Boolean(dedupeOpt?.checked);
                    const result = tidy.tidySheet(item.sheetRef, plan);
                    results.push({fileName: item.fileName, sheetName: item.sheetName, result});
                    kept += result.stats.kept;
                    exceptions += result.stats.exceptions;
                    droppedRows += result.stats.droppedRows;
                    droppedDup += result.droppedDup;
                });
                renderResults();
                downloadBtn?.classList.remove('hidden');
                let message = `整理完成：保留 ${kept} 行，异常待确认 ${exceptions} 行，删除噪声 ${droppedRows} 行`;
                if (droppedDup) message += `，去重 ${droppedDup} 行`;
                setStatus(`${message}。`, 'success');
                if (metaEl) metaEl.textContent = `${kept} 行干净数据 · ${exceptions} 行待确认 · 本地整理`;
            } catch (error) {
                setStatus(`整理失败：${error.message}`, 'error');
            }
        });

        downloadBtn?.addEventListener('click', () => {
            if (!results.length) return;
            const defs = [];
            results.forEach(({sheetName, result}) => {
                if (!result.rows.length) return;
                defs.push({
                    name: results.length === 1 ? '整理结果' : `干净-${sheetName}`,
                    headers: result.headers,
                    rows: result.rows,
                });
            });

            const excRows = [];
            results.forEach(({fileName, sheetName, result}) => {
                result.exceptions.forEach(ex => {
                    excRows.push([fileName, sheetName, String(ex._row), String(ex._confidence), ex._reason,
                        joinRecord(result.headers, ex.values)]);
                });
            });
            if (excRows.length) {
                defs.push({name: '异常待确认', headers: ['来源文件', 'Sheet', '行号', '置信度', '原因', '内容'], rows: excRows});
            }

            const dropRows = [];
            results.forEach(({fileName, result}) => {
                result.dropped.forEach(d => {
                    dropRows.push([fileName, d.sheet, String(d.row), roleLabel(d.role), d.reason, d.preview]);
                });
            });
            if (dropRows.length) {
                defs.push({name: '被删行记录', headers: ['来源文件', 'Sheet', '行号', '类型', '原因', '内容预览'], rows: dropRows});
            }

            const mapRows = [];
            results.forEach(({fileName, sheetName, result}) => {
                result.fieldMap.forEach(f => {
                    mapRows.push([fileName, sheetName, f.name, TYPE_LABELS[f.type] || f.type, (f.sourceHeaders || []).join(' / ')]);
                });
            });
            defs.push({name: '字段映射', headers: ['来源文件', 'Sheet', '目标字段', '类型', '来源表头'], rows: mapRows});

            const logRows = [];
            results.forEach(({fileName, sheetName, result}) => {
                [...(result.notes || []), ...result.log].forEach(line => logRows.push([fileName, sheetName, line]));
            });
            defs.push({name: '处理日志', headers: ['来源文件', 'Sheet', '日志'], rows: logRows});

            const blob = buildMultiSheetXlsx(defs);
            const stamp = new Date().toISOString().slice(0, 16).replace(/[-T:]/g, '');
            kit.saveBlob(blob, `数据清洗-${stamp}.xlsx`);
        });

        clearBtn?.addEventListener('click', () => {
            sourceFiles = [];
            resetPlans();
            renderFileList();
            setStatus('');
            if (metaEl) metaEl.textContent = '等待处理';
        });

        function listSheets() {
            const out = [];
            sourceFiles.forEach((file, fileIndex) => {
                file.sheets.forEach(sheet => {
                    out.push({key: `${fileIndex}#${sheet.name}`, fileName: file.fileName, sheetName: sheet.name, sheetRef: sheet});
                });
            });
            return out;
        }

        function resetPlans() {
            plans = new Map();
            currentPlanList = [];
            warnings = [];
            planSection?.classList.add('hidden');
            if (planBody) planBody.innerHTML = '';
            renderWarnings();
            resetResults();
        }

        function resetResults() {
            results = [];
            resultSection?.classList.add('hidden');
            if (resultBody) resultBody.innerHTML = '';
            downloadBtn?.classList.add('hidden');
        }

        function renderFileList() {
            if (!fileListEl) return;
            const items = sourceFiles.map((file, index) => `
                <div class="merge-file-item">
                    <span class="merge-file-name">${escapeHtml(file.fileName)}</span>
                    <span class="merge-file-meta">${file.sheets.length} 个 sheet · ${kit.formatBytes(file.size)}</span>
                    <button class="excel-text-btn" type="button" data-tidy-remove-file="${index}">移除</button>
                </div>
            `);
            fileListEl.innerHTML = items.join('') || '<p class="merge-file-empty">还没有选择文件。可多选，支持多个 sheet。</p>';
            fileListEl.querySelectorAll('[data-tidy-remove-file]').forEach(btn => {
                btn.addEventListener('click', () => {
                    sourceFiles.splice(Number(btn.dataset.tidyRemoveFile), 1);
                    resetPlans();
                    renderFileList();
                });
            });
        }

        function typeOptions(selected) {
            return Object.entries(TYPE_LABELS).map(([value, label]) =>
                `<option value="${value}" ${value === selected ? 'selected' : ''}>${label}</option>`).join('');
        }

        function cleanerText(cleaners) {
            return (cleaners || []).map(name => CLEANER_LABELS[name] || name).join('、');
        }

        function renderPlanSection() {
            if (!planSection || !planBody) return;
            currentPlanList = [...plans.values()];
            if (!currentPlanList.length) {
                planSection.classList.add('hidden');
                planBody.innerHTML = '';
                return;
            }
            planSection.classList.remove('hidden');

            planBody.innerHTML = currentPlanList.map((entry, ei) => {
                const sourceText = entry.source === 'local-rule' ? '本地规则' : 'AI 规划';
                const rows = entry.plan.targetFields.map((field, fi) => `
                    <tr>
                        <td><input value="${escapeHtml(field.name)}" data-tidy-name="${ei}:${fi}"></td>
                        <td><select data-tidy-type="${ei}:${fi}">${typeOptions(field.type)}</select></td>
                        <td>${escapeHtml((field.sourceHeaders || []).join(' / '))}</td>
                        <td>${escapeHtml(cleanerText(field.cleaners))}</td>
                        <td><button type="button" class="excel-text-btn" data-tidy-field-remove="${ei}:${fi}">移除</button></td>
                    </tr>
                `).join('');
                const notes = (entry.plan.notes || []).map(n => `<p class="merge-file-meta">${escapeHtml(n)}</p>`).join('');
                return `
                    <div class="tidy-plan-block">
                        <h3>${escapeHtml(shorten(entry.fileName, 24))} · ${escapeHtml(entry.sheetName)}
                            <small>（${sourceText} · ${entry.plan.targetFields.length} 个字段）</small></h3>
                        <div class="tool-table-wrap">
                            <table>
                                <thead><tr><th>目标字段</th><th>类型</th><th>来源表头</th><th>清洗</th><th></th></tr></thead>
                                <tbody>${rows}</tbody>
                            </table>
                        </div>
                        ${notes}
                    </div>
                `;
            }).join('');

            planBody.querySelectorAll('[data-tidy-name]').forEach(input => {
                input.addEventListener('change', () => {
                    const field = fieldByRef(input.dataset.tidyName);
                    if (!field) return;
                    field.name = input.value.trim() || field.name;
                    input.value = field.name;
                    resetResults();
                });
            });
            planBody.querySelectorAll('[data-tidy-type]').forEach(select => {
                select.addEventListener('change', () => {
                    const field = fieldByRef(select.dataset.tidyType);
                    if (!field) return;
                    field.type = select.value;
                    field.cleaners = defaultCleanersFor(select.value);
                    renderPlanSection();
                    resetResults();
                });
            });
            planBody.querySelectorAll('[data-tidy-field-remove]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const [ei, fi] = btn.dataset.tidyFieldRemove.split(':').map(Number);
                    currentPlanList[ei]?.plan.targetFields.splice(fi, 1);
                    renderPlanSection();
                    resetResults();
                });
            });
        }

        function fieldByRef(ref) {
            const [ei, fi] = String(ref || '').split(':').map(Number);
            return currentPlanList[ei]?.plan.targetFields[fi] || null;
        }

        function renderResults() {
            if (!resultSection || !resultBody) return;
            if (!results.length) {
                resultSection.classList.add('hidden');
                resultBody.innerHTML = '';
                return;
            }
            resultSection.classList.remove('hidden');
            resultBody.innerHTML = results.map(({fileName, sheetName, result}) => {
                const s = result.stats;
                let html = `<div class="tidy-result-block">
                    <h3>${escapeHtml(shorten(fileName, 24))} · ${escapeHtml(sheetName)}</h3>
                    <p class="merge-file-meta">识别 ${s.regions} 个数据区域 · 保留 ${s.kept} 行 · 异常待确认 ${s.exceptions} 行 · 删除噪声 ${s.droppedRows} 行${result.droppedDup ? ` · 去重 ${result.droppedDup} 行` : ''}</p>`;

                if (result.rows.length) {
                    html += `<div class="tool-table-wrap">${tableHtml(result.headers,
                        result.rows.slice(0, 30).map(row => row.map(v => escapeHtml(shorten(v, 40)))))}</div>`;
                    if (result.rows.length > 30) {
                        html += `<p class="merge-file-meta">仅预览前 30 行，完整数据在下载的 xlsx 里。</p>`;
                    }
                } else {
                    html += `<p class="merge-file-empty">没有识别到有效数据行。</p>`;
                }

                if (result.exceptions.length) {
                    const rows = result.exceptions.slice(0, 20).map(ex => [
                        String(ex._row), String(ex._confidence), escapeHtml(ex._reason),
                        escapeHtml(shorten(joinRecord(result.headers, ex.values), 80)),
                    ]);
                    html += `<h4>⚠ 异常待确认（${result.exceptions.length} 行）</h4>
                        <div class="tool-table-wrap">${tableHtml(['行号', '置信度', '原因', '内容'], rows)}</div>`;
                }

                if (result.dropped.length) {
                    const rows = result.dropped.slice(0, 20).map(d => [
                        String(d.row), roleLabel(d.role), escapeHtml(d.reason), escapeHtml(shorten(d.preview, 60)),
                    ]);
                    html += `<h4>🗑 被删噪声行（${result.dropped.length} 行）</h4>
                        <div class="tool-table-wrap">${tableHtml(['行号', '类型', '原因', '内容预览'], rows)}</div>`;
                }

                if (result.log.length || (result.notes || []).length) {
                    html += `<p class="merge-file-meta">${escapeHtml([...(result.notes || []), ...result.log].join(' / '))}</p>`;
                }
                return html + '</div>';
            }).join('');
        }

        function tableHtml(headers, preEscapedRows) {
            const head = `<thead><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>`;
            const body = `<tbody>${preEscapedRows.map(row =>
                `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody>`;
            return `<table>${head}${body}</table>`;
        }

        function joinRecord(headers, values) {
            return headers.map((h, i) => values[i] ? `${h}:${values[i]}` : '').filter(Boolean).join(' | ');
        }

        function renderWarnings() {
            if (!warningsBox) return;
            warningsBox.classList.toggle('hidden', !warnings.length);
            warningsBox.textContent = warnings.join('\n');
        }

        function setStatus(message, type = '') {
            if (!statusEl) return;
            statusEl.textContent = message || '';
            statusEl.classList.toggle('error', type === 'error');
            statusEl.classList.toggle('success', type === 'success');
        }

        function shorten(text, max) {
            const value = String(text || '');
            return value.length > max ? `${value.slice(0, max)}…` : value;
        }
    };

    const TableTidyUiKit = {adaptAiPlan, sanitizeSheetName, buildMultiSheetXlsx, isPlainNumber, roleLabel, defaultCleanersFor};
    if (typeof module !== 'undefined' && module.exports) module.exports = TableTidyUiKit;
    if (typeof window !== 'undefined') window.TableTidyUiKit = TableTidyUiKit;
})();
