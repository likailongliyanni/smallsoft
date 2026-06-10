(function () {
    'use strict';

    window.initSpreadsheetImagesLocal = function initSpreadsheetImagesLocal(deps) {
        const userApi = deps.userApi;
        const formToObject = deps.formToObject;
        const escapeHtml = deps.escapeHtml;
        const userTokenKey = deps.userTokenKey;

        const loginPanel = document.querySelector('#sheetLoginPanel');
        const loginForm = document.querySelector('#sheetLoginForm');
        const registerBtn = document.querySelector('#sheetRegisterBtn');
        const loginResult = document.querySelector('#sheetLoginResult');
        const logoutBtn = document.querySelector('#sheetLogoutBtn');
        const userBadge = document.querySelector('#sheetUserBadge');
        const exportForm = document.querySelector('#sheetExportForm');
        const exportBtn = document.querySelector('#sheetExportBtn');
        const clearBtn = document.querySelector('#sheetClearBtn');
        const exportResult = document.querySelector('#sheetExportResult');
        const resultMeta = document.querySelector('#sheetResultMeta');
        const downloadBtn = document.querySelector('#sheetDownloadBtn');
        const planBox = document.querySelector('#sheetPlanBox');
        const warningsBox = document.querySelector('#sheetWarnings');
        const previewWrap = document.querySelector('#sheetPreviewWrap');
        const previewBody = document.querySelector('#sheetPreviewBody');
        const fileInput = document.querySelector('#sheetFile');
        const fileNameEl = document.querySelector('#sheetFileName');
        const fileSizeEl = document.querySelector('#sheetFileSize');
        const localPreview = document.querySelector('#sheetLocalPreview');
        const sheetTabs = document.querySelector('#sheetTabs');
        const gridPreview = document.querySelector('#sheetGridPreview');
        const imagePreview = document.querySelector('#sheetImagePreview');

        let workbook = null;
        let activeSheetIndex = 0;
        let exportBlob = null;
        let exportName = 'excel-images.zip';

        syncUserState();
        renderExportResult(null);

        loginForm?.addEventListener('submit', async (event) => {
            event.preventDefault();
            await loginOrRegister('/api/auth/login');
        });

        registerBtn?.addEventListener('click', async () => {
            await loginOrRegister('/api/auth/register');
        });

        logoutBtn?.addEventListener('click', () => {
            localStorage.removeItem(userTokenKey);
            syncUserState();
            setResult(loginResult, '已退出');
        });

        fileInput?.addEventListener('change', async () => {
            const file = fileInput.files?.[0];
            revokePreviewUrls();
            workbook = null;
            exportBlob = null;
            renderExportResult(null);
            if (!file) {
                updateFileInfo(null);
                renderWorkbookPreview(null);
                return;
            }

            updateFileInfo(file);
            exportBtn.disabled = true;
            setResult(exportResult, '正在本地读取表格...');
            try {
                workbook = await parseXlsxWorkbook(file);
                activeSheetIndex = 0;
                renderWorkbookPreview(workbook);
                const imageCount = workbook.sheets.reduce((sum, sheet) => sum + sheet.images.length, 0);
                setResult(exportResult, `已本地读取：${workbook.sheets.length} 个 sheet，${imageCount} 张图片`, 'success');
            } catch (error) {
                workbook = null;
                renderWorkbookPreview(null);
                setResult(exportResult, error.message, 'error');
            } finally {
                exportBtn.disabled = false;
            }
        });

        clearBtn?.addEventListener('click', () => {
            exportForm?.reset();
            updateFileInfo(null);
            revokePreviewUrls();
            workbook = null;
            exportBlob = null;
            renderWorkbookPreview(null);
            renderExportResult(null);
            setResult(exportResult, '');
        });

        exportForm?.addEventListener('submit', async (event) => {
            event.preventDefault();
            if (!workbook) {
                setResult(exportResult, '请先选择一个 xlsx 表格。', 'error');
                return;
            }

            const instruction = String(document.querySelector('#sheetInstruction')?.value || '').trim();
            if (!instruction) {
                setResult(exportResult, '请填写整理要求。', 'error');
                return;
            }

            exportBtn.disabled = true;
            downloadBtn?.classList.add('hidden');
            setResult(exportResult, localStorage.getItem(userTokenKey)
                ? '正在生成 AI 规则并在本地整理图片...'
                : '正在本地整理图片...');
            try {
                const result = await exportImagesLocally(workbook, instruction, {userApi, userTokenKey});
                exportBlob = result.blob;
                exportName = result.fileName;
                renderExportResult(result);
                const sourceText = result.plan_source === 'ai' ? 'AI 规则' : '本地规则';
                setResult(exportResult, `${sourceText}整理完成：${result.images_count} 张图片`, 'success');
            } catch (error) {
                renderExportResult(null);
                setResult(exportResult, error.message, 'error');
            } finally {
                exportBtn.disabled = false;
            }
        });

        downloadBtn?.addEventListener('click', () => {
            if (!exportBlob) return;
            saveBlob(exportBlob, exportName);
        });

        async function loginOrRegister(path) {
            const data = formToObject(loginForm);
            data.username = String(data.username || '').trim();
            data.password = String(data.password || '');
            if (!data.username || !data.password) {
                setResult(loginResult, '请填写用户名和密码', 'error');
                return;
            }
            if (path.includes('/register') && data.password.length < 6) {
                setResult(loginResult, '注册密码至少 6 位', 'error');
                return;
            }
            setResult(loginResult, '处理中...');
            try {
                const response = await userApi(path, {method: 'POST', body: data});
                localStorage.setItem(userTokenKey, response.token);
                syncUserState(response.user);
                setResult(loginResult, '已登录', 'success');
            } catch (error) {
                setResult(loginResult, error.message, 'error');
            }
        }

        async function syncUserState(user = null) {
            const token = localStorage.getItem(userTokenKey);
            if (!token) {
                loginPanel?.classList.remove('hidden');
                logoutBtn?.classList.add('hidden');
                if (userBadge) userBadge.textContent = '本地处理';
                return;
            }

            try {
                if (!user) {
                    const response = await userApi('/api/me');
                    user = response.user;
                }
                loginPanel?.classList.add('hidden');
                logoutBtn?.classList.remove('hidden');
                if (userBadge) {
                    userBadge.textContent = `${user.username} · ${user.available_generations ?? 0} 次`;
                }
            } catch (error) {
                localStorage.removeItem(userTokenKey);
                loginPanel?.classList.remove('hidden');
                logoutBtn?.classList.add('hidden');
                if (userBadge) userBadge.textContent = '本地处理';
            }
        }

        function renderWorkbookPreview(book) {
            if (!book) {
                localPreview?.classList.add('hidden');
                if (sheetTabs) sheetTabs.innerHTML = '';
                if (gridPreview) gridPreview.innerHTML = '';
                if (imagePreview) imagePreview.innerHTML = '';
                if (resultMeta) resultMeta.textContent = '等待处理';
                return;
            }

            localPreview?.classList.remove('hidden');
            if (resultMeta) {
                const imageCount = book.sheets.reduce((sum, sheet) => sum + sheet.images.length, 0);
                resultMeta.textContent = `${book.sheets.length} 个 sheet · ${imageCount} 张图片 · 本地预览`;
            }

            if (sheetTabs) {
                sheetTabs.innerHTML = book.sheets.map((sheet, index) => `
                    <button class="sheet-tab ${index === activeSheetIndex ? 'active' : ''}" type="button" data-sheet-index="${index}">
                        ${escapeHtml(sheet.name)} (${sheet.images.length})
                    </button>
                `).join('');
                sheetTabs.querySelectorAll('.sheet-tab').forEach((button) => {
                    button.addEventListener('click', () => {
                        activeSheetIndex = Number(button.dataset.sheetIndex) || 0;
                        renderWorkbookPreview(book);
                    });
                });
            }

            const sheet = book.sheets[activeSheetIndex] || book.sheets[0];
            renderSheetGrid(sheet);
            renderSheetImages(sheet);
        }

        function renderSheetGrid(sheet) {
            if (!gridPreview || !sheet) return;

            const maxRow = Math.min(sheet.maxRow || 20, 40);
            const maxCol = Math.min(sheet.maxCol || 10, 12);
            let html = '<thead><tr><th class="row-head"></th>';
            for (let col = 1; col <= maxCol; col++) {
                html += `<th>${columnLetters(col)}</th>`;
            }
            html += '</tr></thead><tbody>';

            for (let row = 1; row <= maxRow; row++) {
                html += `<tr><th class="row-head">${row}</th>`;
                for (let col = 1; col <= maxCol; col++) {
                    const value = sheet.rows.get(row)?.get(col) || '';
                    html += `<td title="${escapeHtml(value)}">${escapeHtml(value)}</td>`;
                }
                html += '</tr>';
            }

            html += '</tbody>';
            gridPreview.innerHTML = html;
        }

        function renderSheetImages(sheet) {
            if (!imagePreview || !sheet) return;

            if (sheet.images.length === 0) {
                imagePreview.innerHTML = '<div class="sheet-image-card"><span>当前 sheet 没有内嵌图片</span></div>';
                return;
            }

            imagePreview.innerHTML = sheet.images.slice(0, 80).map((image, index) => `
                <div class="sheet-image-card">
                    <img src="${image.url}" alt="">
                    <span>${escapeHtml(columnLetters(image.col) + image.row)} · ${index + 1}</span>
                </div>
            `).join('');
        }

        function renderExportResult(data) {
            downloadBtn?.classList.toggle('hidden', !data?.blob);
            if (resultMeta) {
                const sourceText = data?.plan_source === 'ai' ? 'AI 规则' : '本地规则';
                resultMeta.textContent = data
                    ? `${data.images_count} 张图片 · ${data.sheets_count} 个 sheet · ${sourceText}`
                    : '等待处理';
            }

            if (planBox) {
                planBox.classList.toggle('hidden', !data?.plan);
                planBox.textContent = data?.plan ? JSON.stringify({
                    source: data.plan_source,
                    used_provider: data.used_provider || null,
                    used_model: data.used_model || null,
                    plan: data.plan,
                }, null, 2) : '';
            }

            if (warningsBox) {
                const warnings = data?.warnings || [];
                warningsBox.classList.toggle('hidden', warnings.length === 0);
                warningsBox.textContent = warnings.join('\n');
            }

            if (previewWrap && previewBody) {
                const rows = data?.manifest_preview || [];
                previewWrap.classList.toggle('hidden', rows.length === 0);
                previewBody.innerHTML = rows.map(row => `
                    <tr>
                        <td>${escapeHtml(row.sheet)}</td>
                        <td>${escapeHtml(row.row)}</td>
                        <td>${escapeHtml(row.image_index)}</td>
                        <td>${escapeHtml(row.file_path)}</td>
                    </tr>
                `).join('');
            }
        }

        function revokePreviewUrls() {
            if (!workbook) return;
            workbook.sheets.forEach(sheet => {
                sheet.images.forEach(image => {
                    if (image.url) URL.revokeObjectURL(image.url);
                });
            });
        }

        function setResult(el, message, type = '') {
            if (!el) return;
            el.textContent = message || '';
            el.classList.toggle('error', type === 'error');
            el.classList.toggle('success', type === 'success');
        }

        function updateFileInfo(file) {
            if (!file) {
                if (fileNameEl) fileNameEl.textContent = '请选择一个 .xlsx 文件';
                if (fileSizeEl) fileSizeEl.textContent = '文件只在浏览器本地读取，不上传服务器';
                return;
            }
            if (fileNameEl) fileNameEl.textContent = file.name;
            if (fileSizeEl) fileSizeEl.textContent = formatBytes(file.size);
        }
    };

    async function parseXlsxWorkbook(file) {
        if (!('DecompressionStream' in window)) {
            throw new Error('当前浏览器不支持本地解压 xlsx，请使用新版 Chrome 或 Edge。');
        }

        const zip = await LocalZipReader.fromFile(file);
        const sharedStrings = await readSharedStrings(zip);
        const sheetRefs = await readWorkbookSheets(zip);
        const sheets = [];

        for (const sheetRef of sheetRefs) {
            const rowsInfo = await readSheetRows(zip, sheetRef.path, sharedStrings);
            const images = await readSheetImages(zip, sheetRef.path);
            const headerRow = guessHeaderRow(rowsInfo.rows, images);
            const headers = headersForRow(rowsInfo.rows.get(headerRow), rowsInfo.maxCol);

            sheets.push({
                name: sheetRef.name,
                path: sheetRef.path,
                rows: rowsInfo.rows,
                maxRow: rowsInfo.maxRow,
                maxCol: rowsInfo.maxCol,
                images,
                headerRow,
                headers,
            });
        }

        if (sheets.length === 0) {
            throw new Error('没有读取到工作表。');
        }

        return {fileName: file.name, zip, sheets};
    }

    async function exportImagesLocally(workbook, instruction, apiDeps = {}) {
        const planResult = await resolvePlan(workbook, instruction, apiDeps);
        const plan = planResult.plan;
        const files = [];
        const manifestRows = [];
        const warnings = [...(planResult.warnings || [])];
        const usedPaths = new Set();
        const rowImageIndexes = new Map();
        const unmatchedFolderWarnings = new Set();
        let imageCount = 0;
        let sheetCount = 0;
        let globalIndex = 0;

        for (const sheet of workbook.sheets) {
            if (sheet.images.length === 0) continue;
            if (plan.sheet_mode === 'selected' && plan.sheets.length && !plan.sheets.includes(sheet.name)) continue;
            sheetCount++;
            const headerRow = resolveHeaderRow(sheet, plan);
            const headers = headerRow === sheet.headerRow
                ? sheet.headers
                : headersForRow(sheet.rows.get(headerRow), sheet.maxCol);

            for (const image of sheet.images) {
                const matchedRow = matchImageRow(sheet.rows, headerRow, image.row);
                const rowCells = sheet.rows.get(matchedRow);
                const rowData = rowToAssoc(rowCells, headers);
                const rowKey = `${sheet.name}#${matchedRow}`;
                const rowImageIndex = (rowImageIndexes.get(rowKey) || 0) + 1;
                rowImageIndexes.set(rowKey, rowImageIndex);
                globalIndex++;

                const placeholders = makePlaceholders(
                    rowData,
                    sheet.name,
                    matchedRow,
                    rowImageIndex,
                    globalIndex,
                    rowCells,
                    plan.field_column_map,
                );
                const processed = await processImage(image.bytes, image.extension, plan.image_processing, warnings);
                let folder = renderFolder(plan.folder_template, placeholders);
                if (String(plan.folder_template || '').includes('69码') && !folder) {
                    folder = `未匹配69码/${sanitizePathPart(`${sheet.name}_${matchedRow}`, 'row')}`;
                    const warningKey = `${sheet.name}#${matchedRow}#69码`;
                    if (!unmatchedFolderWarnings.has(warningKey)) {
                        warnings.push(`${sheet.name} 第 ${matchedRow} 行没有匹配到 69 码，已放入未匹配目录。`);
                        unmatchedFolderWarnings.add(warningKey);
                    }
                }
                let filenameBase = renderTemplate(plan.filename_template, placeholders);
                if (!filenameBase) {
                    filenameBase = renderTemplate(plan.fallback_filename_template, placeholders);
                }
                filenameBase = sanitizePathPart(filenameBase, `image-${globalIndex}`);
                const entryName = uniquePath(`${folder ? folder + '/' : ''}${filenameBase}.${processed.extension}`, usedPaths);

                files.push({name: entryName, bytes: processed.bytes});
                imageCount++;

                manifestRows.push({
                    sheet: sheet.name,
                    row: matchedRow,
                    image_index: rowImageIndex,
                    file_path: entryName,
                    source_media: image.path,
                    anchor: columnLetters(image.col) + image.row,
                });
            }
        }

        if (imageCount < 1) {
            throw new Error('没有找到可提取的内嵌图片。');
        }

        files.push({name: 'manifest.csv', bytes: utf8Bytes('\uFEFF' + csv(manifestRows))});
        files.push({
            name: 'plan.json',
            bytes: utf8Bytes(JSON.stringify({
                source: planResult.source,
                used_provider: planResult.used_provider || null,
                used_model: planResult.used_model || null,
                plan,
            }, null, 2)),
        });

        const blob = createStoredZip(files);
        const baseName = sanitizePathPart(workbook.fileName.replace(/\.xlsx$/i, ''), 'excel-images');

        return {
            blob,
            fileName: `${baseName}-images.zip`,
            images_count: imageCount,
            sheets_count: sheetCount,
            plan_source: planResult.source,
            used_provider: planResult.used_provider || null,
            used_model: planResult.used_model || null,
            plan,
            manifest_preview: manifestRows.slice(0, 50),
            warnings,
        };
    }

    async function resolvePlan(workbook, instruction, apiDeps) {
        const localPlan = makeLocalPlan(workbook, instruction);
        const token = localStorage.getItem(apiDeps.userTokenKey);

        if (!token || typeof apiDeps.userApi !== 'function') {
            return {
                source: 'local-rule',
                plan: localPlan,
                warnings: ['未登录，已使用本地规则；登录后才会调用 AI 处理不规则表格。'],
            };
        }

        try {
            const response = await apiDeps.userApi('/api/excel-automation/image-extract/plan', {
                method: 'POST',
                body: {
                    instruction,
                    summary: buildWorkbookSummary(workbook),
                },
            });

            return {
                source: response.source || 'ai',
                used_provider: response.used_provider || null,
                used_model: response.used_model || null,
                plan: normalizePlanForLocal(response.plan, localPlan),
                warnings: Array.isArray(response.warnings) ? response.warnings : [],
            };
        } catch (error) {
            return {
                source: 'local-rule',
                plan: localPlan,
                warnings: [`AI 规则生成失败，已使用本地规则：${error.message}`],
            };
        }
    }

    function makeLocalPlan(workbook, instruction) {
        const barcodeKeywords = ['69码', '69 码', '条码', '条形码', '商品条码', '国际条码', 'EAN', 'ean', 'barcode', 'bar code', 'UPC', 'upc'];
        const wantsBarcode = containsAny(instruction, barcodeKeywords);
        const explicitBarcodeColumn = explicitColumn(instruction, barcodeKeywords);
        const barcodeColumn = explicitBarcodeColumn || (wantsBarcode ? inferColumnFromWorkbook(workbook, barcodeKeywords, 'barcode') : null);
        const fieldColumnMap = {};
        if (barcodeColumn) fieldColumnMap['69码'] = barcodeColumn;
        const explicitlyBarcodeFileName = wantsBarcode
            && containsAny(instruction, ['文件名', '图片名'])
            && !containsAny(instruction, ['文件夹', '目录', '/1.jpg', '1.jpg', '2.jpg', '创建文件夹', '每个码']);
        const wantsBarcodeFolder = wantsBarcode && !explicitlyBarcodeFileName;
        let filenameTemplate = null;
        let folderTemplate = '';

        if (wantsBarcodeFolder) {
            filenameTemplate = '{图片序号}';
            folderTemplate = '{69码}';
        } else if (explicitlyBarcodeFileName) {
            filenameTemplate = '{69码}_{图片序号}';
        }

        const fields = [];
        const addField = (name, keywords) => {
            if (containsAny(instruction, keywords) || workbook.sheets.some(sheet => sheet.headers.some(header => containsAny(header, keywords)))) {
                fields.push(name);
            }
        };

        if (!filenameTemplate) {
            addField('69码', barcodeKeywords);
            addField('货号', ['货号', '款号', 'sku', 'SKU', '编码', '商品编码', 'item', 'code']);
            addField('颜色', ['颜色', '色号', 'color']);
            addField('尺码', ['尺码', '尺寸', 'size']);
            addField('品名', ['品名', '名称', '商品名', 'title', 'name']);
            addField('品牌', ['品牌', 'brand']);
            addField('分类', ['分类', '类目', 'category']);

            if (fields.length === 0) fields.push('货号');
            fields.push('图片序号');
            filenameTemplate = `{${fields.join('}_{')}}`;
        }

        if (folderTemplate) {
            // Explicit barcode folder rule already wins.
        } else if (containsAny(instruction, ['每个sheet', '每个 sheet', '按sheet', '按 sheet', 'sheet单独', '工作表单独'])) {
            folderTemplate = '{sheet}';
        } else if (containsAny(instruction, ['按品牌', '品牌分', '品牌文件夹'])) {
            folderTemplate = '{品牌}';
        } else if (containsAny(instruction, ['按分类', '按类目', '分类文件夹', '类目文件夹'])) {
            folderTemplate = '{分类}';
        } else if (workbook.sheets.length > 1) {
            folderTemplate = '{sheet}';
        }

        let resize = null;
        const resizeMatch = instruction.match(/(\d{2,5})\s*[xX×*]\s*(\d{2,5})/u);
        if (resizeMatch) {
            resize = {width: Number(resizeMatch[1]), height: Number(resizeMatch[2])};
        }

        let format = 'original';
        if (containsAny(instruction, ['jpg', 'jpeg', 'JPG', 'JPEG'])) format = 'jpg';
        if (containsAny(instruction, ['png', 'PNG'])) format = 'png';

        return {
            mode: 'browser-local',
            sheet_mode: 'all',
            sheets: [],
            header_row_by_sheet: {},
            field_column_map: fieldColumnMap,
            filename_template: filenameTemplate,
            folder_template: folderTemplate,
            fallback_filename_template: '{sheet}_{row}_{图片序号}',
            image_match_rule: 'anchor_row',
            image_processing: {
                crop_whitespace: containsAny(instruction, ['裁剪', '裁掉白边', '去白边', '白边']),
                resize,
                enhance: containsAny(instruction, ['清晰', '清晰化', '锐化', '增强']),
                format,
            },
        };
    }

    function buildWorkbookSummary(workbook) {
        return {
            file_name: workbook.fileName,
            sheets: workbook.sheets.slice(0, 30).map(sheet => {
                const headerRow = sheet.headerRow || 1;
                const headers = headersForRow(sheet.rows.get(headerRow), sheet.maxCol);
                const sampleRows = [];
                for (let row = headerRow + 1; row <= sheet.maxRow && sampleRows.length < 8; row++) {
                    const cells = sheet.rows.get(row);
                    if (!hasAnyValue(cells)) continue;
                    sampleRows.push({
                        row,
                        values: rowToAssoc(cells, headers),
                        cells: rowCellsToList(cells, sheet.maxCol, 24),
                    });
                }

                return {
                    name: sheet.name,
                    max_row: sheet.maxRow,
                    max_col: sheet.maxCol,
                    guessed_header_row: headerRow,
                    headers: headers.slice(1, Math.min(sheet.maxCol, 30) + 1),
                    sample_rows: sampleRows,
                    column_samples: buildColumnSamples(sheet, headers),
                    image_count: sheet.images.length,
                    image_anchors: sheet.images.slice(0, 120).map(image => ({
                        row: image.row,
                        col: columnLetters(image.col),
                        cell: columnLetters(image.col) + image.row,
                    })),
                };
            }),
        };
    }

    function buildColumnSamples(sheet, headers) {
        const columns = [];
        const maxCol = Math.min(sheet.maxCol || 0, 40);
        const maxRow = Math.min(sheet.maxRow || 0, 80);

        for (let col = 1; col <= maxCol; col++) {
            const samples = [];
            for (let row = 1; row <= maxRow && samples.length < 8; row++) {
                const value = String(sheet.rows.get(row)?.get(col) || '').trim();
                if (value) samples.push({row, value});
            }

            if (samples.length || headers[col]) {
                columns.push({
                    column: columnLetters(col),
                    header: String(headers[col] || '').trim(),
                    samples,
                });
            }
        }

        return columns;
    }

    function rowCellsToList(cells, maxCol, limit) {
        const out = [];
        const lastCol = Math.min(maxCol || 0, limit);
        for (let col = 1; col <= lastCol; col++) {
            const value = String(cells?.get(col) || '').trim();
            if (value) out.push({column: columnLetters(col), value});
        }
        return out;
    }

    function normalizePlanForLocal(plan, fallback) {
        const input = isPlainObject(plan) ? plan : {};
        const imageProcessing = isPlainObject(input.image_processing) ? input.image_processing : {};
        const fallbackProcessing = fallback.image_processing || {};
        const format = normalizeImageFormat(imageProcessing.format || fallbackProcessing.format);

        return {
            mode: 'browser-local',
            sheet_mode: ['all', 'selected'].includes(input.sheet_mode) ? input.sheet_mode : (fallback.sheet_mode || 'all'),
            sheets: Array.isArray(input.sheets) ? input.sheets.filter(name => typeof name === 'string') : (fallback.sheets || []),
            header_row_by_sheet: isPlainObject(input.header_row_by_sheet) ? input.header_row_by_sheet : (fallback.header_row_by_sheet || {}),
            field_column_map: normalizeFieldColumnMap({
                ...(fallback.field_column_map || {}),
                ...(isPlainObject(input.field_column_map) ? input.field_column_map : {}),
            }),
            filename_template: nonEmptyString(input.filename_template, fallback.filename_template),
            folder_template: nonEmptyString(input.folder_template, fallback.folder_template || ''),
            image_match_rule: 'anchor_row',
            fallback_filename_template: nonEmptyString(input.fallback_filename_template, fallback.fallback_filename_template),
            image_processing: {
                crop_whitespace: Boolean(imageProcessing.crop_whitespace ?? fallbackProcessing.crop_whitespace),
                resize: normalizeResize(imageProcessing.resize ?? fallbackProcessing.resize),
                enhance: Boolean(imageProcessing.enhance ?? fallbackProcessing.enhance),
                format,
            },
        };
    }

    function normalizeFieldColumnMap(map) {
        const normalized = {};
        Object.entries(map || {}).forEach(([field, column]) => {
            const name = String(field || '').trim();
            const letters = String(column || '').trim().toUpperCase();
            if (name && /^[A-Z]{1,3}$/u.test(letters)) normalized[name] = letters;
        });
        return normalized;
    }

    function normalizeResize(resize) {
        if (typeof resize === 'string') {
            const match = resize.match(/(\d{2,5})\s*[xX×*]\s*(\d{2,5})/u);
            if (match) return {width: Number(match[1]), height: Number(match[2])};
        }
        if (!isPlainObject(resize)) return null;
        const width = Number(resize.width);
        const height = Number(resize.height);
        return width > 0 && height > 0 ? {width, height} : null;
    }

    function normalizeImageFormat(format) {
        const value = String(format || 'original').toLowerCase();
        if (value === 'jpeg') return 'jpg';
        return ['original', 'jpg', 'png'].includes(value) ? value : 'original';
    }

    function nonEmptyString(value, fallback) {
        const text = String(value ?? '').trim();
        return text || fallback || '';
    }

    function resolveHeaderRow(sheet, plan) {
        const value = plan.header_row_by_sheet?.[sheet.name];
        const row = Number(value);
        return Number.isInteger(row) && row >= 1 && row <= sheet.maxRow ? row : sheet.headerRow;
    }

    function explicitColumn(instruction, keywords) {
        const keywordPattern = keywords.map(escapeRegExp).join('|');
        const before = new RegExp(`\\b([A-Z]{1,3})\\s*列[^，。；;\\n]*(${keywordPattern})`, 'iu');
        const after = new RegExp(`(${keywordPattern})[^，。；;\\n]*\\b([A-Z]{1,3})\\s*列`, 'iu');
        const beforeMatch = String(instruction || '').match(before);
        if (beforeMatch) return beforeMatch[1].toUpperCase();
        const afterMatch = String(instruction || '').match(after);
        if (afterMatch) return afterMatch[2].toUpperCase();
        return null;
    }

    function inferColumnFromWorkbook(workbook, keywords, kind = 'text') {
        let bestColumn = null;
        let bestScore = 0;

        workbook.sheets.forEach(sheet => {
            const maxCol = Math.min(sheet.maxCol || 0, 80);
            const maxRow = Math.min(sheet.maxRow || 0, 200);

            for (let col = 1; col <= maxCol; col++) {
                let score = 0;
                const header = String(sheet.headers?.[col] || '').trim();
                if (containsAny(header, keywords)) score += 100;

                for (let row = 1; row <= maxRow; row++) {
                    const value = String(sheet.rows.get(row)?.get(col) || '').trim();
                    if (!value) continue;
                    if (containsAny(value, keywords)) score += 30;
                    if (kind === 'barcode' && looksLikeBarcode(value)) score += 80;
                }

                if (score > bestScore) {
                    bestScore = score;
                    bestColumn = columnLetters(col);
                }
            }
        });

        return bestScore > 0 ? bestColumn : null;
    }

    function looksLikeBarcode(value) {
        return /69\d{11}/u.test(String(value || '').replace(/\s+/gu, ''));
    }

    function escapeRegExp(value) {
        return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    function isPlainObject(value) {
        return value !== null && typeof value === 'object' && !Array.isArray(value);
    }

    class LocalZipReader {
        static async fromFile(file) {
            const bytes = new Uint8Array(await file.arrayBuffer());
            return new LocalZipReader(bytes);
        }

        constructor(bytes) {
            this.bytes = bytes;
            this.view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
            this.entries = this.readCentralDirectory();
        }

        async text(name) {
            return new TextDecoder('utf-8').decode(await this.fileBytes(name));
        }

        async fileBytes(name) {
            const entry = this.entries.get(name) || this.entries.get(name.replace(/^\/+/, ''));
            if (!entry) throw new Error(`xlsx 缺少文件：${name}`);

            const local = entry.localOffset;
            if (this.u32(local) !== 0x04034b50) {
                throw new Error(`zip 本地文件头损坏：${name}`);
            }
            const nameLen = this.u16(local + 26);
            const extraLen = this.u16(local + 28);
            const dataStart = local + 30 + nameLen + extraLen;
            const compressed = this.bytes.slice(dataStart, dataStart + entry.compressedSize);

            if (entry.method === 0) return compressed;
            if (entry.method === 8) return inflateRaw(compressed);
            throw new Error(`不支持的 zip 压缩方式：${entry.method}`);
        }

        readCentralDirectory() {
            const eocd = this.findEocd();
            const total = this.u16(eocd + 10);
            let offset = this.u32(eocd + 16);
            const entries = new Map();
            const decoder = new TextDecoder('utf-8');

            for (let i = 0; i < total; i++) {
                if (this.u32(offset) !== 0x02014b50) {
                    throw new Error('zip 中央目录损坏。');
                }
                const method = this.u16(offset + 10);
                const compressedSize = this.u32(offset + 20);
                const uncompressedSize = this.u32(offset + 24);
                const nameLen = this.u16(offset + 28);
                const extraLen = this.u16(offset + 30);
                const commentLen = this.u16(offset + 32);
                const localOffset = this.u32(offset + 42);
                const name = decoder.decode(this.bytes.slice(offset + 46, offset + 46 + nameLen));
                entries.set(name, {name, method, compressedSize, uncompressedSize, localOffset});
                offset += 46 + nameLen + extraLen + commentLen;
            }

            return entries;
        }

        findEocd() {
            const min = Math.max(0, this.bytes.length - 22 - 65535);
            for (let i = this.bytes.length - 22; i >= min; i--) {
                if (this.u32(i) === 0x06054b50) return i;
            }
            throw new Error('不是有效的 xlsx/zip 文件。');
        }

        u16(offset) { return this.view.getUint16(offset, true); }
        u32(offset) { return this.view.getUint32(offset, true); }
    }

    async function inflateRaw(bytes) {
        const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
        return new Uint8Array(await new Response(stream).arrayBuffer());
    }

    async function readSharedStrings(zip) {
        if (!zip.entries.has('xl/sharedStrings.xml')) return [];
        const dom = xml(await zip.text('xl/sharedStrings.xml'));
        return nodes(dom, 'si').map(si => nodes(si, 't').map(t => t.textContent || '').join(''));
    }

    async function readWorkbookSheets(zip) {
        const dom = xml(await zip.text('xl/workbook.xml'));
        const rels = await readRelationships(zip, 'xl/_rels/workbook.xml.rels', 'xl/workbook.xml');
        return nodes(dom, 'sheet').map((sheet, index) => {
            const rid = sheet.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'id')
                || sheet.getAttribute('r:id');
            return {
                name: sheet.getAttribute('name') || `Sheet${index + 1}`,
                path: rels.get(rid)?.target,
            };
        }).filter(sheet => sheet.path);
    }

    async function readRelationships(zip, relsPath, baseFile) {
        if (!zip.entries.has(relsPath)) return new Map();
        const dom = xml(await zip.text(relsPath));
        const rels = new Map();
        nodes(dom, 'Relationship').forEach(rel => {
            rels.set(rel.getAttribute('Id'), {
                type: rel.getAttribute('Type'),
                target: resolvePath(baseFile, rel.getAttribute('Target') || ''),
            });
        });
        return rels;
    }

    async function readSheetRows(zip, sheetPath, sharedStrings) {
        const dom = xml(await zip.text(sheetPath));
        const rows = new Map();
        let maxRow = 0;
        let maxCol = 0;

        nodes(dom, 'row').forEach((rowNode, rowIndex) => {
            const rowNumber = Number(rowNode.getAttribute('r')) || rowIndex + 1;
            maxRow = Math.max(maxRow, rowNumber);
            const cells = new Map();
            nodes(rowNode, 'c').forEach(cell => {
                const ref = cell.getAttribute('r') || '';
                const col = ref ? columnNumber(ref) : cells.size + 1;
                maxCol = Math.max(maxCol, col);
                const value = cellValue(cell, sharedStrings);
                if (value !== '') cells.set(col, value);
            });
            rows.set(rowNumber, cells);
        });

        return {rows, maxRow, maxCol};
    }

    async function readSheetImages(zip, sheetPath) {
        const sheetDom = xml(await zip.text(sheetPath));
        const sheetRels = await readRelationships(zip, relsPath(sheetPath), sheetPath);
        const images = [];

        for (const drawing of nodes(sheetDom, 'drawing')) {
            const rid = drawing.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'id')
                || drawing.getAttribute('r:id');
            const drawingPath = sheetRels.get(rid)?.target;
            if (!drawingPath) continue;
            images.push(...await readDrawingImages(zip, drawingPath));
        }

        images.sort((a, b) => a.row - b.row || a.col - b.col || a.path.localeCompare(b.path));
        return images;
    }

    async function readDrawingImages(zip, drawingPath) {
        const dom = xml(await zip.text(drawingPath));
        const rels = await readRelationships(zip, relsPath(drawingPath), drawingPath);
        const anchors = [...nodes(dom, 'twoCellAnchor'), ...nodes(dom, 'oneCellAnchor')];
        const images = [];

        for (const anchor of anchors) {
            const from = nodes(anchor, 'from')[0];
            const row = Number(nodes(from, 'row')[0]?.textContent || 0) + 1;
            const col = Number(nodes(from, 'col')[0]?.textContent || 0) + 1;
            const blip = nodes(anchor, 'blip')[0];
            const embed = blip?.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'embed')
                || blip?.getAttribute('r:embed');
            const path = rels.get(embed)?.target;
            if (!path || !zip.entries.has(path)) continue;

            const bytes = await zip.fileBytes(path);
            const extension = safeImageExtension(path.split('.').pop() || 'jpg');
            const blob = new Blob([bytes], {type: imageMime(extension)});
            images.push({
                row: Math.max(1, row),
                col: Math.max(1, col),
                path,
                bytes,
                extension,
                url: URL.createObjectURL(blob),
            });
        }

        return images;
    }

    function cellValue(cell, sharedStrings) {
        const type = cell.getAttribute('t') || '';
        if (type === 's') {
            const index = Number(firstText(cell, 'v'));
            return String(sharedStrings[index] || '').trim();
        }
        if (type === 'inlineStr') {
            return nodes(cell, 't').map(t => t.textContent || '').join('').trim();
        }
        if (type === 'b') {
            return firstText(cell, 'v') === '1' ? 'TRUE' : 'FALSE';
        }
        return firstText(cell, 'v').trim();
    }

    async function processImage(bytes, extension, processing, warnings) {
        const targetFormat = processing.format === 'png' ? 'png' : (processing.format === 'jpg' ? 'jpg' : extension);
        const shouldProcess = processing.crop_whitespace || processing.resize || processing.enhance || processing.format !== 'original';
        if (!shouldProcess) {
            return {bytes, extension: safeImageExtension(extension)};
        }

        try {
            const bitmap = await createImageBitmap(new Blob([bytes], {type: imageMime(extension)}));
            let canvas = document.createElement('canvas');
            let ctx = canvas.getContext('2d', {willReadFrequently: true});
            canvas.width = bitmap.width;
            canvas.height = bitmap.height;
            ctx.drawImage(bitmap, 0, 0);

            if (processing.crop_whitespace) {
                canvas = cropWhitespace(canvas);
                ctx = canvas.getContext('2d', {willReadFrequently: true});
            }

            if (processing.resize) {
                canvas = resizeToCanvas(canvas, processing.resize.width, processing.resize.height);
                ctx = canvas.getContext('2d', {willReadFrequently: true});
            }

            if (processing.enhance) {
                canvas = redrawWithFilter(canvas, 'contrast(1.08) saturate(1.04)');
            }

            const outExt = targetFormat === 'png' ? 'png' : 'jpg';
            const blob = await new Promise(resolve => canvas.toBlob(resolve, imageMime(outExt), 0.92));
            return {bytes: new Uint8Array(await blob.arrayBuffer()), extension: outExt};
        } catch (error) {
            warnings.push(`图片处理失败，已保留原图：${error.message}`);
            return {bytes, extension: safeImageExtension(extension)};
        }
    }

    function cropWhitespace(canvas) {
        const ctx = canvas.getContext('2d', {willReadFrequently: true});
        const {width, height} = canvas;
        const data = ctx.getImageData(0, 0, width, height).data;
        let minX = width, minY = height, maxX = -1, maxY = -1;

        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const i = (y * width + x) * 4;
                const a = data[i + 3];
                const isWhite = data[i] > 245 && data[i + 1] > 245 && data[i + 2] > 245;
                if (a > 10 && !isWhite) {
                    minX = Math.min(minX, x);
                    minY = Math.min(minY, y);
                    maxX = Math.max(maxX, x);
                    maxY = Math.max(maxY, y);
                }
            }
        }

        if (maxX < minX || maxY < minY) return canvas;
        const pad = 4;
        minX = Math.max(0, minX - pad);
        minY = Math.max(0, minY - pad);
        maxX = Math.min(width - 1, maxX + pad);
        maxY = Math.min(height - 1, maxY + pad);

        const out = document.createElement('canvas');
        out.width = maxX - minX + 1;
        out.height = maxY - minY + 1;
        out.getContext('2d').drawImage(canvas, minX, minY, out.width, out.height, 0, 0, out.width, out.height);
        return out;
    }

    function resizeToCanvas(source, width, height) {
        width = Math.max(1, Math.min(Number(width) || source.width, 5000));
        height = Math.max(1, Math.min(Number(height) || source.height, 5000));
        const scale = Math.min(width / source.width, height / source.height);
        const drawW = Math.max(1, Math.floor(source.width * scale));
        const drawH = Math.max(1, Math.floor(source.height * scale));
        const out = document.createElement('canvas');
        out.width = width;
        out.height = height;
        const ctx = out.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, width, height);
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(source, Math.floor((width - drawW) / 2), Math.floor((height - drawH) / 2), drawW, drawH);
        return out;
    }

    function redrawWithFilter(source, filter) {
        const out = document.createElement('canvas');
        out.width = source.width;
        out.height = source.height;
        const ctx = out.getContext('2d');
        ctx.filter = filter;
        ctx.drawImage(source, 0, 0);
        return out;
    }

    function createStoredZip(files) {
        const encoder = new TextEncoder();
        const chunks = [];
        const central = [];
        let offset = 0;
        const now = new Date();
        const dosTime = ((now.getHours() & 31) << 11) | ((now.getMinutes() & 63) << 5) | Math.floor(now.getSeconds() / 2);
        const dosDate = (((now.getFullYear() - 1980) & 127) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();

        for (const file of files) {
            const nameBytes = encoder.encode(file.name.replace(/^\/+/, ''));
            const data = file.bytes instanceof Uint8Array ? file.bytes : new Uint8Array(file.bytes);
            const crc = crc32(data);
            const local = new Uint8Array(30 + nameBytes.length);
            const view = new DataView(local.buffer);
            writeLocalHeader(view, crc, data.length, nameBytes.length, dosTime, dosDate);
            local.set(nameBytes, 30);
            chunks.push(local, data);

            const centralHeader = new Uint8Array(46 + nameBytes.length);
            const centralView = new DataView(centralHeader.buffer);
            writeCentralHeader(centralView, crc, data.length, nameBytes.length, offset, dosTime, dosDate);
            centralHeader.set(nameBytes, 46);
            central.push(centralHeader);
            offset += local.length + data.length;
        }

        const centralOffset = offset;
        let centralSize = 0;
        central.forEach(chunk => {
            chunks.push(chunk);
            centralSize += chunk.length;
            offset += chunk.length;
        });

        const eocd = new Uint8Array(22);
        const eocdView = new DataView(eocd.buffer);
        eocdView.setUint32(0, 0x06054b50, true);
        eocdView.setUint16(8, files.length, true);
        eocdView.setUint16(10, files.length, true);
        eocdView.setUint32(12, centralSize, true);
        eocdView.setUint32(16, centralOffset, true);
        chunks.push(eocd);

        return new Blob(chunks, {type: 'application/zip'});
    }

    function writeLocalHeader(view, crc, size, nameLength, dosTime, dosDate) {
        view.setUint32(0, 0x04034b50, true);
        view.setUint16(4, 20, true);
        view.setUint16(6, 0x0800, true);
        view.setUint16(8, 0, true);
        view.setUint16(10, dosTime, true);
        view.setUint16(12, dosDate, true);
        view.setUint32(14, crc, true);
        view.setUint32(18, size, true);
        view.setUint32(22, size, true);
        view.setUint16(26, nameLength, true);
    }

    function writeCentralHeader(view, crc, size, nameLength, offset, dosTime, dosDate) {
        view.setUint32(0, 0x02014b50, true);
        view.setUint16(4, 20, true);
        view.setUint16(6, 20, true);
        view.setUint16(8, 0x0800, true);
        view.setUint16(10, 0, true);
        view.setUint16(12, dosTime, true);
        view.setUint16(14, dosDate, true);
        view.setUint32(16, crc, true);
        view.setUint32(20, size, true);
        view.setUint32(24, size, true);
        view.setUint16(28, nameLength, true);
        view.setUint32(42, offset, true);
    }

    const crcTable = (() => {
        const table = new Uint32Array(256);
        for (let n = 0; n < 256; n++) {
            let c = n;
            for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
            table[n] = c >>> 0;
        }
        return table;
    })();

    function crc32(bytes) {
        let crc = 0xffffffff;
        for (let i = 0; i < bytes.length; i++) {
            crc = crcTable[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
        }
        return (crc ^ 0xffffffff) >>> 0;
    }

    function guessHeaderRow(rows, images) {
        const firstImageRow = images.length ? Math.min(...images.map(image => image.row)) : 20;
        const limit = Math.max(1, Math.min(30, firstImageRow));
        let bestRow = 1;
        let bestScore = -1;

        for (const [rowNumber, cells] of rows.entries()) {
            if (rowNumber > limit) continue;
            const values = [...cells.values()].filter(Boolean);
            let score = values.length;
            values.forEach(value => {
                if (containsAny(value, ['货号', '款号', 'sku', '编码', '品名', '名称', '颜色', '尺码', '品牌', '分类', '图片', 'image'])) {
                    score += 4;
                }
            });
            if (score > bestScore) {
                bestScore = score;
                bestRow = rowNumber;
            }
        }

        return bestRow;
    }

    function headersForRow(row, maxCol) {
        const headers = [];
        for (let col = 1; col <= Math.max(1, maxCol); col++) {
            headers[col] = String(row?.get(col) || columnLetters(col)).trim();
        }
        return headers;
    }

    function matchImageRow(rows, headerRow, anchorRow) {
        const row = Math.max(headerRow + 1, anchorRow);
        const candidates = [row, row + 1, row - 1, row + 2, row - 2];
        return candidates.find(candidate => candidate > headerRow && hasAnyValue(rows.get(candidate))) || row;
    }

    function rowToAssoc(row, headers) {
        const data = {};
        headers.forEach((header, col) => {
            if (!col) return;
            const value = String(row?.get(col) || '').trim();
            if (value) data[header] = value;
        });
        return data;
    }

    function makePlaceholders(rowData, sheetName, row, rowImageIndex, globalIndex, rowCells = new Map(), fieldColumnMap = {}) {
        const values = {
            sheet: sheetName,
            sheet_name: sheetName,
            工作表: sheetName,
            row: String(row),
            行号: String(row),
            index: String(globalIndex),
            序号: String(globalIndex),
            图片序号: String(rowImageIndex),
            image_index: String(rowImageIndex),
        };

        Object.entries(rowData).forEach(([key, value]) => {
            values[key] = String(value);
            values[normalizeKey(key)] = String(value);
        });

        const aliases = {
            '69码': ['69码', '69 码', '条码', '条形码', '商品条码', '国际条码', 'EAN', 'ean', 'barcode', 'bar code', 'UPC', 'upc'],
            货号: ['货号', '款号', 'sku', 'SKU', '编码', '商品编码', 'item', 'code'],
            颜色: ['颜色', '色号', 'color'],
            尺码: ['尺码', '尺寸', 'size'],
            品名: ['品名', '名称', '商品名', 'title', 'name'],
            品牌: ['品牌', 'brand'],
            分类: ['分类', '类目', 'category'],
        };

        Object.entries(aliases).forEach(([canonical, keywords]) => {
            const found = Object.entries(rowData).find(([key, value]) => containsAny(key, keywords) && String(value).trim());
            if (found) values[canonical] = String(found[1]).trim();
        });

        Object.entries(fieldColumnMap || {}).forEach(([field, column]) => {
            const col = columnNumber(`${String(column || '').trim()}1`);
            const value = String(rowCells?.get(col) || '').trim();
            if (!field || !col || !value) return;
            values[String(field).trim()] = value;
            values[normalizeKey(field)] = value;
        });

        return values;
    }

    function renderTemplate(template, values) {
        return String(template || '')
            .replace(/\{([^}]+)\}/gu, (_, key) => values[key.trim()] || values[normalizeKey(key)] || '')
            .replace(/[_\-\s]+/gu, '_')
            .replace(/^[_\-\s]+|[_\-\s]+$/gu, '');
    }

    function renderFolder(template, values) {
        const folder = renderTemplate(template, values);
        if (!folder) return '';
        return folder.split(/[\\/]+/u).map(part => sanitizePathPart(part, '')).filter(Boolean).join('/');
    }

    function uniquePath(path, used) {
        path = path.replace(/\\/g, '/').replace(/^\/+/, '');
        const slash = path.lastIndexOf('/');
        const dir = slash >= 0 ? path.slice(0, slash + 1) : '';
        const file = slash >= 0 ? path.slice(slash + 1) : path;
        const dot = file.lastIndexOf('.');
        const base = dot >= 0 ? file.slice(0, dot) : file;
        const ext = dot >= 0 ? file.slice(dot) : '';
        let candidate = path;
        let index = 2;
        while (used.has(candidate.toLowerCase())) {
            candidate = `${dir}${base}-${index}${ext}`;
            index++;
        }
        used.add(candidate.toLowerCase());
        return candidate;
    }

    function csv(rows) {
        const header = ['sheet', 'row', 'image_index', 'file_path', 'source_media', 'anchor'];
        return [header, ...rows.map(row => header.map(key => row[key] ?? ''))]
            .map(row => row.map(csvCell).join(','))
            .join('\r\n');
    }

    function csvCell(value) {
        const text = String(value);
        return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    }

    function saveBlob(blob, fileName) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 3000);
    }

    function xml(text) {
        const dom = new DOMParser().parseFromString(text, 'application/xml');
        if (dom.getElementsByTagName('parsererror').length) {
            throw new Error('xlsx XML 解析失败。');
        }
        return dom;
    }

    function nodes(root, localName) {
        return Array.from(root?.getElementsByTagNameNS?.('*', localName) || []);
    }

    function firstText(root, localName) {
        return nodes(root, localName)[0]?.textContent || '';
    }

    function resolvePath(baseFile, target) {
        if (!target) return '';
        if (target.startsWith('/')) return target.replace(/^\/+/, '');
        const parts = `${baseFile.split('/').slice(0, -1).join('/')}/${target}`.split('/');
        const out = [];
        parts.forEach(part => {
            if (!part || part === '.') return;
            if (part === '..') out.pop();
            else out.push(part);
        });
        return out.join('/');
    }

    function relsPath(path) {
        const parts = path.split('/');
        const file = parts.pop();
        return `${parts.join('/')}/_rels/${file}.rels`;
    }

    function columnNumber(ref) {
        const match = String(ref).match(/^([A-Z]+)/i);
        if (!match) return 0;
        return match[1].toUpperCase().split('').reduce((num, char) => num * 26 + char.charCodeAt(0) - 64, 0);
    }

    function columnLetters(col) {
        let letters = '';
        while (col > 0) {
            col--;
            letters = String.fromCharCode(65 + (col % 26)) + letters;
            col = Math.floor(col / 26);
        }
        return letters || 'A';
    }

    function sanitizePathPart(value, fallback) {
        const text = String(value || '')
            .replace(/[<>:"/\\|?*\x00-\x1F]+/gu, '_')
            .replace(/\s+/gu, ' ')
            .replace(/^[ ._\-]+|[ ._\-]+$/gu, '')
            .slice(0, 120);
        return text || fallback;
    }

    function normalizeKey(key) {
        return String(key || '').toLowerCase().replace(/[\s_：:\-]+/gu, '');
    }

    function containsAny(text, keywords) {
        const haystack = String(text || '').toLowerCase();
        return keywords.some(keyword => haystack.includes(String(keyword).toLowerCase()));
    }

    function hasAnyValue(row) {
        if (!row) return false;
        return [...row.values()].some(value => String(value || '').trim() !== '');
    }

    function safeImageExtension(extension) {
        extension = String(extension || '').toLowerCase();
        if (extension === 'jpeg') return 'jpg';
        return ['jpg', 'png', 'gif', 'webp', 'bmp'].includes(extension) ? extension : 'jpg';
    }

    function imageMime(extension) {
        extension = safeImageExtension(extension);
        if (extension === 'jpg') return 'image/jpeg';
        return `image/${extension}`;
    }

    function utf8Bytes(text) {
        return new TextEncoder().encode(text);
    }

    function formatBytes(bytes) {
        if (!Number.isFinite(bytes) || bytes <= 0) return '0 KB';
        const units = ['B', 'KB', 'MB', 'GB'];
        let value = bytes;
        let unit = 0;
        while (value >= 1024 && unit < units.length - 1) {
            value /= 1024;
            unit++;
        }
        return `${value >= 10 || unit === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unit]}`;
    }
})();
