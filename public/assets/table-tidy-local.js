// 通用脏 Excel 智能结构化引擎（纯函数核心，无浏览器 / 框架依赖）。
//
// 设计原则：
//   1. 不绑定任何业务表（订单 / 商品 / 供应商…）。所有判断只依赖「数据形态」和
//      「表格结构信号」，业务字段名一律由内容 + 用户意图动态推断，绝不写死在逻辑里。
//   2. 引擎只消费一个「计划 plan」并在本地执行；plan 可以来自后端 AI，也可以由
//      buildLocalPlan 用本地启发式兜底。两条路径产物结构完全一致。
//   3. 仅含语义「数据类型」探测（电话 / 日期 / 金额 / 身份证…）——这是跨所有表通用的
//      格式特征，不是业务字段。角色噪声词（合计 / 备注 / 制表人…）是「结构角色」级别的
//      通用提示，且可被 plan.noiseHints 覆盖，从不单独决定一行的去留。
//
// 浏览器里挂在 window.TableTidyKit；Node 里 module.exports 同一对象，便于无头单测。
(function () {
    'use strict';

    // ───────────────────────────── 基础工具 ─────────────────────────────

    function normText(value) {
        return String(value ?? '')
            .replace(/[​-‍﻿]/g, '') // 零宽字符
            .replace(/　/g, ' ')               // 全角空格
            .trim();
    }

    function rowValues(cells, maxCol) {
        const out = [];
        const last = Math.max(maxCol || 0, cells ? Math.max(0, ...cells.keys()) : 0);
        for (let col = 1; col <= last; col++) out.push(normText(cells?.get(col)));
        return out;
    }

    function filledCount(cells) {
        if (!cells) return 0;
        let n = 0;
        for (const v of cells.values()) if (normText(v) !== '') n++;
        return n;
    }

    function isBlankRow(cells) {
        return filledCount(cells) === 0;
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

    function letterToColumn(letters) {
        let col = 0;
        String(letters || '').trim().toUpperCase().split('').forEach(ch => {
            col = col * 26 + (ch.charCodeAt(0) - 64);
        });
        return col;
    }

    function toHalfWidth(text) {
        return String(text ?? '').replace(/[！-～]/g, ch =>
            String.fromCharCode(ch.charCodeAt(0) - 0xFEE0)).replace(/　/g, ' ');
    }

    // ─────────────────────── 1. 单元格语义类型探测 ───────────────────────
    //
    // 通用「数据形态」分类，跨所有表通用，不含任何业务字段语义。

    const TYPE_PATTERNS = [
        ['phone', v => /^1[3-9]\d{9}$/.test(v)],
        ['idcard', v => /^\d{17}[\dXx]$/.test(v)],
        ['email', v => /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(v)],
        ['url', v => /^(https?:\/\/|www\.)[^\s]+$/i.test(v)],
        ['datetime', v => /^\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?[ T]\d{1,2}:\d{2}(:\d{2})?$/.test(v)],
        ['date', v => /^\d{4}[-/.年]\d{1,2}([-/.月]\d{1,2}日?)?$/.test(v)],
        ['amount', v => /^[¥￥$]\s?-?\d[\d,]*(\.\d+)?$/.test(v) || /^-?\d[\d,]*\.\d{2}$/.test(v) || /^-?\d[\d,]*(\.\d+)?\s?元$/.test(v)],
        ['percent', v => /^-?\d+(\.\d+)?%$/.test(v)],
        ['integer', v => /^-?\d{1,11}$/.test(v) && !/^0\d/.test(v)],
        ['longid', v => /^\d{12,}$/.test(v)],
        ['decimal', v => /^-?\d+\.\d+$/.test(v)],
        ['code', v => v.length >= 4 && /^[A-Za-z0-9][A-Za-z0-9\-_]*$/.test(v) && /[A-Za-z]/.test(v) && /\d/.test(v)],
    ];

    function detectCellType(value) {
        const v = normText(value);
        if (v === '') return 'empty';
        for (const [name, test] of TYPE_PATTERNS) {
            if (test(v)) return name;
        }
        return 'text';
    }

    // 把细类型归并到「家族」，做类型相容性判断时用（integer/decimal/amount 都算 number 家族）。
    const TYPE_FAMILY = {
        phone: 'id', idcard: 'id', longid: 'id', code: 'id',
        amount: 'number', integer: 'number', decimal: 'number', percent: 'number',
        date: 'date', datetime: 'date',
        email: 'contact', url: 'contact',
        text: 'text', empty: 'empty',
        // 家族名自映射，使 typeFamily 幂等：字段类型既可能是细类型也可能已是家族。
        id: 'id', number: 'number', contact: 'contact',
    };

    function typeFamily(type) {
        return TYPE_FAMILY[type] || 'text';
    }

    // 一列的形态画像：主类型 + 纯度 + 非空数 + 唯一值数。用于推断字段类型和置信度。
    function profileColumn(values) {
        const counts = {};
        let nonEmpty = 0;
        const seen = new Set();
        values.forEach(raw => {
            const v = normText(raw);
            if (v === '') return;
            nonEmpty++;
            seen.add(v.toLowerCase());
            const fam = typeFamily(detectCellType(v));
            counts[fam] = (counts[fam] || 0) + 1;
        });
        let type = 'text';
        let best = -1;
        Object.entries(counts).forEach(([fam, n]) => {
            if (n > best) { best = n; type = fam; }
        });
        return {
            type: nonEmpty ? type : 'empty',
            purity: nonEmpty ? best / nonEmpty : 0,
            nonEmpty,
            unique: seen.size,
            uniqueRatio: nonEmpty ? seen.size / nonEmpty : 0,
        };
    }

    // ─────────────────────── 合并单元格展开（预处理） ───────────────────────
    //
    // xlsx 里合并单元格只有左上角格子有值，区域内其它格子是空的。纵向合并（供应商/客户/
    // 日期列合并若干行）若不展开，下方行的该列会缺值 → 丢数据或错位。这里把左上角的值
    // 复制到合并区内的空格。**只展开纵向合并（bottom>top）**：纯横向合并（标题/表头跨列，
    // bottom===top）不展开，否则会把标题铺满整行、干扰区域识别。
    function expandMerges(sheet) {
        const merges = sheet.merges || [];
        if (!merges.length) return sheet;

        const rows = new Map();
        for (const [r, cells] of sheet.rows) rows.set(r, new Map(cells));

        merges.forEach(m => {
            if (m.bottom <= m.top) return; // 纯横向合并不展开
            const value = normText(rows.get(m.top)?.get(m.left));
            if (value === '') return;
            for (let r = m.top; r <= m.bottom; r++) {
                for (let c = m.left; c <= m.right; c++) {
                    if (r === m.top && c === m.left) continue;
                    const row = rows.get(r) || new Map();
                    if (normText(row.get(c)) === '') row.set(c, value);
                    rows.set(r, row);
                }
            }
        });

        return { ...sheet, rows };
    }

    // ─────────────────────── 2. 行画像 / 表结构画像 ───────────────────────

    function profileSheet(sheet) {
        const rowProfiles = [];
        for (let row = 1; row <= sheet.maxRow; row++) {
            const cells = sheet.rows.get(row);
            const values = rowValues(cells, sheet.maxCol);
            const filled = values.filter(v => v !== '').length;
            const fams = {};
            values.forEach(v => {
                if (v === '') return;
                const fam = typeFamily(detectCellType(v));
                fams[fam] = (fams[fam] || 0) + 1;
            });
            rowProfiles.push({
                row,
                filled,
                ratio: sheet.maxCol ? filled / sheet.maxCol : 0,
                families: fams,
                // 「像表头」：以文本为主、几乎不含数字、且单元格各不相同。
                headerLikeness: headerLikeness(values, fams, filled),
            });
        }
        return { rowProfiles, colCount: sheet.maxCol, rowCount: sheet.maxRow };
    }

    function headerLikeness(values, fams, filled) {
        if (filled < 2) return 0;
        const texty = (fams.text || 0);
        const numbery = (fams.number || 0) + (fams.id || 0) + (fams.date || 0);
        const distinct = new Set(values.filter(Boolean).map(v => v.toLowerCase())).size;
        const textRatio = texty / filled;
        const distinctRatio = distinct / filled;
        // 文本占比高、唯一度高、数字占比低 => 越像表头。
        return Math.max(0, textRatio * 0.6 + distinctRatio * 0.4 - numbery / Math.max(filled, 1) * 0.5);
    }

    // ─────────────────────── 3. 有效数据区域 / 表头识别 ───────────────────────
    //
    // 用「空行切块」把一个 sheet 切成多个块；每块内找表头行（形态得分 × 宽度权重，
    // 防止「导出人 / 合计」这类两三格的标签行冒充表头）。关键原则：**任何一行都不能
    // 静默丢失**——表头上方的行若上面已有区域，就是上一个表的续表行（extraRows），
    // 否则是标题/说明区（leadingRows）；整块找不到表头时同理。

    function detectRegions(sheet, profile) {
        profile = profile || profileSheet(sheet);
        const rp = profile.rowProfiles;
        const blocks = [];
        let start = null;
        for (let i = 0; i < rp.length; i++) {
            const blank = rp[i].filled === 0;
            if (!blank && start === null) start = rp[i].row;
            if (blank && start !== null) {
                blocks.push([start, rp[i - 1].row]);
                start = null;
            }
        }
        if (start !== null) blocks.push([start, rp[rp.length - 1].row]);

        const regions = [];
        const pendingLead = [];
        blocks.forEach(([top, bottom]) => {
            const prev = regions[regions.length - 1] || null;
            const found = analyzeBlock(sheet, profile, top, bottom, prev);
            if (found) {
                if (prev) prev.extraRows.push(...found.preambleRows);
                else pendingLead.push(...found.preambleRows);
                regions.push(found.region);
            } else if (prev) {
                // 没有新表头的块：是上一个表的续表 / 尾部（合计、页脚），并入上一区域，
                // 由行分类决定每行去留——绝不静默丢弃。
                prev.extraRows.push(...rangeRows(sheet, top, bottom));
            } else {
                pendingLead.push(...rangeRows(sheet, top, bottom));
            }
        });

        if (regions.length && pendingLead.length) {
            regions[0].leadingRows.push(...pendingLead);
        }

        // 续表行并入后，按完整数据行重算各列形态画像（供字段推断和 AI 摘要）。
        regions.forEach(region => {
            if (!region.extraRows.length) return;
            region.extraRows.sort((a, b) => a - b);
            const rows = regionDataRows(region);
            region.columns = profileRegionColumns(sheet, region.headerRows, rows);
            region.dataRowCount = rows.length;
        });

        return regions;
    }

    function analyzeBlock(sheet, profile, top, bottom, prevRegion) {
        const byRow = new Map(profile.rowProfiles.map(p => [p.row, p]));
        let maxFilled = 0;
        for (let row = top; row <= bottom; row++) {
            maxFilled = Math.max(maxFilled, byRow.get(row)?.filled || 0);
        }
        if (!maxFilled) return null;

        // 续表块判定：块的第一行非空行若是上一区域的重复表头，整块就是上一张表的延续，
        // 直接返回 null 让它并入上一区域的 extraRows——绝不能在剩余行里重新找表头，
        // 否则会把紧跟的第一条数据行误当成（多行）表头，吃掉一整行数据。
        if (prevRegion) {
            for (let row = top; row <= bottom; row++) {
                const cells = sheet.rows.get(row);
                if (isBlankRow(cells)) continue;
                if (overlapWithHeader(headerSignature(rowValues(cells, sheet.maxCol)), prevRegion.headerSignature) >= 0.8) {
                    return null;
                }
                break; // 只看块里第一行非空行
            }
        }

        // 表头候选：形态得分 × 宽度权重。两三个格的标签行（导出人 / 合计金额）即使全是
        // 文本也压不过铺满整行的真表头；合计 / 说明 / 分隔线不能当表头；与上一区域表头
        // 一致的是重复表头（续表标志），也不能开新区域。
        let headerRow = 0;
        let bestScore = 0.25; // 整块最高分低于该阈值视为没有表头
        const scanLimit = Math.min(bottom, top + 8);
        for (let row = top; row <= scanLimit; row++) {
            const p = byRow.get(row);
            if (!p || p.filled < 2) continue;
            const score = p.headerLikeness * (0.55 + 0.45 * p.filled / maxFilled) - (row - top) * 0.02;
            if (score <= bestScore) continue;
            const cells = sheet.rows.get(row);
            const cls = classifyRow(cells, { colCount: sheet.maxCol });
            if (['summary', 'note', 'separator', 'empty'].includes(cls.role)) continue;
            if (prevRegion
                && overlapWithHeader(headerSignature(rowValues(cells, sheet.maxCol)), prevRegion.headerSignature) >= 0.8) {
                continue;
            }
            bestScore = score;
            headerRow = row;
        }
        if (!headerRow) return null;

        // 多行表头：紧邻上方、偏文本且覆盖面相当的行并入（合并单元格的分组行）。
        // 覆盖面要求 >= 表头行的 30%，防止把「供应商：xxx」这类标签行拼进表头。
        const headerFilled = byRow.get(headerRow).filled;
        const headerRows = [headerRow];
        for (let row = headerRow - 1; row >= top; row--) {
            const p = byRow.get(row);
            if (p && p.filled >= 2 && p.filled >= headerFilled * 0.3 && p.headerLikeness > 0.3) {
                headerRows.unshift(row);
            } else break;
        }

        const dataTop = headerRow + 1;
        if (dataTop > bottom) return null; // 纯表头块，没数据。

        const dataRows = rangeRows(sheet, dataTop, bottom);
        const columns = profileRegionColumns(sheet, headerRows, dataRows);
        if (!columns.length) return null;

        return {
            preambleRows: rangeRows(sheet, top, headerRows[0] - 1),
            region: {
                top, bottom,
                headerRows,
                headerRow,
                dataTop, dataBottom: bottom,
                columns,
                dataRowCount: dataRows.length,
                headerSignature: headerSignature(columns.map(c => c.header)),
                extraRows: [],
                leadingRows: [],
            },
        };
    }

    function rangeRows(sheet, from, to) {
        const rows = [];
        for (let row = from; row <= to; row++) {
            if (!isBlankRow(sheet.rows.get(row))) rows.push(row);
        }
        return rows;
    }

    function regionDataRows(region) {
        const rows = [];
        for (let row = region.dataTop; row <= region.dataBottom; row++) rows.push(row);
        rows.push(...(region.extraRows || []));
        return [...new Set(rows)].sort((a, b) => a - b);
    }

    function profileRegionColumns(sheet, headerRows, dataRows) {
        const columns = [];
        for (let col = 1; col <= sheet.maxCol; col++) {
            const header = joinHeaderCells(sheet, headerRows, col);
            const colValues = dataRows.map(row => normText(sheet.rows.get(row)?.get(col)));
            const prof = profileColumn(colValues);
            if (header === '' && prof.nonEmpty === 0) continue;
            columns.push({ col, letter: columnLetters(col), header, ...prof });
        }
        return columns;
    }

    // 多行表头按列纵向拼接（去重相邻重复，处理合并单元格留下的空格）。
    function joinHeaderCells(sheet, headerRows, col) {
        const parts = [];
        headerRows.forEach(row => {
            const v = normText(sheet.rows.get(row)?.get(col));
            if (v && parts[parts.length - 1] !== v) parts.push(v);
        });
        return parts.join('-');
    }

    function headerSignature(headers) {
        return headers.map(h => normalizeHeader(h)).filter(Boolean).join('|');
    }

    function normalizeHeader(text) {
        return toHalfWidth(String(text || '')).toLowerCase()
            .replace(/[\s_：:\-（）()/\\.、，,]+/g, '');
    }

    // ─────────────────────── 4. 行角色分类（有效数据 / 噪声 / 表头…） ───────────────────────
    //
    // 角色：empty / separator / repeated_header / summary / note / data
    // 结构信号为主，噪声词为「弱通用提示」且可覆盖，从不单独决定一行去留。

    const DEFAULT_NOISE_HINTS = {
        // 结构角色级别的通用词，不是业务字段。可被 plan.noiseHints 覆盖 / 扩充。
        total: ['合计', '小计', '总计', '总额', '汇总', '总数', '共计', 'total', 'subtotal', 'sum', 'grand total'],
        note: ['备注', '说明', '注', '制表', '制表人', '审核', '审核人', '复核', '复核人', '填表', '填表人',
            '制单', '打印', '打印时间', '导出', '导出时间', '统计时间', '页脚', '签字', '签名', '盖章'],
        end: ['end', '结束', '以下空白', '以下为空', '本页无', '无内容', '完'],
    };

    function classifyRow(cells, ctx) {
        const colCount = ctx.colCount || 1;
        const values = rowValues(cells, colCount);
        const filled = values.filter(v => v !== '').length;
        if (filled === 0) return role('empty', 1, ['空行']);

        const joined = values.join('');
        const hints = ctx.noiseHints || DEFAULT_NOISE_HINTS;

        // 分隔线：整行只有重复符号。
        if (/^[-=_*~·•.—–\s]+$/.test(joined) && joined.length >= 2) {
            return role('separator', 0.95, ['分隔线']);
        }

        // 重复表头：归一化后与本区域表头签名一致。
        if (ctx.headerSignature) {
            const sig = headerSignature(values);
            if (sig && sig === ctx.headerSignature) return role('repeated_header', 0.95, ['与表头一致']);
            // 部分重复：填充少且每个非空值都命中表头词。
            if (filled >= 2 && overlapWithHeader(sig, ctx.headerSignature) >= 0.8) {
                return role('repeated_header', 0.8, ['疑似重复表头']);
            }
        }

        const firstText = values.find(v => v !== '') || '';
        const labelCells = values.filter(v => v !== '');

        // 合计 / 小计行：有「合计」类标签，且其余非空单元格基本是数字。
        if (containsHint(joined, hints.total)) {
            const nums = labelCells.filter(v => typeFamily(detectCellType(v)) === 'number').length;
            const labels = labelCells.filter(v => containsHint(v, hints.total)).length;
            if (filled <= Math.ceil(colCount / 2) + 1 || nums >= Math.max(1, labelCells.length - labels)) {
                return role('summary', 0.85, ['合计/小计行']);
            }
        }

        // 备注 / 制表人 / 导出时间等页脚：填充极少且命中说明词，或单格长文本。
        if (filled <= 2 && containsHint(joined, hints.note)) {
            return role('note', 0.8, ['说明/页脚行']);
        }
        if (filled === 1 && containsHint(firstText, hints.end)) {
            return role('note', 0.85, ['结束标记']);
        }
        if (filled === 1 && colCount >= 3 && firstText.length >= 12 && typeFamily(detectCellType(firstText)) === 'text') {
            return role('note', 0.6, ['整段说明文本']);
        }

        // 默认：数据行。置信度交给字段级打分细化。
        return role('data', 0.9, []);
    }

    function role(name, confidence, reasons) {
        return { role: name, confidence, reasons };
    }

    function containsHint(text, words) {
        const t = String(text || '').toLowerCase();
        return (words || []).some(w => t.includes(String(w).toLowerCase()));
    }

    function overlapWithHeader(sig, headerSig) {
        if (!sig || !headerSig) return 0;
        const a = sig.split('|').filter(Boolean);
        const b = new Set(headerSig.split('|').filter(Boolean));
        if (!a.length) return 0;
        return a.filter(x => b.has(x)).length / a.length;
    }

    // ─────────────────────── 5. 目标字段推断（本地启发式） ───────────────────────
    //
    // 没有 AI / 没有模板时的兜底：字段名取表头文本，类型取列形态。完全由内容驱动，
    // 不映射到任何预设业务字段表。AI 计划会覆盖这里，给出更规范的中文字段名。

    function inferSchema(region) {
        const usedNames = new Set();
        const fields = region.columns
            .filter(c => c.header !== '' || c.nonEmpty > 0)
            .map((c, idx) => {
                let name = c.header || `列${idx + 1}`;
                let uniq = name;
                let n = 2;
                while (usedNames.has(normalizeHeader(uniq))) uniq = `${name}_${n++}`;
                usedNames.add(normalizeHeader(uniq));
                return {
                    name: uniq,
                    type: c.type,
                    sourceCols: [c.col],
                    confidence: Math.round((0.4 + (c.header ? 0.3 : 0) + c.purity * 0.3) * 100) / 100,
                };
            });
        return { fields, headerRows: region.headerRows };
    }

    // ─────────────────────── 6. 通用数据清洗模块（按语义类型，非业务字段） ───────────────────────

    const cleaners = {
        trim: v => normText(v),

        collapseSpace: v => normText(v).replace(/\s+/g, ' '),

        stripSymbols: v => normText(v).replace(/[​-‍﻿]/g, '').replace(/\s+/g, ' ').trim(),

        // 换行 / 多空白压成单空格（处理从微信、网页粘贴进来的折行文本）。
        unwrap: v => normText(v).replace(/[\r\n]+/g, ' ').replace(/\s{2,}/g, ' ').trim(),

        toHalfWidth,

        // 日期标准化为 YYYY-MM-DD（带时间则保留）。无法解析返回原值。
        normalizeDate(v) {
            const s = normText(v);
            const m = s.match(/(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?/);
            if (!m) return s;
            const pad = n => String(n).padStart(2, '0');
            const date = `${m[1]}-${pad(m[2])}-${pad(m[3])}`;
            if (m[4] != null) return `${date} ${pad(m[4])}:${m[5]}:${m[6] || '00'}`;
            return date;
        },

        // 金额 / 数字标准化：去货币符号、千分位、单位「元」，全角转半角。返回纯数字串。
        normalizeAmount(v) {
            const s = toHalfWidth(normText(v)).replace(/[¥￥$,，\s]/g, '').replace(/元|人民币|rmb/gi, '');
            const m = s.match(/-?\d+(\.\d+)?/);
            return m ? m[0] : normText(v);
        },

        normalizeNumber(v) {
            return cleaners.normalizeAmount(v);
        },

        // 「同上 / 〃 / 同前」回填上一行同列的有效值。
        fillDitto(value, prev) {
            const v = normText(value);
            if (/^(同上|同前|〃|″|"|同|上同|do\.?)$/i.test(v)) return prev ?? '';
            return v;
        },

        // 数值 + 单位拆分：'500g' -> {value:'500', unit:'g'}。
        splitUnit(v) {
            const s = toHalfWidth(normText(v));
            const m = s.match(/^(-?\d+(?:\.\d+)?)\s*([^\d\s].*)?$/);
            if (!m) return { value: s, unit: '' };
            return { value: m[1], unit: (m[2] || '').trim() };
        },

        // 中文数字转阿拉伯数字（支持 〇零一二…十百千万，含「两」）。非纯中文数字原样返回。
        cnNumeralToArabic(v) {
            const s = normText(v);
            if (!/^[〇零一二两三四五六七八九十百千万亿]+$/.test(s)) return s;
            const digit = { '〇': 0, '零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9 };
            const unit = { '十': 10, '百': 100, '千': 1000 };
            const big = { '万': 10000, '亿': 100000000 };
            let total = 0, section = 0, current = 0;
            for (const ch of s) {
                if (ch in digit) {
                    current = digit[ch];
                } else if (ch in unit) {
                    section += (current || 1) * unit[ch];
                    current = 0;
                } else if (ch in big) {
                    section = (section + current) * big[ch];
                    total += section;
                    section = 0;
                    current = 0;
                }
            }
            return String(total + section + current);
        },
    };

    // 抽取器：从任意文本里提取结构化片段（通用，跨表通用）。
    const extractors = {
        phone: t => (String(t).match(/1[3-9]\d{9}/) || [])[0] || '',
        idcard: t => (String(t).match(/\d{17}[\dXx]/) || [])[0] || '',
        email: t => (String(t).match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/) || [])[0] || '',
        amounts: t => (String(t).match(/[¥￥$]\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?元/g) || [])
            .map(x => cleaners.normalizeAmount(x)),
        // 地址：含行政区划（市/区/县…）+ 道路/门牌特征（路/号/室…）的连续片段。
        // 不强制「省」开头，兼容直辖市（北京市朝阳区…）。
        address(t) {
            const m = String(t).match(/[一-龥][^\s，,；;]*?(?:市|区|县|州|镇|乡)[^\s，,；;]*?(?:路|街|道|巷|村|院|号|栋|幢|室|楼|单元)[^\s，,；;]*/);
            return m ? m[0] : '';
        },
    };

    // 按探测到的语义类型选清洗方法（字段 plan 也可显式指定 cleaners 列表）。
    function cleanByType(value, type) {
        switch (typeFamily(type)) {
            case 'date': return cleaners.normalizeDate(value);
            case 'number': return cleaners.normalizeAmount(value);
            default: return cleaners.collapseSpace(value);
        }
    }

    function applyCleaners(value, names, prev) {
        let v = value;
        (names || []).forEach(name => {
            if (name === 'fillDitto') v = cleaners.fillDitto(v, prev);
            else if (typeof cleaners[name] === 'function') v = cleaners[name](v);
        });
        return v;
    }

    // ─────────────────────── 7. 非结构化文本解析（微信 / 网页粘贴整段） ───────────────────────
    //
    // 把「张三 13800138000 北京市朝阳区xx路1号 球鞋 ¥299 备注…」一类自由文本
    // 拆成字段，每个抽取结果带一个粗置信度。通用抽取，不预设业务字段。

    function extractEntities(text) {
        const raw = cleaners.unwrap(text);
        const fields = {};
        const hits = [];

        const phone = extractors.phone(raw);
        if (phone) { fields.phone = phone; hits.push(1); }
        const idcard = extractors.idcard(raw);
        if (idcard) { fields.idcard = idcard; hits.push(1); }
        const email = extractors.email(raw);
        if (email) { fields.email = email; hits.push(1); }
        const amounts = extractors.amounts(raw);
        if (amounts.length) { fields.amount = amounts[0]; hits.push(0.7); }
        const address = extractors.address(raw);
        if (address) { fields.address = address; hits.push(0.8); }

        // 姓名启发式：开头 2~4 个连续中文，后面紧跟分隔 / 电话 / 标签。
        const nameMatch = raw.match(/^[\s,，:：]*([一-龥]{2,4})(?=[\s,，:：]|1[3-9]\d|$)/);
        if (nameMatch) { fields.name = nameMatch[1]; hits.push(0.5); }

        const confidence = hits.length ? Math.min(1, hits.reduce((a, b) => a + b, 0) / Math.max(2, hits.length)) : 0;
        return { fields, confidence: Math.round(confidence * 100) / 100, raw };
    }

    // ─────────────────────── 8. 字段级置信度打分 ───────────────────────

    function scoreCell(value, expectedType) {
        const v = normText(value);
        if (v === '') return 0;
        const fam = typeFamily(detectCellType(v));
        if (!expectedType || expectedType === 'text' || expectedType === 'empty') return 0.8;
        if (fam === typeFamily(expectedType)) return 1;
        if (fam === 'text') return 0.5;   // 期望数字 / 日期却是文本，可疑
        return 0.4;                       // 类型不符
    }

    // ─────────────────────── 9. 本地兜底计划 ───────────────────────

    function buildLocalPlan(sheet, options = {}) {
        sheet = expandMerges(sheet);
        const profile = profileSheet(sheet);
        const regions = detectRegions(sheet, profile);
        if (!regions.length) {
            return { regions: [], targetFields: [], rowFilter: defaultRowFilter(), notes: ['未识别到有效数据区域。'] };
        }
        const primary = regions.reduce((a, b) => (b.dataRowCount > a.dataRowCount ? b : a));

        // 目标字段 = 所有区域表头的并集（归一化去重）。本地不靠词典合并同义列——
        // 「收货人 / 买家 / 客户」这类语义合并交给 AI 计划；本地优先保证不错位、不丢列。
        const fields = [];
        const byNorm = new Map();
        regions.forEach(region => {
            region.columns.forEach(column => {
                const name = column.header || `列${column.letter}`;
                const norm = normalizeHeader(name);
                const existing = byNorm.get(norm);
                if (existing) {
                    if (!column.header && !existing.sourceLetters.includes(column.letter)) {
                        existing.sourceLetters.push(column.letter);
                    }
                    return;
                }
                const field = {
                    name,
                    type: column.type,
                    sourceHeaders: column.header ? [column.header] : [],
                    sourceLetters: column.header ? [] : [column.letter],
                    cleaners: defaultCleanersFor(column.type),
                    confidence: Math.round((0.4 + (column.header ? 0.3 : 0) + column.purity * 0.3) * 100) / 100,
                };
                byNorm.set(norm, field);
                fields.push(field);
            });
        });

        return {
            source: 'local-rule',
            regions,
            primaryRegionIndex: regions.indexOf(primary),
            targetFields: fields,
            rowFilter: defaultRowFilter(options),
            fillDitto: true,
            dedupe: false,
            noiseHints: options.noiseHints || DEFAULT_NOISE_HINTS,
            notes: ['本地规则按各区域表头取并集，不合并同义列；登录用 AI 规划可把「收货人/买家/客户」这类同义字段并成一列。'],
        };
    }

    function defaultRowFilter(options = {}) {
        return {
            dropRoles: options.dropRoles || ['empty', 'separator', 'repeated_header', 'summary', 'note'],
            minConfidence: options.minConfidence ?? 0.5,
        };
    }

    function defaultCleanersFor(type) {
        switch (typeFamily(type)) {
            case 'date': return ['fillDitto', 'normalizeDate'];
            case 'number': return ['fillDitto', 'normalizeAmount'];
            default: return ['fillDitto', 'collapseSpace'];
        }
    }

    // ─────────────────────── 10. 编排：把一个 sheet 整理成规范表 ───────────────────────
    //
    // 输出：干净表 + 异常表 + 被删行记录 + 字段映射 + 处理日志 + 置信度，
    // 完全对应「输出结果」验收项。

    function tidySheet(sheet, plan) {
        sheet = expandMerges(sheet);
        plan = plan || buildLocalPlan(sheet);
        const regions = plan.regions && plan.regions.length ? plan.regions : detectRegions(sheet);
        if (!regions.length) {
            return emptyResult(['未识别到有效数据区域。']);
        }

        const targetFields = (plan.targetFields && plan.targetFields.length)
            ? plan.targetFields
            : inferSchema(regions[plan.primaryRegionIndex || 0] || regions[0]).fields.map(f => ({
                name: f.name, type: f.type, sourceHeaders: [f.name], cleaners: defaultCleanersFor(f.type),
            }));

        const rowFilter = plan.rowFilter || defaultRowFilter();
        const headers = targetFields.map(f => f.name);
        const rows = [];
        const exceptions = [];
        const dropped = [];
        const log = [];
        const seen = new Set();
        let droppedDup = 0;

        regions.forEach((region, regionIdx) => {
            // 每个区域：把它自己的列映射到统一目标字段（按表头归一化匹配）。
            const colForField = mapRegionColumns(region, targetFields);
            const ctx = {
                colCount: sheet.maxCol,
                headerSignature: region.headerSignature,
                noiseHints: plan.noiseHints || DEFAULT_NOISE_HINTS,
            };
            const prevValues = {}; // 字段名 -> 上一行有效值，供 fillDitto

            // 表头上方的标题 / 说明区：按角色记录删除（带原因），绝不静默丢行。
            (region.leadingRows || []).forEach(row => {
                const cells = sheet.rows.get(row);
                const cls = classifyRow(cells, ctx);
                const role = cls.role === 'data' ? 'note' : cls.role;
                if (role === 'empty') return;
                dropped.push({
                    sheet: sheet.name, row, role,
                    reason: cls.role === 'data' ? '表头上方的标题/说明区' : cls.reasons.join('；'),
                    preview: rowValues(cells, sheet.maxCol).filter(Boolean).slice(0, 4).join(' | '),
                });
            });

            // 数据行 = 表头下方区间 + 并入的续表行（跨空行 / 跨小计的同表数据）。
            for (const row of regionDataRows(region)) {
                const cells = sheet.rows.get(row);
                const cls = classifyRow(cells, ctx);
                if (cls.role !== 'data') {
                    if ((rowFilter.dropRoles || []).includes(cls.role)) {
                        if (cls.role !== 'empty') {
                            dropped.push({ sheet: sheet.name, row, role: cls.role, reason: cls.reasons.join('；'),
                                preview: rowValues(cells, sheet.maxCol).filter(Boolean).slice(0, 4).join(' | ') });
                        }
                        continue;
                    }
                }

                // 抽字段值 + 清洗 + 打分。
                const record = [];
                const cellScores = [];
                targetFields.forEach(field => {
                    const cols = colForField.get(field.name) || [];
                    let raw = '';
                    for (const col of cols) {
                        const v = normText(cells?.get(col));
                        if (v) { raw = v; break; }
                    }
                    let value = applyCleaners(raw, field.cleaners, prevValues[field.name]);
                    if (value !== '') prevValues[field.name] = value;
                    record.push(value);
                    cellScores.push(value === '' ? 0 : scoreCell(value, field.type));
                });

                if (record.every(v => v === '')) continue;

                // 行置信度：非空字段打分的均值（对该行实际填了的字段负责）。
                const filledScores = cellScores.filter((_, i) => record[i] !== '');
                const conf = filledScores.length
                    ? Math.round(filledScores.reduce((a, b) => a + b, 0) / filledScores.length * 100) / 100
                    : 0;

                if (plan.dedupe) {
                    const k = record.join('');
                    if (seen.has(k)) { droppedDup++; continue; }
                    seen.add(k);
                }

                const meta = { _sheet: sheet.name, _row: row, _confidence: conf };
                if (conf < (rowFilter.minConfidence ?? 0.5)) {
                    exceptions.push({ values: record, ...meta, _reason: '字段类型与表头不符，置信度偏低，待人工确认' });
                } else {
                    rows.push(record);
                }
            }

            log.push(`区域${regionIdx + 1}：表头行 ${region.headerRows.join('+')}，数据行 ${region.dataTop}~${region.dataBottom}，` +
                `映射 ${[...colForField.values()].filter(v => v.length).length}/${targetFields.length} 字段。`);
        });

        // 落单行清扫（安全网）：理论上 detectRegions 已把每个非空行分进数据区 / 表头 /
        // 续表 / 标题区，这里兜住万一漏掉的行——噪声行计入被删记录，**像数据的行进异常表**，
        // 任何一行都不允许静默消失。
        const accounted = new Set();
        regions.forEach(r => {
            r.headerRows.forEach(hr => accounted.add(hr));
            for (let row = r.dataTop; row <= r.dataBottom; row++) accounted.add(row);
            (r.extraRows || []).forEach(row => accounted.add(row));
            (r.leadingRows || []).forEach(row => accounted.add(row));
        });
        for (let row = 1; row <= sheet.maxRow; row++) {
            if (accounted.has(row)) continue;
            const cells = sheet.rows.get(row);
            if (isBlankRow(cells)) continue;
            const cls = classifyRow(cells, { colCount: sheet.maxCol, noiseHints: plan.noiseHints || DEFAULT_NOISE_HINTS });
            const preview = rowValues(cells, sheet.maxCol).filter(Boolean).slice(0, 4).join(' | ');
            if (cls.role !== 'data') {
                if ((rowFilter.dropRoles || []).includes(cls.role) && cls.role !== 'empty') {
                    dropped.push({ sheet: sheet.name, row, role: cls.role, reason: cls.reasons.join('；'), preview });
                }
            } else {
                exceptions.push({
                    values: targetFields.map(() => ''),
                    _sheet: sheet.name, _row: row, _confidence: 0,
                    _reason: `不在任何识别出的表格区域内，请人工确认：${preview}`,
                });
            }
        }

        return {
            headers,
            rows,
            exceptions,
            dropped,
            droppedDup,
            log,
            fieldMap: targetFields.map(f => ({ name: f.name, type: f.type, sourceHeaders: f.sourceHeaders || [f.name] })),
            stats: {
                regions: regions.length,
                kept: rows.length,
                exceptions: exceptions.length,
                droppedRows: dropped.length,
                droppedDup,
            },
            notes: plan.notes || [],
        };
    }

    // 把一个区域的源列按表头归一化匹配到统一目标字段。**绝不按位置乱猜**：
    // 表头对不上的列宁可不映射（行会因空值多而落进异常表），也不能把另一段表的数据
    // 错位塞进别的字段——错位比缺失更糟。无表头的列按列字母对位（整表没表头的场景）。
    function mapRegionColumns(region, targetFields) {
        const map = new Map(targetFields.map(f => [f.name, []]));
        const byNorm = new Map();
        const byLetter = new Map();
        region.columns.forEach(c => {
            const key = normalizeHeader(c.header);
            if (key && !byNorm.has(key)) byNorm.set(key, c);
            byLetter.set(c.letter, c);
        });

        targetFields.forEach(field => {
            const wanted = [field.name, ...(field.sourceHeaders || [])].map(normalizeHeader).filter(Boolean);
            let col = null;
            for (const w of wanted) {
                if (byNorm.has(w)) { col = byNorm.get(w); break; }
            }
            if (!col) {
                for (const letter of field.sourceLetters || []) {
                    const cand = byLetter.get(letter);
                    if (cand && cand.header === '') { col = cand; break; }
                }
            }
            if (col) map.get(field.name).push(col.col);
        });
        return map;
    }

    function emptyResult(notes) {
        return {
            headers: [], rows: [], exceptions: [], dropped: [], droppedDup: 0,
            log: [], fieldMap: [], stats: { regions: 0, kept: 0, exceptions: 0, droppedRows: 0, droppedDup: 0 },
            notes: notes || [],
        };
    }

    function tidyWorkbook(workbook, planBySheet = {}) {
        const sheets = workbook.sheets.map(sheet => ({
            name: sheet.name,
            result: tidySheet(sheet, planBySheet[sheet.name]),
        }));
        return { sheets };
    }

    // 构造发给后端 AI 的轻量摘要：只含表头候选、列形态统计、少量样例和区域结构，
    // 绝不上报整列原值。和现有 image-extract / table-merge 的隐私口径一致。
    function buildTidySummary(sheet, options = {}) {
        sheet = expandMerges(sheet);
        const profile = profileSheet(sheet);
        const regions = detectRegions(sheet, profile);
        return {
            sheet_name: sheet.name,
            max_row: sheet.maxRow,
            max_col: sheet.maxCol,
            regions: regions.map(r => ({
                header_rows: r.headerRows,
                data_top: r.dataTop,
                data_bottom: r.dataBottom,
                data_row_count: r.dataRowCount,
                columns: r.columns.map(c => ({
                    column: c.letter,
                    header: c.header,
                    value_kind: c.type,
                    purity: Math.round(c.purity * 100) / 100,
                    non_empty: c.nonEmpty,
                    unique: c.unique,
                    samples: sampleColumn(sheet, c.col, r.dataTop, r.dataBottom, options.sampleSize || 5),
                })),
            })),
        };
    }

    function sampleColumn(sheet, col, top, bottom, limit) {
        const out = [];
        for (let row = top; row <= bottom && out.length < limit; row++) {
            const v = normText(sheet.rows.get(row)?.get(col));
            if (v) out.push(v.slice(0, 40));
        }
        return out;
    }

    const TableTidyKit = {
        // 基础
        normText, columnLetters, letterToColumn, toHalfWidth,
        // 类型探测
        detectCellType, typeFamily, profileColumn,
        // 结构
        expandMerges, profileSheet, detectRegions,
        // 行分类
        classifyRow, DEFAULT_NOISE_HINTS,
        // 字段推断
        inferSchema,
        // 清洗 / 抽取
        cleaners, extractors, cleanByType, extractEntities,
        // 置信度
        scoreCell,
        // 计划 / 编排
        buildLocalPlan, buildTidySummary, tidySheet, tidyWorkbook,
        // 内部可测
        normalizeHeader, headerSignature, mapRegionColumns,
    };

    if (typeof module !== 'undefined' && module.exports) module.exports = TableTidyKit;
    if (typeof window !== 'undefined') window.TableTidyKit = TableTidyKit;
})();
