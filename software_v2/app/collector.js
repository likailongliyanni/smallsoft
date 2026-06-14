/*
 * 采集引擎（页面 → 表格）核心算法
 * ================================
 * 与现有 inject.js（录制"写入"操作）方向相反：这里负责"读取"页面信息。
 *
 * 核心能力：用户在采集模式下点选一个字段元素，自动识别整页的「重复记录结构」
 * （列表/卡片/表格行），把所有同结构记录的对应字段抓成多行多列。
 *
 * 设计原则：
 *   - 纯前端、零依赖，可被 Playwright page.evaluate 注入，也可在测试 HTML 里直接调。
 *   - 不写死任何站点/业务字段，只靠 DOM 结构 + 元素特征推断。
 *   - 字段名优先用页面语义（aria-label / 表头 / 邻近文本），拿不到再兜底。
 *
 * 暴露：window.__hbfCollector
 *   pickField(el)              点选一个元素 → {fieldSelector, label, attr, sample}
 *   inferRepeat(el)            从元素推断重复记录结构 → {containerSelector, count} | null
 *   extract(containerSel, fields)  按容器 + 字段列表抓全页 → {headers, rows}
 *   autoTable(el)              点一个元素一键推断整表（容器 + 同结构兄弟里的可见字段）
 */
(function () {
    'use strict';

    // 框架通用 class（el-/ant-/…）不作为业务特征，避免选择器脆弱。
    const GENERIC_CLASS = /^(el-|ant-|n-|van-|is-|has-|v-|mui-|MuiBox|css-|chakra-|tw-)/;

    function bizClasses(el) {
        if (!el || typeof el.className !== 'string') return [];
        return el.className.trim().split(/\s+/).filter(c => c && c.length > 1 && !GENERIC_CLASS.test(c));
    }

    // 结构签名：同 tag + 同业务 class 集合视为「同一种记录」。
    function structSig(el) {
        return el.tagName + '|' + bizClasses(el).slice().sort().join('.');
    }

    function text(el) {
        return ((el && (el.innerText || el.textContent)) || '').trim().replace(/\s+/g, ' ');
    }

    function visible(el) {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        if (r.width < 1 || r.height < 1) return false;
        const s = getComputedStyle(el);
        return s.visibility !== 'hidden' && s.display !== 'none';
    }

    // 同结构兄弟：父节点下与 anc 同签名的子元素（>=2 即构成重复列表）。
    function sameSiblings(anc) {
        const p = anc.parentElement;
        if (!p) return [];
        const sig = structSig(anc);
        return Array.from(p.children).filter(c => structSig(c) === sig);
    }

    // 兄弟是否「纵向堆叠」（记录列表是上下排，不是左右排）。用来排除表格里同一行的
    // 多个 <td>（它们横向同 top）被误当成重复记录——记录单元应该是 <tr>。
    function isVerticalList(sibs) {
        if (sibs.length < 2) return false;
        const tops = sibs.slice(0, 5).map(s => Math.round(s.getBoundingClientRect().top));
        return new Set(tops).size >= 2;
    }

    // 从点选元素向上找「重复记录单元」：第一个拥有 >=2 个同结构、纵向堆叠且含内容的
    // 兄弟的祖先。表格场景记录单元是 <tr>，卡片场景是 .card/.item。
    function inferUnit(el) {
        let anc = el;
        const root = document.body;
        while (anc && anc !== root && anc.parentElement) {
            const sibs = sameSiblings(anc);
            if (sibs.length >= 2 && isVerticalList(sibs)) {
                const withText = sibs.filter(s => text(s).length > 0);
                // 至少一半兄弟有内容，排除「装饰性等高 div」误判。
                if (withText.length >= Math.max(2, sibs.length * 0.5)) {
                    return { unit: anc, records: sibs };
                }
            }
            anc = anc.parentElement;
        }
        return null;
    }

    // 容器选择器：能 querySelectorAll 选中所有记录单元。优先业务 class，
    // 表格行用 'tag'，再兜底用相对父节点的结构路径。
    function containerSelector(unit) {
        const tag = unit.tagName.toLowerCase();
        const biz = bizClasses(unit);
        if (biz.length) {
            const sel = tag + '.' + cssEscape(biz[0]);
            if (document.querySelectorAll(sel).length === sameSiblings(unit).length) return sel;
            // 业务 class 在别处也出现 → 加父级限定
            const p = unit.parentElement;
            const pBiz = p && bizClasses(p)[0];
            if (pBiz) return p.tagName.toLowerCase() + '.' + cssEscape(pBiz) + ' > ' + sel;
            return sel;
        }
        // 无业务 class（典型 <tr>）：用父容器 + 子 tag
        const p = unit.parentElement;
        const pBiz = p && bizClasses(p)[0];
        if (pBiz) return p.tagName.toLowerCase() + '.' + cssEscape(pBiz) + ' > ' + tag;
        if (p && p.tagName === 'TBODY') return 'tbody > ' + tag;
        return tag;
    }

    // 字段相对容器的选择器：沿 tag(.业务class) 链生成。无业务 class 且同级有多个同 tag
    // 兄弟时（典型 <td>）用 :nth-child 区分，否则表格只能取到第一列。
    function relSelector(el, unit) {
        if (el === unit) return ':scope';
        const parts = [];
        let cur = el;
        let guard = 0;
        while (cur && cur !== unit && guard++ < 8) {
            let part = cur.tagName.toLowerCase();
            const biz = bizClasses(cur)[0];
            if (biz) {
                part += '.' + cssEscape(biz);
            } else {
                const p = cur.parentElement;
                if (p) {
                    const sameTag = Array.from(p.children).filter(c => c.tagName === cur.tagName);
                    if (sameTag.length > 1) {
                        const idx = Array.prototype.indexOf.call(p.children, cur) + 1;
                        part += ':nth-child(' + idx + ')';
                    }
                }
            }
            parts.unshift(part);
            cur = cur.parentElement;
        }
        return parts.join(' > ') || ':scope';
    }

    // 取值：链接取 href、图片取 src，其余取文本。
    function attrOf(el) {
        const tag = el.tagName.toLowerCase();
        if (tag === 'a') return 'href';
        if (tag === 'img') return 'src';
        if (tag === 'input' || tag === 'textarea' || tag === 'select') return 'value';
        return 'text';
    }

    function valueOf(el, attr) {
        if (!el) return '';
        if (attr === 'text') return text(el);
        if (attr === 'href' || attr === 'src') return el.getAttribute(attr) || el[attr] || '';
        if (attr === 'value') return el.value != null ? String(el.value) : '';
        return el.getAttribute(attr) || '';
    }

    // 字段名推断：aria-label → 表头同列 <th> → 邻近 label/前置文本 → 占位符 → 列序。
    function fieldLabel(el, unit, index) {
        const al = el.getAttribute && el.getAttribute('aria-label');
        if (al && al.trim()) return clean(al);

        // 表格：用同列表头
        if (unit && unit.tagName === 'TR') {
            const cell = el.closest('td,th');
            if (cell && cell.parentElement) {
                const idx = Array.prototype.indexOf.call(cell.parentElement.children, cell);
                const table = unit.closest('table');
                const head = table && (table.querySelector('thead tr') || table.querySelector('tr'));
                const th = head && head.children[idx];
                if (th && text(th)) return clean(text(th));
            }
        }
        const ph = el.getAttribute && el.getAttribute('placeholder');
        if (ph) return clean(ph);
        // 业务 class 名兜底（title/price/sales 比"字段N"有意义，用户可再改名）。
        const biz = bizClasses(el)[0];
        if (biz) return biz;
        return '字段' + (index + 1);
    }

    function clean(s) {
        return String(s || '').trim().replace(/\s+/g, ' ').replace(/[:：*]+$/, '').slice(0, 30);
    }

    function cssEscape(s) {
        return String(s).replace(/([^a-zA-Z0-9_一-龥-])/g, '\\$1');
    }

    // ── 对外：点选单个字段 ──
    function pickField(el) {
        const found = inferUnit(el);
        if (!found) return null;
        const attr = attrOf(el);
        return {
            containerSelector: containerSelector(found.unit),
            fieldSelector: relSelector(el, found.unit),
            attr,
            label: fieldLabel(el, found.unit, 0),
            sample: valueOf(el, attr),
            recordCount: found.records.length,
        };
    }

    function inferRepeat(el) {
        const found = inferUnit(el);
        if (!found) return null;
        return { containerSelector: containerSelector(found.unit), count: found.records.length };
    }

    // ── 对外：按容器 + 字段抓全页 ──
    // fields: [{name, selector(相对容器), attr}]
    function extract(containerSel, fields) {
        const records = Array.from(document.querySelectorAll(containerSel));
        const headers = fields.map(f => f.name);
        const rows = [];
        records.forEach(rec => {
            const row = fields.map(f => {
                const target = (f.selector === ':scope') ? rec : rec.querySelector(f.selector);
                return valueOf(target, f.attr || (target ? attrOf(target) : 'text'));
            });
            if (row.some(v => String(v).trim() !== '')) rows.push(row);
        });
        return { headers, rows };
    }

    // ── 对外：点一个元素，一键推断「整条记录里的所有可见字段」 ──
    // 适合"我点一下这个商品块，把它每个信息都抓出来"。
    function autoTable(el) {
        const found = inferUnit(el);
        if (!found) return null;
        const unit = found.unit;
        // 候选字段：记录单元里"叶子级、有文本/链接/图片"的元素，去重同选择器。
        const fields = [];
        const seen = new Set();
        const leaves = unit.querySelectorAll('td, th, a, img, span, div, p, h1, h2, h3, h4');
        Array.prototype.forEach.call(leaves, node => {
            const tag = node.tagName.toLowerCase();
            // 图片只要有 src 就算（懒加载/未渲染尺寸也要抓）；其余要求可见。
            if (tag === 'img') {
                if (!node.getAttribute('src')) return;
            } else if (!visible(node)) {
                return;
            }
            // 只取"叶子或近叶子"：自身有直接文本，或是 a/img
            const hasOwnText = Array.from(node.childNodes).some(n => n.nodeType === 3 && n.textContent.trim());
            if (!(tag === 'a' || tag === 'img' || hasOwnText)) return;
            const sel = relSelector(node, unit);
            if (seen.has(sel)) return;
            // 链接/按钮有文字时取文字（用户点"标题"要的是文字不是 URL）；纯链接才取 href。
            let attr;
            if (tag === 'img') attr = 'src';
            else if (tag === 'a') attr = text(node) ? 'text' : 'href';
            else attr = 'text';
            const val = valueOf(node, attr);
            if (String(val).trim() === '') return;
            seen.add(sel);
            fields.push({ name: fieldLabel(node, unit, fields.length), selector: sel, attr });
        });
        if (!fields.length) return null;
        const containerSel = containerSelector(unit);
        const result = extract(containerSel, fields);
        return { containerSelector: containerSel, fields, ...result };
    }

    window.__hbfCollector = { pickField, inferRepeat, extract, autoTable,
        // 暴露内部函数便于测试
        _inferUnit: inferUnit, _structSig: structSig, _containerSelector: containerSelector, _relSelector: relSelector };
})();
