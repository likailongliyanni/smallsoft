(function () {
    'use strict';

    window.initTableMergeLocal = function initTableMergeLocal(deps) {
        const kit = window.ExcelLocalKit;
        if (!kit) return;

        const userApi = deps.userApi;
        const escapeHtml = deps.escapeHtml;
        const userTokenKey = deps.userTokenKey;

        const panel = document.querySelector('#tableMergePanel');
        if (!panel) return;

        const sourceInput = document.querySelector('#mergeSourceFiles');
        const templateInput = document.querySelector('#mergeTemplateFile');
        const fileListEl = document.querySelector('#mergeFileList');
        const instructionEl = document.querySelector('#mergeInstruction');
        const classifyBtn = document.querySelector('#mergeClassifyBtn');
        const mergeBtn = document.querySelector('#mergeRunBtn');
        const downloadBtn = document.querySelector('#mergeDownloadBtn');
        const clearBtn = document.querySelector('#mergeClearBtn');
        const statusEl = document.querySelector('#mergeStatus');
        const metaEl = document.querySelector('#mergeResultMeta');
        const warningsBox = document.querySelector('#mergeWarnings');
        const mappingSection = document.querySelector('#mergeMappingSection');
        const fieldChipsEl = document.querySelector('#mergeFieldChips');
        const mappingBody = document.querySelector('#mergeMappingBody');
        const addFieldBtn = document.querySelector('#mergeAddFieldBtn');
        const previewSection = document.querySelector('#mergePreviewSection');
        const previewTable = document.querySelector('#mergePreviewTable');
        const sourceColumnsOpt = document.querySelector('#mergeSourceColumnsOpt');
        const dedupeOpt = document.querySelector('#mergeDedupeOpt');

        let sourceFiles = [];
        let templateFile = null;
        let mapping = null;
        let mergedResult = null;
        let fieldIdSeq = 1;

        initPanelSwitching();

        sourceInput?.addEventListener('change', async () => {
            const files = Array.from(sourceInput.files || []);
            if (!files.length) return;
            setStatus('正在本地读取原始表...');
            classifyBtn.disabled = true;
            try {
                for (const file of files) {
                    if (sourceFiles.length >= 10) {
                        setStatus('最多支持 10 个原始表。', 'error');
                        break;
                    }
                    const workbook = await kit.parseXlsxWorkbook(file, {images: false});
                    sourceFiles.push({fileName: file.name, size: file.size, sheets: workbook.sheets});
                }
                resetPlanState();
                renderFileList();
                setStatus(`已本地读取 ${sourceFiles.length} 个原始表，文件不会上传服务器。`, 'success');
            } catch (error) {
                setStatus(`读取失败：${error.message}`, 'error');
            } finally {
                classifyBtn.disabled = false;
                sourceInput.value = '';
            }
        });

        templateInput?.addEventListener('change', async () => {
            const file = templateInput.files?.[0];
            if (!file) return;
            setStatus('正在本地读取模板表...');
            try {
                const workbook = await kit.parseXlsxWorkbook(file, {images: false});
                const sheet = workbook.sheets[0];
                const fields = [];
                for (let col = 1; col <= sheet.maxCol; col++) {
                    const value = String(sheet.rows.get(sheet.headerRow)?.get(col) || '').trim();
                    if (value) fields.push(value);
                }
                if (!fields.length) {
                    throw new Error('模板表第一个 sheet 没有读取到表头。');
                }
                templateFile = {fileName: file.name, fields};
                resetPlanState();
                renderFileList();
                setStatus(`已读取模板：${fields.length} 个字段。`, 'success');
            } catch (error) {
                templateFile = null;
                setStatus(`模板读取失败：${error.message}`, 'error');
            } finally {
                templateInput.value = '';
            }
        });

        classifyBtn?.addEventListener('click', async () => {
            if (!sourceFiles.length) {
                setStatus('请先选择至少一个原始表。', 'error');
                return;
            }
            classifyBtn.disabled = true;
            setStatus(localStorage.getItem(userTokenKey)
                ? '正在调用 AI 归类字段...'
                : '未登录，使用本地规则归类字段...');
            try {
                const planResult = await resolvePlan();
                mapping = mappingFromPlan(planResult.plan);
                renderWarnings(planResult.warnings || []);
                renderMapping();
                const sourceText = planResult.source === 'ai' ? 'AI' : '本地规则';
                setStatus(`${sourceText}归类完成，请核对下面的字段归类，确认后点「开始合并」。`, 'success');
            } catch (error) {
                setStatus(`字段归类失败：${error.message}`, 'error');
            } finally {
                classifyBtn.disabled = false;
            }
        });

        addFieldBtn?.addEventListener('click', () => {
            if (!mapping) return;
            mapping.targetFields.push({id: `f${fieldIdSeq++}`, name: `新字段${mapping.targetFields.length + 1}`});
            renderMapping();
        });

        mergeBtn?.addEventListener('click', () => {
            if (!mapping) {
                setStatus('请先进行字段归类。', 'error');
                return;
            }
            try {
                mergedResult = mergeTables();
                renderPreview(mergedResult);
                downloadBtn?.classList.remove('hidden');
                setStatus(`合并完成：${mergedResult.rows.length} 行数据，来自 ${mergedResult.sheetCount} 个 sheet${mergedResult.dropped ? `，去重移除 ${mergedResult.dropped} 行` : ''}。`, 'success');
                if (metaEl) metaEl.textContent = `${mergedResult.rows.length} 行 · ${mergedResult.headers.length} 列 · 本地合并`;
            } catch (error) {
                setStatus(`合并失败：${error.message}`, 'error');
            }
        });

        downloadBtn?.addEventListener('click', () => {
            if (!mergedResult) return;
            const blob = buildXlsxBlob('整理结果', mergedResult.headers, mergedResult.rows);
            const stamp = new Date().toISOString().slice(0, 16).replace(/[-T:]/g, '');
            kit.saveBlob(blob, `整理结果-${stamp}.xlsx`);
        });

        clearBtn?.addEventListener('click', () => {
            sourceFiles = [];
            templateFile = null;
            resetPlanState();
            renderFileList();
            setStatus('');
            if (metaEl) metaEl.textContent = '等待处理';
        });

        function resetPlanState() {
            mapping = null;
            mergedResult = null;
            mappingSection?.classList.add('hidden');
            previewSection?.classList.add('hidden');
            downloadBtn?.classList.add('hidden');
            renderWarnings([]);
        }

        function renderFileList() {
            if (!fileListEl) return;
            const items = sourceFiles.map((file, index) => `
                <div class="merge-file-item">
                    <span class="merge-file-name">${escapeHtml(file.fileName)}</span>
                    <span class="merge-file-meta">${file.sheets.length} 个 sheet · ${kit.formatBytes(file.size)}</span>
                    <button class="excel-text-btn" type="button" data-remove-file="${index}">移除</button>
                </div>
            `);
            if (templateFile) {
                items.push(`
                    <div class="merge-file-item template">
                        <span class="merge-file-name">模板：${escapeHtml(templateFile.fileName)}</span>
                        <span class="merge-file-meta">${templateFile.fields.length} 个字段</span>
                        <button class="excel-text-btn" type="button" data-remove-template="1">移除</button>
                    </div>
                `);
            }
            fileListEl.innerHTML = items.join('') || '<p class="merge-file-empty">还没有选择文件。原始表可多选，支持多个 sheet。</p>';

            fileListEl.querySelectorAll('[data-remove-file]').forEach(btn => {
                btn.addEventListener('click', () => {
                    sourceFiles.splice(Number(btn.dataset.removeFile), 1);
                    resetPlanState();
                    renderFileList();
                });
            });
            fileListEl.querySelector('[data-remove-template]')?.addEventListener('click', () => {
                templateFile = null;
                resetPlanState();
                renderFileList();
            });
        }

        function listSourceColumns() {
            const columns = [];
            sourceFiles.forEach((file, fileIndex) => {
                file.sheets.forEach(sheet => {
                    const maxCol = Math.min(sheet.maxCol || 0, 60);
                    for (let col = 1; col <= maxCol; col++) {
                        const header = String(sheet.rows.get(sheet.headerRow)?.get(col) || '').trim();
                        const samples = [];
                        for (let row = sheet.headerRow + 1; row <= sheet.maxRow && samples.length < 5; row++) {
                            const value = String(sheet.rows.get(row)?.get(col) || '').trim();
                            if (value) samples.push(value);
                        }
                        if (!header && !samples.length) continue;
                        columns.push({
                            fileIndex,
                            fileName: file.fileName,
                            sheet: sheet.name,
                            sheetRef: sheet,
                            column: kit.columnLetters(col),
                            colNumber: col,
                            header: header || kit.columnLetters(col),
                            samples,
                        });
                    }
                });
            });
            return columns;
        }

        function buildSummary() {
            const summary = {
                files: sourceFiles.map(file => ({
                    file_name: file.fileName,
                    sheets: file.sheets.slice(0, 30).map(sheet => {
                        const maxCol = Math.min(sheet.maxCol || 0, 60);
                        const columns = [];
                        for (let col = 1; col <= maxCol; col++) {
                            const header = String(sheet.rows.get(sheet.headerRow)?.get(col) || '').trim();
                            const samples = [];
                            for (let row = sheet.headerRow + 1; row <= sheet.maxRow && samples.length < 5; row++) {
                                const value = String(sheet.rows.get(row)?.get(col) || '').trim();
                                if (value) samples.push(value.slice(0, 60));
                            }
                            if (!header && !samples.length) continue;
                            columns.push({column: kit.columnLetters(col), header, samples});
                        }
                        return {
                            name: sheet.name,
                            header_row: sheet.headerRow,
                            max_row: sheet.maxRow,
                            columns,
                        };
                    }),
                })),
            };
            if (templateFile) {
                summary.template = {file_name: templateFile.fileName, fields: templateFile.fields};
            }
            return summary;
        }

        async function resolvePlan() {
            const localPlan = makeLocalPlan();
            const token = localStorage.getItem(userTokenKey);

            if (!token || typeof userApi !== 'function') {
                return {
                    source: 'local-rule',
                    plan: localPlan,
                    warnings: ['未登录，已使用本地规则归类；登录后 AI 能更好地识别不规范表头。'],
                };
            }

            try {
                const response = await userApi('/api/excel-automation/table-merge/plan', {
                    method: 'POST',
                    body: {
                        instruction: String(instructionEl?.value || '').trim(),
                        summary: buildSummary(),
                    },
                });
                const plan = response.plan;
                if (!plan || !Array.isArray(plan.target_fields) || !plan.target_fields.length) {
                    throw new Error('AI 没有返回有效的字段归类。');
                }
                return {
                    source: response.source || 'ai',
                    plan,
                    warnings: Array.isArray(response.warnings) ? response.warnings : [],
                };
            } catch (error) {
                return {
                    source: 'local-rule',
                    plan: localPlan,
                    warnings: [`AI 字段归类失败，已使用本地规则：${error.message}`],
                };
            }
        }

        const aliasGroups = [
            ['商品名称', '品名', '名称', '商品名', '产品名称', '货品名称', 'title', 'name', 'product name'],
            ['69码', '69 码', '条码', '条形码', '商品条码', '国际条码', 'ean', 'barcode', 'bar code', 'upc'],
            ['商品编码', '货号', '款号', '编码', '编号', '商品编号', 'sku', 'item', 'code', 'item no'],
            ['颜色', '色号', 'color', 'colour'],
            ['尺码', '尺寸', 'size'],
            ['品牌', 'brand'],
            ['分类', '类目', 'category'],
            ['数量', 'qty', 'quantity'],
            ['单价', 'unit price'],
            ['金额', '总价', '合计', 'amount', 'total'],
            ['单位', 'unit'],
            ['规格', 'spec', '规格型号'],
            ['备注', '说明', 'remark', 'remarks', 'note', 'notes'],
            ['供应商', '供货商', '厂家', 'supplier', 'vendor'],
            ['日期', '时间', 'date'],
        ];

        function normalizeHeader(text) {
            return String(text || '').toLowerCase().replace(/[\s_：:\-（）()/\\.]+/gu, '');
        }

        function groupKey(header) {
            const normalized = normalizeHeader(header);
            if (!normalized) return '';
            for (let i = 0; i < aliasGroups.length; i++) {
                if (aliasGroups[i].some(alias => normalizeHeader(alias) === normalized)) {
                    return `group:${i}`;
                }
            }
            return `header:${normalized}`;
        }

        function makeLocalPlan() {
            const columns = listSourceColumns();

            if (templateFile) {
                const targets = templateFile.fields.map(field => ({
                    name: field,
                    sources: columns
                        .filter(col => groupKey(field) && groupKey(field) === groupKey(col.header))
                        .map(col => ({file_index: col.fileIndex, sheet: col.sheet, column: col.column})),
                }));
                return {target_fields: targets, notes: ['本地规则按模板字段名匹配，请人工核对未匹配的列。']};
            }

            const groups = new Map();
            columns.forEach(col => {
                const key = groupKey(col.header);
                if (!key) return;
                if (!groups.has(key)) groups.set(key, {headers: [], sources: []});
                groups.get(key).headers.push(col.header);
                groups.get(key).sources.push({file_index: col.fileIndex, sheet: col.sheet, column: col.column});
            });

            const targets = [];
            groups.forEach((group, key) => {
                let name = group.headers[0];
                if (key.startsWith('group:')) {
                    name = aliasGroups[Number(key.slice(6))][0];
                }
                targets.push({name, sources: group.sources});
            });

            return {target_fields: targets, notes: ['本地规则按表头同义词归类，请人工核对。']};
        }

        function mappingFromPlan(plan) {
            const targetFields = [];
            const assign = new Map();

            (plan.target_fields || []).forEach(target => {
                const id = `f${fieldIdSeq++}`;
                targetFields.push({id, name: String(target.name || '').trim() || `字段${targetFields.length + 1}`});
                (target.sources || []).forEach(source => {
                    const key = columnKey(source.file_index, source.sheet, source.column);
                    if (!assign.has(key)) assign.set(key, id);
                });
            });

            return {targetFields, assign, notes: plan.notes || []};
        }

        function columnKey(fileIndex, sheet, column) {
            return `${fileIndex}#${sheet}#${String(column).toUpperCase()}`;
        }

        function renderMapping() {
            if (!mapping || !mappingBody || !fieldChipsEl) return;
            mappingSection?.classList.remove('hidden');
            previewSection?.classList.add('hidden');
            downloadBtn?.classList.add('hidden');
            mergedResult = null;

            fieldChipsEl.innerHTML = mapping.targetFields.map(field => `
                <span class="merge-field-chip" data-field-id="${field.id}">
                    <input value="${escapeHtml(field.name)}" data-field-input="${field.id}">
                    <button type="button" title="删除字段" data-field-remove="${field.id}">×</button>
                </span>
            `).join('');

            fieldChipsEl.querySelectorAll('[data-field-input]').forEach(input => {
                input.addEventListener('change', () => {
                    const field = mapping.targetFields.find(f => f.id === input.dataset.fieldInput);
                    if (field) {
                        field.name = input.value.trim() || field.name;
                        input.value = field.name;
                        renderMapping();
                    }
                });
            });
            fieldChipsEl.querySelectorAll('[data-field-remove]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const id = btn.dataset.fieldRemove;
                    mapping.targetFields = mapping.targetFields.filter(f => f.id !== id);
                    mapping.assign.forEach((value, key) => {
                        if (value === id) mapping.assign.set(key, null);
                    });
                    renderMapping();
                });
            });

            const columns = listSourceColumns();
            mappingBody.innerHTML = columns.map(col => {
                const key = columnKey(col.fileIndex, col.sheet, col.column);
                const assigned = mapping.assign.get(key) ?? null;
                const options = [
                    `<option value="">— 忽略此列 —</option>`,
                    ...mapping.targetFields.map(field =>
                        `<option value="${field.id}" ${assigned === field.id ? 'selected' : ''}>${escapeHtml(field.name)}</option>`),
                ].join('');
                return `
                    <tr class="${assigned ? '' : 'merge-row-ignored'}">
                        <td title="${escapeHtml(col.fileName)}">${escapeHtml(shorten(col.fileName, 18))}</td>
                        <td>${escapeHtml(col.sheet)}</td>
                        <td>${escapeHtml(col.column)}</td>
                        <td>${escapeHtml(col.header)}</td>
                        <td class="merge-samples" title="${escapeHtml(col.samples.join(' / '))}">${escapeHtml(shorten(col.samples.slice(0, 2).join(' / '), 30))}</td>
                        <td><select data-assign-key="${escapeHtml(key)}">${options}</select></td>
                    </tr>
                `;
            }).join('');

            mappingBody.querySelectorAll('[data-assign-key]').forEach(select => {
                select.addEventListener('change', () => {
                    mapping.assign.set(select.dataset.assignKey, select.value || null);
                    select.closest('tr')?.classList.toggle('merge-row-ignored', !select.value);
                });
            });
        }

        function mergeTables() {
            const includeSource = Boolean(sourceColumnsOpt?.checked);
            const dedupe = Boolean(dedupeOpt?.checked);
            const fields = mapping.targetFields;
            if (!fields.length) {
                throw new Error('没有目标字段，请至少保留一个字段。');
            }

            const headers = fields.map(f => f.name);
            if (includeSource) headers.push('来源文件', '来源Sheet');

            const rows = [];
            const seen = new Set();
            let dropped = 0;
            let sheetCount = 0;

            sourceFiles.forEach((file, fileIndex) => {
                file.sheets.forEach(sheet => {
                    const fieldColumns = fields.map(field => {
                        const cols = [];
                        const maxCol = Math.min(sheet.maxCol || 0, 60);
                        for (let col = 1; col <= maxCol; col++) {
                            const key = columnKey(fileIndex, sheet.name, kit.columnLetters(col));
                            if (mapping.assign.get(key) === field.id) cols.push(col);
                        }
                        return cols;
                    });

                    if (!fieldColumns.some(cols => cols.length)) return;
                    sheetCount++;

                    for (let row = sheet.headerRow + 1; row <= sheet.maxRow; row++) {
                        const cells = sheet.rows.get(row);
                        if (!kit.hasAnyValue(cells)) continue;

                        const values = fieldColumns.map(cols => {
                            for (const col of cols) {
                                const value = String(cells?.get(col) || '').trim();
                                if (value) return value;
                            }
                            return '';
                        });

                        if (values.every(value => value === '')) continue;

                        if (dedupe) {
                            const dedupeKey = values.join('\u0001');
                            if (seen.has(dedupeKey)) {
                                dropped++;
                                continue;
                            }
                            seen.add(dedupeKey);
                        }

                        if (includeSource) values.push(file.fileName, sheet.name);
                        rows.push(values);
                    }
                });
            });

            if (!rows.length) {
                throw new Error('没有合并出任何数据行，请检查字段归类。');
            }

            return {headers, rows, sheetCount, dropped};
        }

        function renderPreview(result) {
            if (!previewSection || !previewTable) return;
            previewSection.classList.remove('hidden');
            const head = `<thead><tr>${result.headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>`;
            const body = `<tbody>${result.rows.slice(0, 50).map(row =>
                `<tr>${row.map(value => `<td title="${escapeHtml(value)}">${escapeHtml(shorten(value, 40))}</td>`).join('')}</tr>`,
            ).join('')}</tbody>`;
            previewTable.innerHTML = head + body;
        }

        function renderWarnings(warnings) {
            if (!warningsBox) return;
            const notes = mapping?.notes || [];
            const all = [...warnings, ...notes];
            warningsBox.classList.toggle('hidden', !all.length);
            warningsBox.textContent = all.join('\n');
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

        function initPanelSwitching() {
            const navItems = document.querySelectorAll('.excel-nav-item[data-panel]');
            const panels = {
                'image-extract': document.querySelector('#sheetExportForm'),
                'table-merge': panel,
            };
            navItems.forEach(item => {
                item.addEventListener('click', () => {
                    navItems.forEach(other => other.classList.toggle('active', other === item));
                    Object.entries(panels).forEach(([name, el]) => {
                        el?.classList.toggle('hidden', name !== item.dataset.panel);
                    });
                });
            });
        }
    };

    function buildXlsxBlob(sheetName, headers, rows) {
        const kit = window.ExcelLocalKit;
        const allRows = [headers, ...rows];
        const colCount = headers.length;

        let sheetXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + `<dimension ref="A1:${colLetters(colCount)}${allRows.length}"/>`
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
            sheetXml += rowXml;
        });

        sheetXml += '</sheetData></worksheet>';

        const contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            + '<Default Extension="xml" ContentType="application/xml"/>'
            + '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            + '</Types>';

        const rootRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            + '</Relationships>';

        const workbookXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            + `<sheets><sheet name="${escapeXml(sheetName)}" sheetId="1" r:id="rId1"/></sheets>`
            + '</workbook>';

        const workbookRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            + '</Relationships>';

        const blob = kit.createStoredZip([
            {name: '[Content_Types].xml', bytes: kit.utf8Bytes(contentTypes)},
            {name: '_rels/.rels', bytes: kit.utf8Bytes(rootRels)},
            {name: 'xl/workbook.xml', bytes: kit.utf8Bytes(workbookXml)},
            {name: 'xl/_rels/workbook.xml.rels', bytes: kit.utf8Bytes(workbookRels)},
            {name: 'xl/worksheets/sheet1.xml', bytes: kit.utf8Bytes(sheetXml)},
        ]);

        return new Blob([blob], {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
    }

    // 13 位条码等长数字保留为文本，避免 Excel 显示成科学计数法或丢失前导零。
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

    window.TableMergeKit = {buildXlsxBlob};
})();
