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
        const planPanel = document.querySelector('#mergePlanPanel');
        const fieldChipsEl = document.querySelector('#mergeFieldChips');
        const mappingBody = document.querySelector('#mergeMappingBody');
        const addFieldBtn = document.querySelector('#mergeAddFieldBtn');
        const previewSection = document.querySelector('#mergePreviewSection');
        const previewTable = document.querySelector('#mergePreviewTable');
        const sourceColumnsOpt = document.querySelector('#mergeSourceColumnsOpt');
        const dedupeOpt = document.querySelector('#mergeDedupeOpt');

        const mergeKit = window.TableMergeKit;

        let sourceFiles = [];
        let templateFile = null;
        let mapping = null;
        let mergedResult = null;
        let fieldIdSeq = 1;
        let lastEvidence = null;

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
                ? '正在调用 AI 规划合并...'
                : '未登录，使用本地规则规划合并...');
            try {
                const planResult = await resolvePlan();
                mapping = mappingFromPlan(planResult.plan);
                if (dedupeOpt && typeof planResult.plan.dedupe === 'boolean') {
                    dedupeOpt.checked = planResult.plan.dedupe;
                }
                if (sourceColumnsOpt) {
                    if (mapping.operation === 'join') {
                        sourceColumnsOpt.checked = false;
                    } else if (typeof planResult.plan.include_source === 'boolean') {
                        sourceColumnsOpt.checked = planResult.plan.include_source;
                    }
                }
                renderWarnings(planResult.warnings || []);
                renderMapping();
                const sourceText = planResult.source === 'ai' ? 'AI' : '本地规则';
                setStatus(`${sourceText}规划完成，请核对上方合并计划和字段归类，确认后点「开始合并」。`, 'success');
            } catch (error) {
                setStatus(`合并规划失败：${error.message}`, 'error');
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
                let message = `合并完成：${mergedResult.rows.length} 行数据`;
                if (mergedResult.joinStats) {
                    const stats = mergedResult.joinStats;
                    message += `，主表 ${stats.leftRows} 行中 ${stats.matchedLeft} 行匹配上`;
                    if (stats.joinType !== 'left' && stats.unmatchedLeft) {
                        message += `（未匹配的 ${stats.unmatchedLeft} 行已按计划丢弃）`;
                    }
                    message += `，被查表 ${stats.rightKeyCount} 个键用到 ${stats.usedRightKeys} 个`;
                } else {
                    message += `，来自 ${mergedResult.sheetCount} 个 sheet`;
                }
                if (mergedResult.dropped) message += `，去重移除 ${mergedResult.dropped} 行`;
                setStatus(`${message}。`, 'success');
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
            lastEvidence = null;
            mappingSection?.classList.add('hidden');
            planPanel?.classList.add('hidden');
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

        /**
         * 本地算证据：每列的值形态 / 唯一值数 / 非空数，以及跨 sheet 的键值交集。
         * 只有统计结果会随摘要发给 AI，列值本身不出浏览器。
         */
        function computeEvidence() {
            const stats = new Map();
            const candidates = [];
            sourceFiles.forEach((file, fileIndex) => {
                file.sheets.forEach(sheet => {
                    const maxCol = Math.min(sheet.maxCol || 0, 60);
                    for (let col = 1; col <= maxCol; col++) {
                        const header = String(sheet.rows.get(sheet.headerRow)?.get(col) || '').trim();
                        const {set, nonEmpty} = mergeKit.collectColumnValues(sheet, col);
                        if (!header && !nonEmpty) continue;
                        const letter = kit.columnLetters(col);
                        const kind = mergeKit.detectValueKind(Array.from(set).slice(0, 80));
                        stats.set(columnKey(fileIndex, sheet.name, letter), {kind, unique: set.size, nonEmpty});
                        const uniqueRatio = nonEmpty ? set.size / nonEmpty : 0;
                        const idLike = kind === 'phone' || kind === 'longid' || kind === 'code';
                        if (nonEmpty >= 3 && (idLike || uniqueRatio >= 0.8)) {
                            candidates.push({
                                ref: {file_index: fileIndex, sheet: sheet.name, column: letter, header},
                                sheetId: `${fileIndex}#${sheet.name}`,
                                set,
                            });
                        }
                    }
                });
            });
            return {stats, overlaps: mergeKit.computeKeyOverlaps(candidates)};
        }

        function buildSummary(evidence) {
            const summary = {
                files: sourceFiles.map((file, fileIndex) => ({
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
                            const column = {column: kit.columnLetters(col), header, samples};
                            const stat = evidence?.stats.get(columnKey(fileIndex, sheet.name, column.column));
                            if (stat) {
                                column.value_kind = stat.kind;
                                column.unique_count = stat.unique;
                                column.non_empty = stat.nonEmpty;
                            }
                            columns.push(column);
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
            if (evidence?.overlaps.length) {
                summary.key_overlaps = evidence.overlaps;
            }
            return summary;
        }

        async function resolvePlan() {
            lastEvidence = computeEvidence();
            const localPlan = makeLocalPlan(lastEvidence);
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
                        summary: buildSummary(lastEvidence),
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
            ['姓名', '人名', '收货人姓名', '收件人姓名', '收件人', '联系人'],
            ['电话', '手机号', '手机号码', '电话号码', '联系电话', '收货人电话', '收件人电话', '买家手机号', 'phone', 'mobile', 'tel'],
            ['快递单号', '快递', '快递号', '物流单号', '运单号', '运单编号', '商品发货物流单号', 'tracking no', 'tracking number'],
            ['线上单号', '订单号', '订单编号', '线上订单号', 'order no', 'order id'],
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

        // 模板字段的来源列：表头与字段名完全一致的排最前（合并取每行第一个非空来源，
        // 例如模板「线上单号」同时命中「线上单号」「订单编号」时必须优先用前者）。
        function templateFieldSources(field, pool) {
            const exact = [];
            const grouped = [];
            pool.forEach(col => {
                if (!groupKey(field) || groupKey(field) !== groupKey(col.header)) return;
                const source = {file_index: col.fileIndex, sheet: col.sheet, column: col.column};
                (normalizeHeader(col.header) === normalizeHeader(field) ? exact : grouped).push(source);
            });
            return exact.concat(grouped);
        }

        function makeLocalPlan(evidence) {
            const columns = listSourceColumns();
            const overlaps = evidence?.overlaps || [];

            if (templateFile) {
                // 两表存在高重合键列时，本地规则也推断「按键匹配」：行数多的一侧作主表。
                const best = overlaps.find(pair => pair.overlap >= 3 && pair.coverage >= 0.5);
                if (best) {
                    const rowsOf = ref => {
                        const sheet = resolveSheet(ref.file_index, ref.sheet);
                        return sheet ? Math.max(0, sheet.maxRow - sheet.headerRow) : 0;
                    };
                    const [left, right] = rowsOf(best.a) >= rowsOf(best.b) ? [best.a, best.b] : [best.b, best.a];
                    const allowed = new Set([`${left.file_index}#${left.sheet}`, `${right.file_index}#${right.sheet}`]);
                    const targets = templateFile.fields.map(field => ({
                        name: field,
                        sources: templateFieldSources(field, columns.filter(col => allowed.has(`${col.fileIndex}#${col.sheet}`))),
                    }));
                    return {
                        operation: 'join',
                        join: {
                            left: {file_index: left.file_index, sheet: left.sheet},
                            right: {file_index: right.file_index, sheet: right.sheet},
                            keys: [{left_column: left.column, right_column: right.column}],
                            type: 'inner',
                        },
                        dedupe: true,
                        include_source: false,
                        target_fields: targets,
                        notes: [
                            `本地规则按值重合推断匹配键：「${left.header || left.column}」=「${right.header || right.column}」（重合 ${best.overlap} 个值），请人工核对。`,
                        ],
                    };
                }

                const targets = templateFile.fields.map(field => ({
                    name: field,
                    sources: templateFieldSources(field, columns),
                }));
                return {
                    operation: 'union',
                    join: null,
                    dedupe: false,
                    include_source: false,
                    target_fields: targets,
                    notes: ['本地规则按模板字段名匹配，请人工核对未匹配的列。'],
                };
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

            return {
                operation: 'union',
                join: null,
                dedupe: false,
                include_source: true,
                target_fields: targets,
                notes: ['本地规则按表头同义词归类，请人工核对。'],
            };
        }

        function mappingFromPlan(plan) {
            const targetFields = [];
            const assign = new Map();
            // 计划里 sources 的先后是取值优先级（每行取第一个非空），执行时按它排序。
            const sourceRank = new Map();

            (plan.target_fields || []).forEach(target => {
                const id = `f${fieldIdSeq++}`;
                targetFields.push({id, name: String(target.name || '').trim() || `字段${targetFields.length + 1}`});
                (target.sources || []).forEach((source, rank) => {
                    const key = columnKey(source.file_index, source.sheet, source.column);
                    if (!assign.has(key)) {
                        assign.set(key, id);
                        sourceRank.set(key, rank);
                    }
                });
            });

            let operation = plan.operation === 'join' ? 'join' : 'union';
            let join = null;
            if (operation === 'join' && plan.join) {
                const left = plan.join.left || {};
                const right = plan.join.right || {};
                const keys = (plan.join.keys || [])
                    .map(pair => ({
                        leftColumn: String(pair.left_column || '').trim().toUpperCase(),
                        rightColumn: String(pair.right_column || '').trim().toUpperCase(),
                    }))
                    .filter(pair => pair.leftColumn && pair.rightColumn);
                if (keys.length
                    && resolveSheet(Number(left.file_index), String(left.sheet || ''))
                    && resolveSheet(Number(right.file_index), String(right.sheet || ''))) {
                    join = {
                        left: {fileIndex: Number(left.file_index), sheet: String(left.sheet)},
                        right: {fileIndex: Number(right.file_index), sheet: String(right.sheet)},
                        keys,
                        type: plan.join.type === 'left' ? 'left' : 'inner',
                    };
                }
            }
            if (!join) operation = 'union';

            return {targetFields, assign, sourceRank, notes: plan.notes || [], operation, join};
        }

        function sourceRankOf(key) {
            return mapping?.sourceRank?.get(key) ?? Number.MAX_SAFE_INTEGER;
        }

        function columnKey(fileIndex, sheet, column) {
            return `${fileIndex}#${sheet}#${String(column).toUpperCase()}`;
        }

        function resolveSheet(fileIndex, sheetName) {
            return sourceFiles[fileIndex]?.sheets.find(sheet => sheet.name === sheetName) || null;
        }

        function listSheets() {
            const sheets = [];
            sourceFiles.forEach((file, fileIndex) => {
                file.sheets.forEach(sheet => {
                    sheets.push({fileIndex, fileName: file.fileName, name: sheet.name, sheetRef: sheet});
                });
            });
            return sheets;
        }

        function refMatchesSide(ref, side) {
            return ref.file_index === side.fileIndex && ref.sheet === side.sheet;
        }

        function firstHeaderColumn(side) {
            const sheet = resolveSheet(side.fileIndex, side.sheet);
            if (!sheet) return 'A';
            const maxCol = Math.min(sheet.maxCol || 0, 60);
            for (let col = 1; col <= maxCol; col++) {
                if (String(sheet.rows.get(sheet.headerRow)?.get(col) || '').trim()) {
                    return kit.columnLetters(col);
                }
            }
            return 'A';
        }

        // 在两个指定 sheet 之间挑默认匹配键：优先用证据里的最优重合列对。
        function defaultKeysBetween(left, right) {
            const overlaps = lastEvidence?.overlaps || [];
            const match = overlaps.find(pair =>
                (refMatchesSide(pair.a, left) && refMatchesSide(pair.b, right))
                || (refMatchesSide(pair.a, right) && refMatchesSide(pair.b, left)));
            if (match) {
                const leftRef = refMatchesSide(match.a, left) ? match.a : match.b;
                const rightRef = refMatchesSide(match.a, left) ? match.b : match.a;
                return [{leftColumn: leftRef.column, rightColumn: rightRef.column}];
            }
            return [{leftColumn: firstHeaderColumn(left), rightColumn: firstHeaderColumn(right)}];
        }

        function defaultJoinConfig() {
            const sheets = listSheets();
            if (sheets.length < 2) return null;
            const best = (lastEvidence?.overlaps || [])[0];
            if (best) {
                const rowsOf = ref => {
                    const sheet = resolveSheet(ref.file_index, ref.sheet);
                    return sheet ? Math.max(0, sheet.maxRow - sheet.headerRow) : 0;
                };
                const [left, right] = rowsOf(best.a) >= rowsOf(best.b) ? [best.a, best.b] : [best.b, best.a];
                return {
                    left: {fileIndex: left.file_index, sheet: left.sheet},
                    right: {fileIndex: right.file_index, sheet: right.sheet},
                    keys: [{leftColumn: left.column, rightColumn: right.column}],
                    type: 'inner',
                };
            }
            const left = {fileIndex: sheets[0].fileIndex, sheet: sheets[0].name};
            const right = {fileIndex: sheets[1].fileIndex, sheet: sheets[1].name};
            return {left, right, keys: defaultKeysBetween(left, right), type: 'inner'};
        }

        function sheetLabel(side) {
            const file = sourceFiles[side.fileIndex];
            const fileName = shorten(file?.fileName || `文件${side.fileIndex + 1}`, 18);
            const multiSheet = (file?.sheets.length || 0) > 1;
            return multiSheet ? `${fileName}·${side.sheet}` : fileName;
        }

        function headerOf(sheet, letter) {
            const value = String(sheet.rows.get(sheet.headerRow)?.get(mergeKit.letterToColumn(letter)) || '').trim();
            return value || `${letter} 列`;
        }

        function joinKeysToCols(keys) {
            return keys.map(pair => ({
                leftCol: mergeKit.letterToColumn(pair.leftColumn),
                rightCol: mergeKit.letterToColumn(pair.rightColumn),
            }));
        }

        // 一句人话的计划摘要 + 匹配预检（本地全量数据实时计算）。
        function planSummaryText() {
            if (!mapping) return '';
            const fieldCount = mapping.targetFields.length;
            if (mapping.operation === 'join' && mapping.join) {
                const join = mapping.join;
                const leftSheet = resolveSheet(join.left.fileIndex, join.left.sheet);
                const rightSheet = resolveSheet(join.right.fileIndex, join.right.sheet);
                if (!leftSheet || !rightSheet) return '匹配合并的来源 sheet 不存在，请重新选择。';
                const keyText = join.keys
                    .map(pair => `「${headerOf(leftSheet, pair.leftColumn)} = ${headerOf(rightSheet, pair.rightColumn)}」`)
                    .join(' + ');
                const typeText = join.type === 'left' ? '匹配不上的行保留空值' : '只保留匹配上的行';
                const stats = mergeKit.computeJoinStats({leftSheet, rightSheet, keys: joinKeysToCols(join.keys)});
                return `计划：以「${sheetLabel(join.left)}」为主表，按 ${keyText} 去「${sheetLabel(join.right)}」查找，${typeText}，输出 ${fieldCount} 个字段。`
                    + `匹配预检：主表 ${stats.leftRows} 行中 ${stats.matchedLeft} 行能匹配上；被查表 ${stats.rightKeyCount} 个键里 ${stats.usedRightKeys} 个被用到。`;
            }
            return `计划：把所有来源 sheet 的行上下堆叠成一张表，输出 ${fieldCount} 个字段。`;
        }

        function sheetOptionsHtml(selected) {
            return listSheets().map(item => {
                const value = `${item.fileIndex}#${item.name}`;
                const isSelected = selected.fileIndex === item.fileIndex && selected.sheet === item.name;
                return `<option value="${escapeHtml(value)}" ${isSelected ? 'selected' : ''}>${escapeHtml(`${shorten(item.fileName, 18)} [${item.name}]`)}</option>`;
            }).join('');
        }

        function columnOptionsHtml(side, selectedLetter) {
            const sheet = resolveSheet(side.fileIndex, side.sheet);
            if (!sheet) return '';
            const options = [];
            const maxCol = Math.min(sheet.maxCol || 0, 60);
            for (let col = 1; col <= maxCol; col++) {
                const letter = kit.columnLetters(col);
                const header = String(sheet.rows.get(sheet.headerRow)?.get(col) || '').trim();
                if (!header) continue;
                options.push(`<option value="${letter}" ${letter === selectedLetter ? 'selected' : ''}>${escapeHtml(`${letter} ${shorten(header, 12)}`)}</option>`);
            }
            return options.join('');
        }

        function renderPlanPanel() {
            if (!planPanel || !mapping) return;
            const isJoin = mapping.operation === 'join' && mapping.join;

            let joinEditor = '';
            if (isJoin) {
                const join = mapping.join;
                const keyRows = join.keys.map((pair, index) => `
                    <div class="merge-join-keyrow">
                        <select data-join-key-left="${index}">${columnOptionsHtml(join.left, pair.leftColumn)}</select>
                        <span class="merge-join-eq">=</span>
                        <select data-join-key-right="${index}">${columnOptionsHtml(join.right, pair.rightColumn)}</select>
                        ${join.keys.length > 1 ? `<button type="button" class="excel-text-btn" data-join-key-remove="${index}">移除</button>` : ''}
                    </div>
                `).join('');
                joinEditor = `
                    <div class="merge-join-grid">
                        <label>主表（保留它的行）
                            <select data-join-side="left">${sheetOptionsHtml(join.left)}</select>
                        </label>
                        <label>被查表（按键取它的值）
                            <select data-join-side="right">${sheetOptionsHtml(join.right)}</select>
                        </label>
                        <label>匹配方式
                            <select data-join-type>
                                <option value="inner" ${join.type === 'inner' ? 'selected' : ''}>只保留匹配上的行</option>
                                <option value="left" ${join.type === 'left' ? 'selected' : ''}>保留主表所有行</option>
                            </select>
                        </label>
                    </div>
                    <div class="merge-join-keys">
                        <span class="merge-join-keys-label">匹配键</span>
                        ${keyRows}
                        <button type="button" class="excel-mini-btn" data-join-key-add>+ 添加匹配键</button>
                    </div>
                `;
            }

            planPanel.classList.remove('hidden');
            planPanel.innerHTML = `
                <div class="merge-plan-row">
                    <label class="merge-plan-mode">合并方式
                        <select data-plan-operation>
                            <option value="union" ${isJoin ? '' : 'selected'}>堆叠合并（多表上下拼接）</option>
                            <option value="join" ${isJoin ? 'selected' : ''}>按键匹配（把一张表的信息接到另一张表的行上）</option>
                        </select>
                    </label>
                </div>
                ${joinEditor}
                <p class="merge-plan-text">${escapeHtml(planSummaryText())}</p>
            `;

            planPanel.querySelector('[data-plan-operation]')?.addEventListener('change', event => {
                if (event.target.value === 'join') {
                    mapping.join = mapping.join || defaultJoinConfig();
                    if (!mapping.join) {
                        event.target.value = 'union';
                        setStatus('按键匹配需要至少两个 sheet。', 'error');
                        return;
                    }
                    mapping.operation = 'join';
                    if (sourceColumnsOpt) sourceColumnsOpt.checked = false;
                } else {
                    mapping.operation = 'union';
                }
                renderPlanPanel();
            });

            planPanel.querySelectorAll('[data-join-side]').forEach(select => {
                select.addEventListener('change', () => {
                    const hashIndex = select.value.indexOf('#');
                    const side = {
                        fileIndex: Number(select.value.slice(0, hashIndex)),
                        sheet: select.value.slice(hashIndex + 1),
                    };
                    mapping.join[select.dataset.joinSide] = side;
                    mapping.join.keys = defaultKeysBetween(mapping.join.left, mapping.join.right);
                    renderPlanPanel();
                });
            });

            planPanel.querySelector('[data-join-type]')?.addEventListener('change', event => {
                mapping.join.type = event.target.value === 'left' ? 'left' : 'inner';
                renderPlanPanel();
            });

            planPanel.querySelectorAll('[data-join-key-left]').forEach(select => {
                select.addEventListener('change', () => {
                    mapping.join.keys[Number(select.dataset.joinKeyLeft)].leftColumn = select.value;
                    renderPlanPanel();
                });
            });
            planPanel.querySelectorAll('[data-join-key-right]').forEach(select => {
                select.addEventListener('change', () => {
                    mapping.join.keys[Number(select.dataset.joinKeyRight)].rightColumn = select.value;
                    renderPlanPanel();
                });
            });
            planPanel.querySelector('[data-join-key-add]')?.addEventListener('click', () => {
                mapping.join.keys.push({
                    leftColumn: firstHeaderColumn(mapping.join.left),
                    rightColumn: firstHeaderColumn(mapping.join.right),
                });
                renderPlanPanel();
            });
            planPanel.querySelectorAll('[data-join-key-remove]').forEach(btn => {
                btn.addEventListener('click', () => {
                    mapping.join.keys.splice(Number(btn.dataset.joinKeyRemove), 1);
                    if (!mapping.join.keys.length) {
                        mapping.join.keys = defaultKeysBetween(mapping.join.left, mapping.join.right);
                    }
                    renderPlanPanel();
                });
            });
        }

        function renderMapping() {
            if (!mapping || !mappingBody || !fieldChipsEl) return;
            mappingSection?.classList.remove('hidden');
            renderPlanPanel();
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
                    mapping.sourceRank?.delete(select.dataset.assignKey);
                    select.closest('tr')?.classList.toggle('merge-row-ignored', !select.value);
                });
            });
        }

        function mergeTables() {
            if (mapping.operation === 'join' && mapping.join) {
                return mergeJoinTables();
            }
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
                            if (mapping.assign.get(key) === field.id) cols.push({col, rank: sourceRankOf(key)});
                        }
                        cols.sort((a, b) => (a.rank - b.rank) || (a.col - b.col));
                        return cols.map(item => item.col);
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

        function mergeJoinTables() {
            const dedupe = Boolean(dedupeOpt?.checked);
            const join = mapping.join;
            const leftSheet = resolveSheet(join.left.fileIndex, join.left.sheet);
            const rightSheet = resolveSheet(join.right.fileIndex, join.right.sheet);
            if (!leftSheet || !rightSheet) {
                throw new Error('匹配合并的主表或被查表不存在，请重新选择。');
            }
            if (!mapping.targetFields.length) {
                throw new Error('没有目标字段，请至少保留一个字段。');
            }

            const sides = [
                {side: 'left', fileIndex: join.left.fileIndex, sheet: leftSheet},
                {side: 'right', fileIndex: join.right.fileIndex, sheet: rightSheet},
            ];
            const fields = mapping.targetFields.map(field => {
                const entries = [];
                sides.forEach(({side, fileIndex, sheet}, sideIndex) => {
                    const maxCol = Math.min(sheet.maxCol || 0, 60);
                    for (let col = 1; col <= maxCol; col++) {
                        const key = columnKey(fileIndex, sheet.name, kit.columnLetters(col));
                        if (mapping.assign.get(key) === field.id) {
                            entries.push({side, col, rank: sourceRankOf(key), tie: sideIndex * 1000 + col});
                        }
                    }
                });
                entries.sort((a, b) => (a.rank - b.rank) || (a.tie - b.tie));
                return {name: field.name, sources: entries.map(({side, col}) => ({side, col}))};
            });
            if (!fields.some(field => field.sources.length)) {
                throw new Error('目标字段没有映射到主表或被查表的任何列，请先在归类表里调整。');
            }

            const result = mergeKit.runJoinMerge({
                leftSheet,
                rightSheet,
                keys: joinKeysToCols(join.keys),
                joinType: join.type,
                fields,
                dedupe,
            });
            if (!result.rows.length) {
                throw new Error('没有匹配出任何数据行，请检查匹配键和字段归类。');
            }

            return {headers: result.headers, rows: result.rows, sheetCount: 2, dropped: result.dropped, joinStats: result.stats};
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
                'table-tidy': document.querySelector('#tableTidyPanel'),
                'table-stats': document.querySelector('#tableStatsPanel'),
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

    function letterToColumn(letters) {
        let col = 0;
        String(letters || '').trim().toUpperCase().split('').forEach(ch => {
            col = col * 26 + (ch.charCodeAt(0) - 64);
        });
        return col;
    }

    // 匹配键归一化：电话/单号常被 Excel 存成数字，去掉小数尾巴再比较。
    function normalizeKeyValue(value) {
        let text = String(value ?? '').trim();
        if (/^\d+\.0+$/.test(text)) text = text.replace(/\.0+$/, '');
        return text.toLowerCase();
    }

    function rowHasValue(cells) {
        if (!cells) return false;
        for (const value of cells.values()) {
            if (String(value ?? '').trim() !== '') return true;
        }
        return false;
    }

    function collectColumnValues(sheet, col, cap = 20000) {
        const set = new Set();
        let nonEmpty = 0;
        for (let row = sheet.headerRow + 1; row <= sheet.maxRow; row++) {
            const value = normalizeKeyValue(sheet.rows.get(row)?.get(col));
            if (!value) continue;
            nonEmpty++;
            if (set.size < cap) set.add(value);
        }
        return {set, nonEmpty};
    }

    function detectValueKind(values) {
        if (!values.length) return 'empty';
        const counts = {phone: 0, longid: 0, code: 0, number: 0, date: 0, text: 0};
        values.forEach(raw => {
            const t = String(raw).trim();
            if (/^1[3-9]\d{9}$/.test(t)) counts.phone++;
            else if (/^\d{4}[-/年.]\d{1,2}([-/月.]\d{1,2})?/.test(t)) counts.date++;
            else if (/^\d{6,}$/.test(t)) counts.longid++;
            else if (/^-?\d+(\.\d+)?$/.test(t)) counts.number++;
            else if (t.length >= 5 && /^[a-z0-9\-_]+$/i.test(t) && /[a-z]/i.test(t) && /\d/.test(t)) counts.code++;
            else counts.text++;
        });
        let best = 'text';
        let bestCount = -1;
        Object.keys(counts).forEach(kind => {
            if (counts[kind] > bestCount) {
                best = kind;
                bestCount = counts[kind];
            }
        });
        return bestCount / values.length >= 0.8 ? best : 'mixed';
    }

    // candidates: [{ref: {file_index, sheet, column, header}, sheetId, set}]
    function computeKeyOverlaps(candidates, maxPairs = 12) {
        const pairs = [];
        for (let i = 0; i < candidates.length; i++) {
            for (let j = i + 1; j < candidates.length; j++) {
                const a = candidates[i];
                const b = candidates[j];
                if (a.sheetId === b.sheetId) continue;
                const [small, large] = a.set.size <= b.set.size ? [a, b] : [b, a];
                let overlap = 0;
                small.set.forEach(value => {
                    if (large.set.has(value)) overlap++;
                });
                if (overlap < 3) continue;
                const coverage = overlap / Math.max(1, small.set.size);
                if (coverage < 0.2) continue;
                pairs.push({
                    a: a.ref,
                    b: b.ref,
                    overlap,
                    a_unique: a.set.size,
                    b_unique: b.set.size,
                    coverage: Math.round(coverage * 100) / 100,
                });
            }
        }
        pairs.sort((x, y) => (y.coverage - x.coverage) || (y.overlap - x.overlap));
        return pairs.slice(0, maxPairs);
    }

    // 多键时任一部分为空就视为无键，避免「空=空」误配。
    function buildJoinKey(cells, cols) {
        const parts = cols.map(col => normalizeKeyValue(cells?.get(col)));
        return parts.every(part => part !== '') ? parts.join('\u0001') : null;
    }

    function indexRightRows(rightSheet, rightCols) {
        const index = new Map();
        let rightRows = 0;
        for (let row = rightSheet.headerRow + 1; row <= rightSheet.maxRow; row++) {
            const cells = rightSheet.rows.get(row);
            if (!rowHasValue(cells)) continue;
            rightRows++;
            const key = buildJoinKey(cells, rightCols);
            if (key === null) continue;
            if (!index.has(key)) index.set(key, []);
            index.get(key).push(cells);
        }
        return {index, rightRows};
    }

    // keys: [{leftCol, rightCol}] 列序号
    function computeJoinStats({leftSheet, rightSheet, keys}) {
        const leftCols = keys.map(k => k.leftCol);
        const rightCols = keys.map(k => k.rightCol);
        const {index, rightRows} = indexRightRows(rightSheet, rightCols);
        let leftRows = 0;
        let matchedLeft = 0;
        const usedRightKeys = new Set();
        for (let row = leftSheet.headerRow + 1; row <= leftSheet.maxRow; row++) {
            const cells = leftSheet.rows.get(row);
            if (!rowHasValue(cells)) continue;
            leftRows++;
            const key = buildJoinKey(cells, leftCols);
            if (key !== null && index.has(key)) {
                matchedLeft++;
                usedRightKeys.add(key);
            }
        }
        return {leftRows, rightRows, matchedLeft, rightKeyCount: index.size, usedRightKeys: usedRightKeys.size};
    }

    // fields: [{name, sources: [{side: 'left'|'right', col}]}]，每行取第一个非空来源。
    function runJoinMerge({leftSheet, rightSheet, keys, joinType, fields, dedupe}) {
        const leftCols = keys.map(k => k.leftCol);
        const rightCols = keys.map(k => k.rightCol);
        const {index, rightRows} = indexRightRows(rightSheet, rightCols);

        const rows = [];
        const seen = new Set();
        let dropped = 0;
        let leftRows = 0;
        let matchedLeft = 0;
        const usedRightKeys = new Set();

        for (let row = leftSheet.headerRow + 1; row <= leftSheet.maxRow; row++) {
            const leftCells = leftSheet.rows.get(row);
            if (!rowHasValue(leftCells)) continue;
            leftRows++;

            const key = buildJoinKey(leftCells, leftCols);
            const matches = key !== null ? (index.get(key) || []) : [];
            if (matches.length) {
                matchedLeft++;
                usedRightKeys.add(key);
            } else if (joinType !== 'left') {
                continue;
            }

            (matches.length ? matches : [null]).forEach(rightCells => {
                const values = fields.map(field => {
                    for (const source of field.sources) {
                        const cells = source.side === 'left' ? leftCells : rightCells;
                        const value = String(cells?.get(source.col) ?? '').trim();
                        if (value) return value;
                    }
                    return '';
                });
                if (values.every(value => value === '')) return;
                if (dedupe) {
                    const dedupeKey = values.join('\u0001');
                    if (seen.has(dedupeKey)) {
                        dropped++;
                        return;
                    }
                    seen.add(dedupeKey);
                }
                rows.push(values);
            });
        }

        return {
            headers: fields.map(f => f.name),
            rows,
            dropped,
            stats: {
                leftRows,
                rightRows,
                matchedLeft,
                unmatchedLeft: leftRows - matchedLeft,
                rightKeyCount: index.size,
                usedRightKeys: usedRightKeys.size,
                joinType,
            },
        };
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

    window.TableMergeKit = {
        buildXlsxBlob,
        columnLetters: colLetters,
        letterToColumn,
        normalizeKeyValue,
        detectValueKind,
        collectColumnValues,
        computeKeyOverlaps,
        computeJoinStats,
        runJoinMerge,
    };
})();
