@extends('layouts.app')

@section('title', '使用教程 - 好办法浏览器自动化')
@section('page', 'tutorial')

@section('content')

<style>
    .tut-wrap{max-width:1100px;margin:0 auto;padding:30px 24px 60px;color:#1f2937;line-height:1.7}
    .tut-wrap h1{font-size:32px;margin:0 0 8px;color:#0c4a6e}
    .tut-lead{color:#64748b;font-size:15px;margin:0 0 28px}
    .tut-toc{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:18px 22px;margin:0 0 30px}
    .tut-toc strong{color:#0c4a6e;display:block;margin-bottom:8px;font-size:13px;letter-spacing:0.5px}
    .tut-toc ol{margin:0;padding-left:22px;column-count:2;column-gap:36px;font-size:14px}
    .tut-toc ol li{margin:3px 0;break-inside:avoid}
    .tut-toc a{color:#2563eb;text-decoration:none}
    .tut-toc a:hover{text-decoration:underline}

    .tut-section{margin:50px 0;scroll-margin-top:20px}
    .tut-section h2{font-size:22px;color:#0c4a6e;margin:0 0 8px;display:flex;align-items:baseline;gap:10px}
    .tut-section h2 .tag{background:#0c4a6e;color:#fff;font-size:13px;padding:2px 10px;border-radius:14px;font-weight:600}
    .tut-section h3{font-size:17px;color:#1f2937;margin:20px 0 8px}
    .tut-section p{margin:8px 0;font-size:14.5px}

    .tut-section ul,.tut-section ol{padding-left:22px;margin:8px 0}
    .tut-section li{margin:4px 0;font-size:14.5px}

    .tut-card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 22px;margin:14px 0;
              box-shadow:0 1px 3px rgba(0,0,0,0.03)}
    .tut-callout{border-left:4px solid;padding:14px 16px;border-radius:6px;margin:14px 0;font-size:14px}
    .tut-callout.info{background:#eff6ff;border-color:#2563eb;color:#1e3a8a}
    .tut-callout.tip{background:#f0fdf4;border-color:#16a34a;color:#14532d}
    .tut-callout.warn{background:#fef3c7;border-color:#f59e0b;color:#78350f}
    .tut-callout.danger{background:#fef2f2;border-color:#dc2626;color:#7f1d1d}
    .tut-callout strong{display:block;margin-bottom:4px}

    .step-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin:14px 0}
    .step-grid .step-card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px 18px;
                          position:relative;padding-left:60px}
    .step-grid .step-card .num{position:absolute;left:18px;top:18px;width:30px;height:30px;border-radius:50%;
                                background:#0c4a6e;color:#fff;font-weight:700;display:flex;align-items:center;
                                justify-content:center;font-size:14px}
    .step-grid .step-card h4{margin:0 0 6px;font-size:15px;color:#0c4a6e}
    .step-grid .step-card p{margin:0;font-size:13px;color:#475569;line-height:1.6}

    code{background:#f1f5f9;padding:2px 8px;border-radius:4px;font-size:13px;color:#0f172a;
         font-family:Consolas,Menlo,monospace}
    pre{background:#1e293b;color:#e2e8f0;padding:14px 18px;border-radius:8px;overflow-x:auto;
        font-size:13px;line-height:1.6;margin:12px 0}
    pre code{background:transparent;color:inherit;padding:0}

    table.tut-tbl{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px;background:#fff}
    table.tut-tbl th,table.tut-tbl td{border:1px solid #e2e8f0;padding:9px 12px;text-align:left}
    table.tut-tbl th{background:#f1f5f9;font-weight:600;color:#0c4a6e}
    table.tut-tbl td code{font-size:12px}

    .pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600;margin-right:4px}
    .pill.green{background:#dcfce7;color:#166534}
    .pill.blue{background:#dbeafe;color:#1e40af}
    .pill.orange{background:#fed7aa;color:#9a3412}
    .pill.purple{background:#ede9fe;color:#5b21b6}
    .pill.gray{background:#e2e8f0;color:#475569}

    .faq{margin:10px 0}
    .faq summary{cursor:pointer;font-weight:600;font-size:15px;color:#0c4a6e;padding:12px 14px;
                 background:#f1f5f9;border-radius:8px;list-style:none;display:flex;align-items:center;gap:8px}
    .faq summary::-webkit-details-marker{display:none}
    .faq summary::before{content:"▸";transition:transform 0.2s}
    .faq[open] summary::before{transform:rotate(90deg)}
    .faq .ans{padding:12px 18px;font-size:14.5px;color:#374151;line-height:1.7}

    .hero-meta{display:flex;gap:18px;flex-wrap:wrap;margin:6px 0 22px;font-size:13px;color:#64748b}
    .hero-meta span{display:flex;align-items:center;gap:6px}

    .anchor-link{color:#cbd5e1;font-weight:400;text-decoration:none;margin-left:6px;font-size:14px}
    .anchor-link:hover{color:#0c4a6e}

    @media (max-width:680px){
        .tut-toc ol{column-count:1}
        .tut-section h2{font-size:19px}
    }
</style>

<div class="tut-wrap">

    <h1>📖 好办法浏览器自动化 - 使用教程</h1>
    <p class="tut-lead">要看视频教程可以抖音关注我 @叫狗子的狸花猫 </p>
    <div class="hero-meta">
        <span>📦 当前版本：v2.0 BETA-2</span>
        <span>⏱ 阅读时间：约 8 分钟</span>
        <span>💬 客服微信：18033086531</span>
    </div>

    {{-- 目录 --}}
    <div class="tut-toc">
        <strong>📋 教程目录</strong>
        <ol>
            <li><a href="#install">1. 下载与启动</a></li>
            <li><a href="#first-record">2. 录制第一个流程</a></li>
            <li><a href="#multi-session">3. 多次录制（v2.0 新功能）</a></li>
            <li><a href="#review">4. 整理步骤 + 生成脚本</a></li>
            <li><a href="#excel">5. 填写 Excel 数据表</a></li>
            <li><a href="#run">6. 运行自动化</a></li>
            <li><a href="#manual-takeover">7. 人工接管（步骤出错时）</a></li>
            <li><a href="#upload">8. 文件 / 图片上传（重要）</a></li>
            <li><a href="#tips">9. 录制小技巧</a></li>
            <li><a href="#faq">10. 常见问题</a></li>
            <li><a href="#contact">11. 反馈与支持</a></li>
        </ol>
    </div>

    {{-- 1 安装 --}}
    <section class="tut-section" id="install">
        <h2><span class="tag">1</span>下载与启动 <a class="anchor-link" href="#install">#</a></h2>
        <p>软件目前只支持 <strong>Windows 10 / 11 64 位</strong>，需要约 500MB 磁盘空间。</p>

        <div class="step-grid">
            <div class="step-card">
                <div class="num">1</div>
                <h4>下载压缩包</h4>
                <p>访问首页或下载页，点「立即下载」获取 RAR 压缩包（约 162MB）。</p>
            </div>
            <div class="step-card">
                <div class="num">2</div>
                <h4>右键解压</h4>
                <p>把 RAR 文件解压到任意目录（建议 <code>D:\</code> 或 <code>E:\</code>，路径不要带中文）。</p>
            </div>
            <div class="step-card">
                <div class="num">3</div>
                <h4>双击启动</h4>
                <p>找到「好办法自动化.exe」双击运行。首次启动会自动下载浏览器组件（约 200MB），耐心等待。</p>
            </div>
        </div>

        <div class="tut-callout warn">
            <strong>⚠ 杀毒软件可能误报</strong>
            软件未做代码签名，部分杀毒会拦截。请加入白名单后继续使用。本软件 100% 本地运行，不上传任何数据，可放心使用。
        </div>
    </section>

    {{-- 2 录制第一个流程 --}}
    <section class="tut-section" id="first-record">
        <h2><span class="tag">2</span>录制第一个流程 <a class="anchor-link" href="#first-record">#</a></h2>
        <p>录制是教 AI「这件事怎么做」的过程。整个过程像录屏幕，但软件会自动识别每个点击 / 输入。</p>

        <h3>录制步骤</h3>
        <div class="step-grid">
            <div class="step-card">
                <div class="num">1</div>
                <h4>进入「录制」tab</h4>
                <p>在软件顶部选「录制」，输入目标网址（如 <code>admincg.daoyeshan.com</code>）。</p>
            </div>
            <div class="step-card">
                <div class="num">2</div>
                <h4>选择录制次数</h4>
                <p>点「开始录制」会弹出选择框，<strong>建议根据复杂度选 1 / 3 / 5 次</strong>，详见第 3 节。</p>
            </div>
            <div class="step-card">
                <div class="num">3</div>
                <h4>在浏览器里正常操作</h4>
                <p>软件会弹出一个新浏览器（顶部有红色「🔴 录制中」工具栏），你正常点击、填表、选下拉就行。</p>
            </div>
            <div class="step-card">
                <div class="num">4</div>
                <h4>完成录制</h4>
                <p>做完所有动作后，点浏览器顶部的「✅ 完成」按钮，软件自动跳到「整理」页。</p>
            </div>
        </div>

        <h3>录制时的 5 条铁律</h3>
        <ul>
            <li><strong>动作间隔 3-5 秒</strong>：太快可能漏录，AI 也分不清是 1 步还是 2 步。</li>
            <li><strong>每个动作都要在浏览器里真实执行</strong>：不要鼠标悬停就期望软件录到，必须真正点击。</li>
            <li><strong>下拉菜单要展开 + 选择两步都做</strong>：先点开下拉，等选项出现再点选项。</li>
            <li><strong>少误点</strong>：录到的每一步将来都会被复现，多余的点击会拖慢运行。</li>
            <li><strong>需要截图作辅助时</strong>：把鼠标悬停到目标上 → 按 <code>Ctrl+Shift+X</code> → 然后再点击。</li>
        </ul>

        <div class="tut-callout tip">
            <strong>💡 小技巧</strong>
            录制过程中点错了不要紧 — 在浏览器顶部工具栏有「↶ 撤销」按钮，可以删除最后一步。
        </div>
    </section>

    {{-- 3 多次录制 --}}
    <section class="tut-section" id="multi-session">
        <h2><span class="tag">3</span>多次录制（v2.0 新功能） <a class="anchor-link" href="#multi-session">#</a></h2>

        <div class="tut-callout info">
            <strong>🌱 为什么需要多次录制？</strong>
            一次录制只能告诉 AI「这一次怎么做」，AI 不知道「下次同样的事会不会有变化」。<br>
            录 3-5 次同一任务，AI 能找到<strong>所有次都做的核心步骤</strong>，并自动剔除偶然操作（比如多点一下、不小心滚屏）。
        </div>

        <h3>怎么选录制次数</h3>
        <table class="tut-tbl">
            <thead>
                <tr><th style="width:80px">次数</th><th>适合场景</th><th>典型例子</th></tr>
            </thead>
            <tbody>
                <tr>
                    <td><span class="pill gray">1 次</span></td>
                    <td>简单流程（≤ 10 步），无文件上传</td>
                    <td>登录、查询、简单填表</td>
                </tr>
                <tr>
                    <td><span class="pill green">3 次（推荐）</span></td>
                    <td>中等复杂度，10-30 步</td>
                    <td>商品上架、多字段填表、有文件上传</td>
                </tr>
                <tr>
                    <td><span class="pill blue">5 次（最稳）</span></td>
                    <td>复杂流程，含素材库 / 网络相册</td>
                    <td>批量跑 100+ 次的核心流程、勾选大量图片</td>
                </tr>
            </tbody>
        </table>

        <h3>多次录制的注意事项</h3>
        <ul>
            <li><strong>每次操作顺序尽量一致</strong>：先点 A 再点 B，每次都先 A 后 B。</li>
            <li><strong>可以小幅变化</strong>：下拉选不同的项、填不同的金额、上传不同的图，AI 会自动识别这些是「Excel 数据列」。</li>
            <li><strong>不要中途加新步骤</strong>：比如第 1 次不点「保存草稿」，第 2 次又点了，AI 可能误判。</li>
            <li><strong>累了可以提前结束</strong>：每次结束都会弹「再录一次 / 提前结束」对话框，自由选择。</li>
        </ul>

        <div class="tut-callout warn">
            <strong>⚠ 别为了"凑次数"瞎录</strong>
            2 次精心的录制 比 5 次随便点击的效果好得多。质量永远比数量重要。
        </div>
    </section>

    {{-- 4 整理 --}}
    <section class="tut-section" id="review">
        <h2><span class="tag">4</span>整理步骤 + 生成脚本 <a class="anchor-link" href="#review">#</a></h2>

        <p>录完后软件自动跳到「整理」页。这里你可以：</p>
        <ul>
            <li><strong>取消勾选</strong>不想要的步骤（比如误点、调试时的额外动作）。</li>
            <li><strong>修改 Excel 列名</strong>：默认根据字段标签生成，比如「商品名称」「价格」，你可以改成更短的列名。</li>
            <li><strong>查看每步的截图</strong>：录制时用 <code>Ctrl+Shift+X</code> 截过的图会显示。</li>
            <li><strong>添加描述</strong>：告诉 AI 这步是什么意思，AI 生成脚本时会参考。</li>
        </ul>

        <h3>选择 AI 模型档位</h3>
        <p>「整理」页底部右下角有「AI 模型档位」下拉：</p>
        <table class="tut-tbl">
            <thead>
                <tr><th style="width:140px">档位</th><th>底层模型</th><th>速度</th><th>适合</th></tr>
            </thead>
            <tbody>
                <tr><td><span class="pill green">代码生成（默认）</span></td><td>qwen3-coder-plus</td><td>中</td><td>⭐ 大多数流程都用这个</td></tr>
                <tr><td><span class="pill blue">平衡</span></td><td>qwen3.6-plus</td><td>中</td><td>含截图分析时</td></tr>
                <tr><td><span class="pill orange">强档</span></td><td>qwen3-max</td><td>慢</td><td>非常复杂的流程，前几个不够准时</td></tr>
                <tr><td><span class="pill purple">快速</span></td><td>qwen3.6-flash</td><td>快</td><td>简单流程急用</td></tr>
            </tbody>
        </table>

        <p>点「<strong>生成脚本 + Excel 模板</strong>」按钮，AI 会用你的录制 + 经验包生成 DSL 脚本和数据模板，约 30-60 秒。</p>
    </section>

    {{-- 5 Excel --}}
    <section class="tut-section" id="excel">
        <h2><span class="tag">5</span>填写 Excel 数据表 <a class="anchor-link" href="#excel">#</a></h2>

        <p>生成完成后，流程目录里会有「<code>数据模板.xlsx</code>」，结构是：</p>

        <table class="tut-tbl">
            <thead>
                <tr><th>商品名称</th><th>价格</th><th>库存</th><th>图片文件夹</th></tr>
            </thead>
            <tbody>
                <tr style="background:#fef3c7"><td colspan="4" style="font-size:12px;color:#78350f">⬅ 第 2 行：录制时填的示例（黄色），第 1 次会执行这行</td></tr>
                <tr><td>测试商品 A</td><td>99.00</td><td>10</td><td>D:\图片\A</td></tr>
                <tr><td>测试商品 B</td><td>199.00</td><td>5</td><td>D:\图片\B</td></tr>
                <tr><td>...</td><td>...</td><td>...</td><td>...</td></tr>
            </tbody>
        </table>

        <h3>填写规则</h3>
        <ul>
            <li><strong>第 1 行不要改</strong>：是表头，软件靠列名找数据。</li>
            <li><strong>第 2 行（黄色）= 录制时填的</strong>，会被作为第 1 次循环执行。不想用可以直接覆盖。</li>
            <li><strong>第 3 行起 = 你要批量做的新数据</strong>，每行 = 一次完整流程。</li>
            <li><strong>空行 = 结束循环</strong>，软件读到空行就停。</li>
            <li><strong>下拉菜单列</strong>：填录制时选过的选项文字，比如「上海」「西安」。</li>
            <li><strong>文件夹路径列</strong>：填完整本地路径，如 <code>D:\图片\sku001</code>。详见第 8 节。</li>
        </ul>
    </section>

    {{-- 6 运行 --}}
    <section class="tut-section" id="run">
        <h2><span class="tag">6</span>运行自动化 <a class="anchor-link" href="#run">#</a></h2>

        <div class="step-grid">
            <div class="step-card">
                <div class="num">1</div>
                <h4>进入「我的流程」</h4>
                <p>点顶部「我的流程」tab，找到你生成的流程。</p>
            </div>
            <div class="step-card">
                <div class="num">2</div>
                <h4>点「运行」</h4>
                <p>软件会弹一个新浏览器，请<strong>先手动登录</strong>目标网站，然后点浏览器顶部的「开始工作」按钮。</p>
            </div>
            <div class="step-card">
                <div class="num">3</div>
                <h4>不要动鼠标键盘</h4>
                <p>软件开始按 Excel 数据逐行执行。运行中不要碰浏览器，避免干扰。</p>
            </div>
            <div class="step-card">
                <div class="num">4</div>
                <h4>等待完成</h4>
                <p>所有行执行完后会自动停止，软件底部会显示「✓ 运行完成」。</p>
            </div>
        </div>

        <div class="tut-callout tip">
            <strong>💡 登录态会保留</strong>
            软件用独立的 Edge profile，<strong>登录一次以后都免登录</strong>。除非你清理过浏览器数据。
        </div>
    </section>

    {{-- 7 人工接管 --}}
    <section class="tut-section" id="manual-takeover">
        <h2><span class="tag">7</span>人工接管（步骤出错时） <a class="anchor-link" href="#manual-takeover">#</a></h2>

        <p>批量执行时如果某一行某一步出错，<strong>v2.0 起软件不会退出</strong>，而是在浏览器顶部弹一个红色暂停条，让你接管。</p>

        <h3>5 个按钮该按哪个？</h3>
        <table class="tut-tbl">
            <thead>
                <tr><th style="width:180px">按钮</th><th>含义</th><th>什么时候用</th></tr>
            </thead>
            <tbody>
                <tr>
                    <td>✅ <strong>已手动完成 → 下一步</strong></td>
                    <td>你在浏览器里手动做完了那步，让软件继续后面</td>
                    <td>⭐ 最常用 — 大多数情况都是这个</td>
                </tr>
                <tr>
                    <td>🔁 重试当前步</td>
                    <td>再让软件试一次，可能是网络慢导致的偶发问题</td>
                    <td>你在浏览器里把状态调好了，让软件重做</td>
                </tr>
                <tr>
                    <td>⏩ 跳过这步</td>
                    <td>这步不做了，直接做下一步</td>
                    <td>这步对本行不重要</td>
                </tr>
                <tr>
                    <td>⏭ 跳过本行</td>
                    <td>当前行剩余步骤全跳过，下一行重新开始</td>
                    <td>这行数据有问题，跳过不要</td>
                </tr>
                <tr>
                    <td>🛑 停止运行</td>
                    <td>整个 batch 停掉</td>
                    <td>不想继续了</td>
                </tr>
            </tbody>
        </table>

        <div class="tut-callout info">
            <strong>🌱 接管期间会静默学习</strong>
            v2.0 起，你在浏览器里手动操作的轨迹会被记录到 <code>learning_samples.json</code>，累积到 5+ 次后未来会支持「让 AI 学习」一键修补该步骤。
        </div>
    </section>

    {{-- 8 文件上传 - 重要章节 --}}
    <section class="tut-section" id="upload">
        <h2><span class="tag">8</span>文件 / 图片上传 <a class="anchor-link" href="#upload">#</a></h2>

        <div class="tut-callout danger">
            <strong>⚠ 重要：文件上传目前并不 100% 稳定</strong>
            这是当前版本最难搞的部分。简单的本地文件对话框上传 OK，但「<strong>网络相册 / 素材库</strong>」类需要先上传 → 等待 → 勾选 → 确定的复杂流程，<strong>成功率不高</strong>。我们仍在优化，请优先用下面的变通方案。
        </div>

        <h3>3 类上传场景的成功率</h3>
        <table class="tut-tbl">
            <thead>
                <tr><th style="width:280px">场景</th><th style="width:100px">成功率</th><th>说明</th></tr>
            </thead>
            <tbody>
                <tr>
                    <td>① 点上传 → 系统文件框 → 选图 → 上传完关闭</td>
                    <td><span class="pill green">高</span></td>
                    <td>单文件 / 多文件直接传，Excel 填路径就行。</td>
                </tr>
                <tr>
                    <td>② 点 + 号 → 弹「上传新图」按钮 → 选图 → 自动入库</td>
                    <td><span class="pill orange">中</span></td>
                    <td>需要等待上传完成，AI 一般能处理。</td>
                </tr>
                <tr>
                    <td>③ <strong>素材库 / 网络相册</strong>：上传 → 等待 → 勾选刚上传的 → 确定</td>
                    <td><span class="pill gray">低</span></td>
                    <td>⚠ 当前版本痛点。勾选位置 / 时机依赖网站行为，差异大。</td>
                </tr>
            </tbody>
        </table>

        <h3>怎么填 Excel 的「文件夹列」</h3>
        <p>列名通常带「文件夹」「目录」「路径」字样，比如 <code>主图_文件夹</code>。</p>

        <table class="tut-tbl">
            <thead>
                <tr><th>填法</th><th>软件行为</th></tr>
            </thead>
            <tbody>
                <tr><td><code>D:\图片\主图1.jpg</code></td><td>上传那一张</td></tr>
                <tr><td><code>D:\图片\sku001</code>（文件夹）</td><td>扫描里面所有图片，批量传</td></tr>
                <tr><td>留空</td><td>跳过这步</td></tr>
            </tbody>
        </table>

        <h3>变通方案：碰到素材库类场景怎么办</h3>
        <div class="tut-card">
            <p><strong>方法 A：把上传步骤拆出来，让人工做</strong></p>
            <p>录制时<strong>不录</strong>素材库的上传 / 勾选步骤，只录前后的步骤。运行时<strong>人工接管</strong>处理素材库那段，软件自动做其他。</p>
            <ol>
                <li>录制时跳过素材库的部分（直接点完弹窗的「确定」），假装是空的。</li>
                <li>运行时跑到那步会"出错"或者图为空，触发人工接管。</li>
                <li>你手动在浏览器里完成素材库的上传 + 勾选 + 确定。</li>
                <li>点「✅ 已手动完成 → 下一步」继续。</li>
            </ol>
            <p style="color:#64748b;font-size:13px;margin-top:8px">💡 100 行数据里素材库占了大部分时间？建议先用这套救急。等后续版本优化好再切回全自动。</p>
        </div>

        <div class="tut-card">
            <p><strong>方法 B：用第三方批量上传工具预先入库</strong></p>
            <p>有些网站后台支持 ERP 批量上图。先把图都通过 ERP 入库，然后录制时<strong>只需要勾选已有图片</strong>，跳过上传那步。</p>
        </div>

        <div class="tut-callout info">
            <strong>🛠 我们在做什么</strong>
            v2.0 已经加入「人工接管 + 静默学习」基础设施。后续版本会基于真实的接管样本，让 AI 学会处理你的具体素材库场景。<strong>你每接管一次，未来都能更准。</strong>
        </div>
    </section>

    {{-- 9 录制技巧 --}}
    <section class="tut-section" id="tips">
        <h2><span class="tag">9</span>录制小技巧 <a class="anchor-link" href="#tips">#</a></h2>

        <h3>这些行为会让 AI 更准</h3>
        <ul>
            <li>✅ 输入框先点一下激活，再输入文字（不要直接键盘输入，软件抓不到焦点）。</li>
            <li>✅ 下拉菜单：先点开下拉触发器，等选项动画完成，再点具体选项。</li>
            <li>✅ 多级菜单（如「省 → 市 → 区」）：每一级都要单独点击，不要拖动鼠标快速划过。</li>
            <li>✅ 录制时把窗口最大化或固定尺寸（默认 1280x800），不要中途调整。</li>
            <li>✅ 弹窗确认 / 关闭 都要真实点击「确定」按钮，不要按 ESC 或回车（这些按键不会被录）。</li>
        </ul>

        <h3>这些坑要避开</h3>
        <ul>
            <li>❌ <strong>不要录验证码 / 短信码 / 滑块</strong>：每次值都不同，AI 没办法。这种步骤<strong>留给人工接管</strong>。</li>
            <li>❌ <strong>不要点浏览器自带的「后退」「前进」按钮</strong>：录不到。需要返回就点页面内的「取消」按钮。</li>
            <li>❌ <strong>不要在录制时打开开发者工具（F12）</strong>：可能干扰录制脚本。</li>
            <li>❌ <strong>不要切换标签页</strong>：录制只跟踪一个标签页里的操作。</li>
            <li>❌ <strong>不要在录制时连点同一个按钮 N 次</strong>：会全部录入，AI 难以判断真实意图。</li>
        </ul>

        <h3>截图功能：什么时候用？</h3>
        <p>录制工具栏顶部支持 <code>Ctrl+Shift+X</code> 对鼠标位置截图，截下来的图会作为辅助信息发给 AI（最多 50 张/流程）。建议用于：</p>
        <ul>
            <li>下拉菜单 / 弹窗里的选项位置很奇怪，光看 selector 看不出</li>
            <li>同一个 selector 在页面上多次出现，需要图来辅助识别</li>
            <li>动态生成的元素，class 都是随机的</li>
        </ul>
    </section>

    {{-- 10 FAQ --}}
    <section class="tut-section" id="faq">
        <h2><span class="tag">10</span>常见问题 <a class="anchor-link" href="#faq">#</a></h2>

        <details class="faq">
            <summary>录制时浏览器闪退 / 打不开</summary>
            <div class="ans">
                ① 关掉本机所有的 Edge 浏览器（包括后台进程）<br>
                ② 关掉 VPN / Clash 等代理软件<br>
                ③ 如果用 file:// 协议测试本地 HTML 也会闪退，请用 http://localhost 启动测试服务器<br>
                ④ 看 <code>~/Documents/好办法自动化/error.log</code> 找具体原因
            </div>
        </details>

        <details class="faq">
            <summary>生成脚本时显示「请先登录」（401）</summary>
            <div class="ans">
                软件自动用机器序列号登录，但 token 可能过期。v2.0 起会在生成前自动重新登录，但极端情况下还是可能失败。<br>
                解决：关闭软件重新打开，让它重新走启动流程。
            </div>
        </details>

        <details class="faq">
            <summary>生成脚本时显示「阿里云账户欠费」</summary>
            <div class="ans">
                AI 模型是付费的，账户余额不足会拒绝调用。请联系客服微信，会有专人协助。
            </div>
        </details>

        <details class="faq">
            <summary>运行时浏览器跑到一半卡住，没动作</summary>
            <div class="ans">
                ① 看进度条是不是显示「等待用户接管」—— 浏览器顶部应该有红色暂停条<br>
                ② 看 <code>error.log</code> 最后几行<br>
                ③ 网络慢的话有些 wait_after 可能不够，在「我的流程」点「编辑 DSL」可以加大 wait_after
            </div>
        </details>

        <details class="faq">
            <summary>Excel 数据填好了，但运行时跳过了某些行</summary>
            <div class="ans">
                ① 检查表头的列名跟生成的 DSL 是否一致（不能有多余空格 / 标点差异）<br>
                ② 中间有空行 = 终止信号，确保数据行之间没有空行<br>
                ③ 必填字段（如商品名）不能为空
            </div>
        </details>

        <details class="faq">
            <summary>素材库勾选不上 / 勾错了图</summary>
            <div class="ans">
                这是当前已知最难的场景。详见第 8 节。<br>
                临时方案：录制时跳过素材库部分，运行时人工接管处理。
            </div>
        </details>

        <details class="faq">
            <summary>我想给录制改个名字 / 删除一个录制</summary>
            <div class="ans">
                「我的流程」tab 里，鼠标悬停到流程卡片上会出现「重命名」「删除」按钮。
            </div>
        </details>

        <details class="faq">
            <summary>免费次数用完了，怎么续</summary>
            <div class="ans">
                联系客服微信 <strong>18033086531</strong>，备注「自动化软件用户」。
            </div>
        </details>

        <details class="faq">
            <summary>软件可以装在 Mac / Linux 上吗</summary>
            <div class="ans">
                当前只支持 Windows 10 / 11 64 位。Mac / Linux 版本计划中，预计 2026 Q3 推出。
            </div>
        </details>
    </section>

    {{-- 11 联系 --}}
    <section class="tut-section" id="contact">
        <h2><span class="tag">11</span>反馈与支持 <a class="anchor-link" href="#contact">#</a></h2>

        <div class="tut-card">
            <p><strong>📩 遇到问题怎么反馈</strong></p>
            <ul>
                <li><strong>软件内一键反馈</strong>：运行出错时会自动弹反馈窗，点「发送给作者」即可上传错误信息（自动脱敏）。</li>
                <li><strong>客服微信</strong>：<code>18033086531</code>（备注「自动化软件用户」）</li>
                <li><strong>邮箱</strong>：<code>likailongliyanni@proton.me</code></li>
            </ul>
        </div>

        <div class="tut-callout tip">
            <strong>🌱 你的每一次反馈都让产品变好</strong>
            v2.0 的人工接管 + 智能学习就是从用户反馈里诞生的功能。继续告诉我们你的使用场景，我们会持续优化。
        </div>

        <p style="text-align:center;margin-top:30px;color:#94a3b8;font-size:13px">
            📖 本教程会随软件更新持续完善，建议收藏本页面。
        </p>
    </section>

</div>

<script>
    // 平滑滚动
    document.querySelectorAll('.tut-toc a, .anchor-link').forEach(a => {
        a.addEventListener('click', e => {
            const id = a.getAttribute('href');
            if (id && id.startsWith('#')) {
                const el = document.querySelector(id);
                if (el) {
                    e.preventDefault();
                    el.scrollIntoView({behavior: 'smooth', block: 'start'});
                    history.replaceState(null, '', id);
                }
            }
        });
    });
</script>

@endsection
