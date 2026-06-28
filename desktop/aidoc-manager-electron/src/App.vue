<template>
  <main class="app-shell">
    <section v-if="booting" class="gate">
      <div class="gate-panel">
        <div class="brand-mark"><ShieldCheck :size="24" /></div>
        <h1>好办法 AI 档案管理</h1>
        <p>正在启动本地资料库...</p>
      </div>
    </section>

    <section v-else-if="!state.hasPassword" class="gate">
      <div class="gate-panel">
        <div class="brand-mark"><LockKeyhole :size="24" /></div>
        <h1>设置本地密码</h1>
        <p>这个密码只保存在本机，用来保护本地档案库。</p>
        <form class="gate-form" @submit.prevent="setPassword">
          <input v-model="passwordForm.password" type="password" autocomplete="new-password" placeholder="输入本地密码" />
          <input v-model="passwordForm.confirm" type="password" autocomplete="new-password" placeholder="再次输入" />
          <button class="primary-btn" type="submit" :disabled="busy">
            <KeyRound :size="17" />
            创建本地密码
          </button>
          <span class="error-text">{{ passwordForm.error }}</span>
        </form>
      </div>
    </section>

    <section v-else-if="!state.unlocked" class="gate">
      <div class="gate-panel">
        <div class="brand-mark"><Fingerprint :size="24" /></div>
        <h1>输入本地密码</h1>
        <p>序列号负责授权，密码只负责打开这台电脑里的资料库。</p>
        <form class="gate-form" @submit.prevent="verifyPassword">
          <input v-model="passwordForm.password" type="password" autocomplete="current-password" placeholder="本地密码" />
          <button class="primary-btn" type="submit" :disabled="busy">
            <Unlock :size="17" />
            打开资料库
          </button>
          <span class="error-text">{{ passwordForm.error }}</span>
        </form>
      </div>
    </section>

    <template v-else>
      <aside class="sidebar">
        <div class="sidebar-brand">
          <div class="brand-mark small"><Archive :size="20" /></div>
          <div>
            <strong>AIDOC</strong>
            <span>AI 档案管理</span>
          </div>
        </div>
        <nav>
          <button class="nav-item" :class="{ active: view === 'workbench' }" @click="view = 'workbench'"><LayoutDashboard :size="18" />工作台</button>
          <button class="nav-item" :class="{ active: view === 'library' }" @click="switchToLibrary"><ListChecks :size="18" />识别队列</button>
          <button class="nav-item" :class="{ active: view === 'finder' }" @click="openFinder"><FolderSearch :size="18" />AI 档案秘书</button>
          <button class="nav-item" :class="{ active: view === 'points' }" @click="openPoints"><ShoppingCart :size="18" />购买积分</button>
          <button class="nav-item" disabled><Settings :size="18" />本地设置</button>
        </nav>
      </aside>

      <section class="workspace">
        <header class="topbar">
          <div>
            <p class="eyebrow">本地安全模式</p>
            <h1>AI 档案管理工作台</h1>
          </div>
          <div class="top-actions">
            <button class="ghost-btn" @click="copySerial">
              <Copy :size="16" />
              复制编号
            </button>
            <div class="serial-box">{{ state.serial || '读取中' }}</div>
          </div>
        </header>

        <div v-show="view === 'workbench'">
        <section class="metric-row">
          <article class="metric-card">
            <span class="metric-icon blue"><Files :size="20" /></span>
            <div>
              <small>本地资料</small>
              <strong>{{ summary.documents }}</strong>
            </div>
          </article>
          <article class="metric-card">
            <span class="metric-icon green"><BookOpenCheck :size="20" /></span>
            <div>
              <small>已入库页数</small>
              <strong>{{ summary.pages }}</strong>
            </div>
          </article>
          <article class="metric-card">
            <span class="metric-icon amber"><Gauge :size="20" /></span>
            <div>
              <small>剩余AI积分</small>
              <strong>{{ state.quota.available }} 分</strong>
            </div>
          </article>
          <article class="metric-card">
            <span :class="['metric-icon', state.online ? 'green' : 'red']"><Wifi :size="20" /></span>
            <div>
              <small>后台状态</small>
              <strong>{{ state.online ? '已连接' : '本地模式' }}</strong>
            </div>
          </article>
        </section>

        <section class="content-grid">
          <article class="panel import-panel">
            <div class="panel-head compact">
              <div>
                <p class="eyebrow">上传资料</p>
                <h2>拖文件进来，自动入库</h2>
              </div>
              <button class="ghost-btn" :disabled="scan.running" @click="refreshSummary">
                <RefreshCw :size="16" />
                刷新
              </button>
            </div>

            <div class="field-group">
              <label>本地资料库位置</label>
              <div class="path-row">
                <input :value="state.libraryDir || '尚未设置'" readonly />
                <button class="secondary-btn" :disabled="scan.running" @click="chooseLibrary">
                  <FolderCog :size="16" />
                  设置
                </button>
                <button class="icon-btn" :disabled="!state.libraryDir" title="打开资料库" @click="openPath(state.libraryDir)">
                  <ExternalLink :size="16" />
                </button>
              </div>
            </div>

            <div class="upload-zone" :class="{ dragover: dragOver }"
                 @dragover.prevent="dragOver = true" @dragenter.prevent="dragOver = true"
                 @dragleave.prevent="dragOver = false" @drop.prevent="onDropFiles">
              <FolderInput :size="34" />
              <p class="upload-title">把一个或多个文件拖到这里上传</p>
              <p class="upload-sub">支持 PDF / 图片 / Word / Excel，拖进来自动进资料库</p>
              <button class="primary-btn" :disabled="scan.running" @click="pickAndImport">
                <FolderSearch :size="16" /> 选择文件
              </button>
            </div>

            <details class="folder-scan-more">
              <summary>或：导入整个文件夹</summary>
              <div class="field-group" style="margin-top:10px">
                <div class="path-row">
                  <input :value="scan.sourceDir || '选择供应商资料 / 下载目录等文件夹'" readonly />
                  <button class="secondary-btn" :disabled="scan.running" @click="chooseSource">
                    <FolderSearch :size="16" /> 选择
                  </button>
                  <button class="secondary-btn" :disabled="scan.running || !canStartScan" @click="startScan">开始</button>
                </div>
                <label class="check-line" style="margin-top:8px">
                  <input v-model="scan.recursive" type="checkbox" /><span>包含子文件夹</span>
                </label>
                <div class="folder-scan-actions">
                  <div class="segmented">
                    <button :class="{ active: scan.importMode === 'copy' }" :disabled="scan.running" @click="scan.importMode = 'copy'">复制管理</button>
                    <button :class="{ active: scan.importMode === 'index' }" :disabled="scan.running" @click="scan.importMode = 'index'">仅建索引</button>
                  </div>
                  <p>{{ scan.running ? '正在处理，请保持软件打开。' : '新电脑默认赠送 30 AI积分，任务成功后扣费。' }}</p>
                </div>
              </div>
            </details>
          </article>

          <article class="panel progress-panel">
            <div class="panel-head compact">
              <div>
                <p class="eyebrow">实时进度</p>
                <h2>{{ progress.stageLabel || '等待任务' }}</h2>
              </div>
              <span class="status-pill">{{ scan.running ? '进行中' : '就绪' }}</span>
            </div>

            <div class="progress-block">
              <div class="progress-top">
                <strong>{{ progressPercent }}%</strong>
                <span>{{ progress.donePages }} / {{ progress.totalPages || 0 }} 页</span>
              </div>
              <div class="progress-track">
                <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
              </div>
              <div class="progress-current">
                <FileText :size="16" />
                <span>{{ progress.currentFile || '还没有开始处理文件' }}</span>
              </div>
            </div>

            <div class="counter-grid">
              <div><small>成功</small><strong>{{ progress.successPages }}</strong></div>
              <div><small>重复跳过</small><strong>{{ progress.skippedPages }}</strong></div>
              <div><small>失败</small><strong>{{ progress.failedPages }}</strong></div>
            </div>

            <div v-if="scan.result" class="result-note">
              <CheckCircle2 :size="18" />
              <span>本次导入 {{ scan.result.created_documents }} 份，成功识别 {{ scan.result.billable_pages }} 页。</span>
            </div>
          </article>
        </section>

        <section class="panel queue-panel">
          <div class="panel-head compact">
            <div>
              <p class="eyebrow">最近结果</p>
              <h2>资料队列</h2>
            </div>
            <span class="muted">{{ recentItems.length }} 条</span>
          </div>

          <div class="queue-table">
            <div class="queue-head">
              <span>文件</span>
              <span>页数</span>
              <span>状态</span>
              <span>计数方式</span>
            </div>
            <div v-if="!recentItems.length" class="empty-row">还没有导入资料。</div>
            <div v-for="item in recentItems" :key="item.path || item.name + item.created_at" class="queue-row">
              <span class="file-cell">
                <FileText :size="16" />
                <em>{{ item.name }}</em>
              </span>
              <span>{{ item.pages }}</span>
              <span><i :class="['dot', item.status]"></i>{{ statusLabel(item.status) }}</span>
              <span>{{ item.method || item.extension }}</span>
            </div>
          </div>
        </section>
        </div>

        <!-- ───────────── 购买积分 ───────────── -->
        <div v-show="view === 'points'" class="points-view">
          <section class="points-hero panel">
            <div class="points-balance">
              <span class="metric-icon amber"><ShoppingCart :size="23" /></span>
              <div><small>当前电脑剩余AI积分</small><strong>{{ state.quota.available }}</strong><em>积分</em></div>
            </div>
            <div class="points-device">
              <span>积分账户绑定本机序列号</span>
              <strong>{{ state.serial }}</strong>
              <button class="ghost-btn small" @click="syncPoints"><RefreshCw :size="14" /> 刷新积分</button>
            </div>
          </section>

          <section class="points-grid">
            <article class="panel points-contact">
              <p class="eyebrow">联系充值</p>
              <h2>添加开发者微信</h2>
              <div class="wechat-card">
                <div class="wechat-mark">微</div>
                <div><small>微信号</small><strong>{{ state.billing.contact_wechat }}</strong></div>
              </div>
              <button class="primary-btn points-copy" @click="copyWechat"><Copy :size="16" />复制微信号</button>
              <p>付款后请发送<strong>电脑序列号</strong>和购买积分档位，工作人员会在后台人工充值。</p>
              <div class="device-warning">
                <strong>积分跟电脑走，不跟账号走</strong>
                <span>本软件无需注册。更换电脑需要迁移积分时，请把新旧电脑序列号发给开发者处理。</span>
              </div>
            </article>

            <article class="panel points-pricing">
              <div class="panel-head compact">
                <div><p class="eyebrow">积分价格</p><h2>首发体验价</h2></div>
                <span class="points-gift">新电脑赠送 {{ state.billing.default_points }} 积分</span>
              </div>
              <div class="pricing-table">
                <div class="pricing-row head"><span>充值额度</span><span>标准售价</span><span>首发体验价</span></div>
                <div v-for="pkg in state.billing.packages" :key="pkg.points" class="pricing-row">
                  <span><strong>{{ pkg.points }}</strong> 积分<em v-if="pkg.once_per_device">每台限一次</em></span>
                  <span>{{ pkg.standard_price == null ? '—' : `¥${pkg.standard_price}` }}</span>
                  <span class="launch-price">¥{{ pkg.launch_price }}</span>
                </div>
              </div>
              <p class="pricing-note">积分不足？联系工作人员充值，充值后长期有效。</p>
            </article>
          </section>

          <section class="panel points-rules">
            <div class="panel-head compact"><div><p class="eyebrow">计费规则</p><h2>AI积分怎么使用</h2></div></div>
            <div class="rule-list">
              <div v-for="(rule, index) in state.billing.rules" :key="rule"><span>{{ index + 1 }}</span><p>{{ rule }}</p></div>
            </div>
            <p class="overdraft-note">允许临时透支 {{ state.billing.overdraft_limit }} 积分；达到透支上限后，需要充值才能继续执行新任务。</p>
          </section>
        </div>

        <!-- ───────────── 识别队列 / 资料库 ───────────── -->
        <div v-show="view === 'library'" class="library-view">
          <section class="metric-row">
            <article class="metric-card lib-stat" :class="{ active: lib.filterStatus === '' && !lib.onlyUnrecognized }" @click="setStatusFilter('')">
              <div><small>全部资料</small><strong>{{ lib.stats.total }}</strong></div>
            </article>
            <article class="metric-card lib-stat" :class="{ active: lib.onlyUnrecognized }" @click="setUnrecognized">
              <div><small>未识别</small><strong>{{ lib.stats.unrecognized }}</strong></div>
            </article>
            <article class="metric-card lib-stat" :class="{ active: lib.filterStatus === 'pending_review' }" @click="setStatusFilter('pending_review')">
              <div><small>待确认</small><strong>{{ lib.stats.pending }}</strong></div>
            </article>
            <article class="metric-card lib-stat" :class="{ active: lib.filterStatus === 'confirmed' }" @click="setStatusFilter('confirmed')">
              <div><small>已确认</small><strong>{{ lib.stats.confirmed }}</strong></div>
            </article>
            <article class="metric-card lib-stat">
              <div><small>重复资料</small><strong>{{ lib.stats.duplicate }}</strong></div>
            </article>
          </section>

          <div class="type-tabs">
            <button :class="{ active: lib.filterType === '' }" @click="setTypeFilter('')">全部</button>
            <button v-for="t in meta.types" :key="t.key" :class="{ active: lib.filterType === t.key }" @click="setTypeFilter(t.key)">{{ t.label }}</button>
          </div>

          <section class="panel">
            <div class="panel-head compact">
              <div><p class="eyebrow">资料库</p><h2>共 {{ lib.total }} 条</h2></div>
              <div class="lib-toolbar">
                <button class="ghost-btn" :disabled="lib.loading" @click="loadDocs"><RefreshCw :size="15" />刷新</button>
                <button class="ghost-btn" :disabled="recog.running || !unrecognizedDocs.length" @click="selectUnrecognized">勾选未识别</button>
                <button class="primary-btn" :disabled="recog.running || !selectedCount" @click="recognizeSelected"><Sparkles :size="15" />识别选中({{ selectedCount }})</button>
                <button class="secondary-btn" :disabled="recog.running || !selectedConfirmable" @click="confirmSelected"><CheckCircle2 :size="15" />确认选中({{ selectedConfirmable }})</button>
              </div>
            </div>

            <!-- AI 识别进度（让用户看见在干活；识别约 10 秒/份）-->
            <div v-if="recog.running || recog.lastError" class="recog-bar" :class="{ done: !recog.running }">
              <div class="recog-line">
                <Sparkles :size="14" />
                <strong>{{ recog.running ? (recog.stageLabel || '识别中…') : '识别完成' }}</strong>
                <span class="recog-current" :title="recog.current">{{ recog.current }}</span>
                <span class="recog-count">{{ recog.done }} / {{ recog.total }}</span>
              </div>
              <div class="recog-track"><div class="recog-fill" :style="{ width: recogPercent + '%' }"></div></div>
              <div v-if="!recog.running && recog.lastError" class="recog-err">部分未用 AI：{{ recog.lastError }}（已按规则粗分类，可手动编辑）</div>
            </div>

            <div class="lib-table">
              <div class="lib-head" :style="gridStyle">
                <span class="sel-cell"><input type="checkbox" :checked="anySelected" @change="toggleSelectAll" title="勾选本页 / 取消" /></span>
                <span>文件</span>
                <span v-for="c in activeColumns" :key="c.key">{{ c.label }}</span>
                <span>状态</span>
                <span>操作</span>
              </div>
              <div v-if="lib.error" class="empty-row error-text">资料列表刷新失败：{{ lib.error }}。原列表已保留，请点击“刷新”重试。</div>
              <div v-else-if="!lib.docs.length" class="empty-row">这里还没有资料。先去「工作台」上传文件，再回来识别。</div>
              <div v-for="d in lib.docs" :key="d.id" class="lib-row" :class="{ 'row-sel': selected.has(d.id) }" :style="gridStyle">
                <span class="sel-cell"><input type="checkbox" :checked="selected.has(d.id)" @change="toggleSelect(d)" /></span>
                <span class="file-cell file-open" :title="'点击打开：' + d.file_name" @click="openPath(d.managed_path || d.original_path)"><FileText :size="15" /><em>{{ d.file_name }}</em></span>
                <span v-for="c in activeColumns" :key="c.key" class="cell-clip" :title="(d.values && d.values[c.key]) || ''">{{ (d.values && d.values[c.key]) || '—' }}</span>
                <span><i class="dot" :class="reviewClass(d)"></i>{{ reviewLabel(d) }}<i v-if="d.is_duplicate" class="dup-tag">重复</i></span>
                <span class="ops">
                  <button class="link-btn" :disabled="d.busy" @click="recognizeOne(d)">{{ d.busy ? '识别中…' : (d.recognized ? '重新识别' : '识别') }}</button>
                  <button class="link-btn" @click="openDetail(d.id)">修改</button>
                  <button v-if="d.recognized && d.review_status !== 'confirmed'" class="link-btn confirm-link" :disabled="d.busy" @click="confirmOne(d)">确认</button>
                  <button class="link-btn delete-link" :disabled="d.busy || recog.running" @click="deleteOne(d)">删除</button>
                </span>
              </div>
            </div>
            <div class="library-pagination">
              <span>共 {{ lib.total }} 条，每页 20 条</span>
              <button class="ghost-btn small" :disabled="lib.page <= 1 || lib.loading" @click="goLibraryPage(lib.page - 1)">上一页</button>
              <strong>{{ lib.page }} / {{ lib.totalPages }}</strong>
              <button class="ghost-btn small" :disabled="lib.page >= lib.totalPages || lib.loading" @click="goLibraryPage(lib.page + 1)">下一页</button>
              <label>跳至 <input v-model.number="lib.jumpPage" type="number" min="1" :max="lib.totalPages" @keyup.enter="jumpLibraryPage" /> 页</label>
              <button class="secondary-btn small" :disabled="lib.loading" @click="jumpLibraryPage">跳转</button>
            </div>
          </section>
        </div>

        <div v-show="view === 'finder'" class="finder-view">
          <section class="panel chat-panel">
            <div class="panel-head">
              <div><p class="eyebrow">AI 档案秘书 <span class="member-tag">会员</span></p><h2>找资料、整理材料、起草合同，一句话交代</h2></div>
              <div class="finder-cache" :class="{ over: cache.over }">
                <span>整理缓存 {{ cache.count }} 个 · {{ fmtSize(cache.bytes) }}<em v-if="cache.over"> · 超 1G，建议清理</em></span>
                <button class="ghost-btn training-entry" @click="openTemplateResources"><Files :size="14" /> 文书资源池 {{ resources.templates.length }}</button>
                <button class="ghost-btn training-entry" @click="openTrainingNotes"><BookOpenCheck :size="14" /> 培训笔记 {{ training.notes.length }}</button>
                <button class="ghost-btn" :disabled="!cache.count" @click="clearCache"><Trash2 :size="14" /> 一键清理</button>
              </div>
            </div>

            <div v-if="!state.isMember" class="chat-locked">
              <ShieldCheck :size="40" />
              <p>AI 档案秘书是<strong>会员专属</strong>功能</p>
              <span>开通会员后，可用聊天查找和整理档案，也可根据业务要求起草合同内容。</span>
            </div>

            <div v-else class="chat-workspace">
              <aside class="conversation-sidebar">
                <div class="conversation-sidebar-head">
                  <button class="primary-btn small" @click="newConversation"><Plus :size="14" /> 新对话</button>
                  <button class="icon-btn" title="打开本地聊天记录文件夹" @click="openConversationFolder"><FolderOpen :size="16" /></button>
                </div>
                <div v-if="conversations.error" class="conversation-error">{{ conversations.error }}</div>
                <div v-if="conversations.loading" class="conversation-empty">正在读取记录…</div>
                <div v-else-if="!conversations.items.length" class="conversation-empty">暂无历史对话</div>
                <div v-for="group in chatGroups" :key="group.key" class="conversation-group">
                  <div class="conversation-group-label">{{ group.label }}</div>
                  <div v-for="item in group.items" :key="item.id" class="conversation-item" :class="{ active: conversations.currentId === item.id }">
                    <button class="conversation-open" @click="loadConversation(item.id)">
                      <strong>{{ item.title }}</strong>
                      <small>{{ formatConversationAge(item.updated_at) }}</small>
                    </button>
                    <div class="conversation-actions">
                      <button title="修改名称" @click.stop="renameConversation(item)"><Pencil :size="12" /></button>
                      <button title="删除对话" @click.stop="deleteConversation(item)"><Trash2 :size="12" /></button>
                    </div>
                  </div>
                </div>
              </aside>

              <div class="chat-main">
                <div class="current-chat-title">
                  <strong>{{ conversations.currentTitle || '新对话' }}</strong>
                  <span>聊天内容自动保存在本地资料库</span>
                </div>
                <div class="chat-scroll">
                <div v-for="m in chat.messages" :key="m.id" class="chat-row" :class="m.role">
                  <div class="chat-bubble">
                    <div class="chat-text">{{ m.text }}</div>
                    <div v-if="m.generatedDocument" class="generated-document">
                      <FileText :size="20" />
                      <span><strong>{{ m.generatedDocument.file_name }}</strong><small>{{ m.generatedDocument.template_name ? `已使用资源池模板：${m.generatedDocument.template_name}` : '已根据本轮要求综合生成新文书' }}</small></span>
                      <button class="primary-btn small" @click="openGeneratedDocument(m)">打开文书</button>
                      <button class="ghost-btn small" @click="openPath(m.generatedDocument.dir)">打开文件夹</button>
                    </div>
                    <div v-if="m.trainingNotesUsed && m.trainingNotesUsed.length" class="training-hit">
                      已应用培训笔记：{{ m.trainingNotesUsed.join('、') }}
                    </div>
                    <div v-if="m.organize && m.materials && m.materials.length" class="chat-materials">
                      <label v-for="x in m.materials" :key="x.id" class="chat-mat">
                        <input type="checkbox" v-model="x.picked" />
                        <span class="cm-name" :title="x.file_name">{{ x.file_name }}</span>
                        <span class="cm-type">{{ x.type_label }}</span>
                      </label>
                      <div class="message-export-options">
                        <label class="watermark-check">
                          <input type="checkbox" v-model="m.useWatermark" />
                          <span>导出副本添加水印</span>
                        </label>
                        <input v-if="m.useWatermark" v-model="m.watermarkText" maxlength="60"
                          placeholder="水印文字，可在导出前修改" />
                        <button class="primary-btn small gather-btn" type="button"
                          @click.stop.prevent="gatherFromMsg(m)">
                          <Copy :size="14" /> {{ m.gathering ? '正在整理…' : (m.gathered ? '打开已整理文件夹' : '整理到文件夹') }}
                        </button>
                      </div>
                      <p v-if="m.exportError" class="message-export-error">{{ m.exportError }}</p>
                    </div>
                  </div>
                </div>
                </div>

                <div class="chat-export-settings">
                <label class="export-toggle" :class="{ active: chat.needOrganize }">
                  <input type="checkbox" v-model="chat.needOrganize" />
                  <span><strong>需要整理文件</strong><small>关闭时秘书只回答，不创建任何文件夹</small></span>
                </label>
                <label v-if="chat.needOrganize" class="export-toggle" :class="{ active: chat.useWatermark }">
                  <input type="checkbox" v-model="chat.useWatermark" />
                  <span><strong>导出添加水印</strong><small>秘书会根据本轮事项建议水印内容</small></span>
                </label>
                <input v-if="chat.needOrganize && chat.useWatermark" v-model="chat.watermarkText"
                  class="watermark-input" maxlength="60" placeholder="可先留空，由秘书生成；也可以直接填写" />
                </div>

                <div class="chat-input">
                <textarea v-model="chat.input" rows="5" :disabled="chat.busy"
                  placeholder="告诉档案秘书要找什么、整理什么，或需要起草什么合同…（回车发送，Shift+回车换行）"
                  @keydown="onChatKeydown"></textarea>
                <button class="ghost-btn chat-img" disabled title="发图片（后续上线）"><FileText :size="16" /></button>
                <button class="primary-btn" :disabled="chat.busy || !chat.input.trim()" @click="sendChat">发送</button>
                </div>
              </div>
            </div>
          </section>
        </div>
      </section>
    </template>

    <!-- 本地文书模板资源池 -->
    <div v-if="resources.open" class="modal-mask" @click.self="resources.open = false">
      <div class="modal training-modal resource-modal">
        <header class="modal-head">
          <div><strong>本地文书资源池</strong><span>从已识别资料提炼模板；AI 写合同、授权书等文书时优先使用</span></div>
          <button class="icon-btn" @click="resources.open = false"><X :size="18" /></button>
        </header>
        <div class="training-body">
          <section class="training-list">
            <div class="training-list-head">
              <span>{{ resources.templates.length }} 个模板 · {{ resources.active }} 个启用</span>
              <button class="secondary-btn" :disabled="resources.rebuilding" @click="rebuildTemplateResources">
                {{ resources.rebuilding ? '提炼中…' : '扫描现有资料' }}
              </button>
            </div>
            <button v-for="item in resources.templates" :key="item.id" class="training-note-item"
              :class="{ active: resources.form.id === item.id, disabled: !item.enabled }" @click="editTemplateResource(item)">
              <span><strong>{{ item.name }}</strong><small>{{ item.type_label }} · 来源：{{ item.source_file_name || '本地创建' }}</small></span>
              <em>使用 {{ item.use_count }} 次</em>
            </button>
            <div v-if="!resources.templates.length" class="training-empty">资源池还没有模板。点击“扫描现有资料”，系统会从合同、授权书等已识别文书中自动提炼。</div>
          </section>
          <form v-if="resources.form.id" class="training-form" @submit.prevent="saveTemplateResource">
            <div class="training-form-title">
              <div><strong>编辑文书模板</strong><span>模板正文和原始资料分开保存，只留在本地</span></div>
              <label class="training-enabled"><input type="checkbox" v-model="resources.form.enabled" /> 启用</label>
            </div>
            <label>模板名称<input v-model="resources.form.name" maxlength="100" /></label>
            <div class="resource-meta">
              <span>类型：{{ resources.form.type_label }}</span>
              <span>状态：{{ resources.form.status === 'candidate' ? '候选模板' : '正式模板' }}</span>
              <span>来源：{{ resources.form.source_file_name }}</span>
            </div>
            <label>可编辑模板正文
              <textarea class="resource-content" v-model="resources.form.template_text" rows="16" maxlength="120000"></textarea>
            </label>
            <p v-if="resources.form.variables.length" class="training-tip">已识别变量：{{ resources.form.variables.map(x => x.label || x.key).join('、') }}</p>
            <p v-if="resources.error" class="message-export-error">{{ resources.error }}</p>
            <div class="training-actions">
              <button class="secondary-btn danger-text" type="button" @click="deleteTemplateResource">删除模板</button>
              <span></span><span></span>
              <button class="primary-btn" type="submit" :disabled="resources.saving">{{ resources.saving ? '保存中…' : '保存模板' }}</button>
            </div>
          </form>
          <div v-else class="training-empty resource-placeholder">从左侧选择一个模板查看和编辑。</div>
        </div>
      </div>
    </div>

    <!-- AI 资料秘书 · 本地培训笔记 -->
    <div v-if="training.open" class="modal-mask" @click.self="training.open = false">
      <div class="modal training-modal">
        <header class="modal-head">
          <div><strong>培训笔记</strong><span>把你的业务经验教给档案秘书，命中场景后自动应用</span></div>
          <button class="icon-btn" @click="training.open = false"><X :size="18" /></button>
        </header>
        <div class="training-body">
          <section class="training-list">
            <div class="training-list-head">
              <span>本地笔记 {{ training.notes.length }} 条</span>
              <button class="secondary-btn" @click="newTrainingNote">＋ 新建</button>
            </div>
            <button v-for="note in training.notes" :key="note.id" class="training-note-item"
              :class="{ active: training.form.id === note.id, disabled: !note.enabled }" @click="editTrainingNote(note)">
              <span><strong>{{ note.title }}</strong><small>{{ note.trigger_keywords }}</small></span>
              <em>已使用 {{ note.use_count }} 次</em>
            </button>
            <div v-if="!training.notes.length" class="training-empty">还没有培训笔记。遇到秘书不懂的场景时，在这里教它一次。</div>
          </section>
          <form class="training-form" @submit.prevent="saveTrainingNote">
            <div class="training-form-title">
              <div><strong>{{ training.form.id ? '编辑培训笔记' : '新增培训笔记' }}</strong><span>所有内容只保存在本机资料库</span></div>
              <label class="training-enabled"><input type="checkbox" v-model="training.form.enabled" /> 启用</label>
            </div>
            <label>场景名称<input v-model="training.form.title" maxlength="100" placeholder="例如：R8 设备采购投标" /></label>
            <label>触发关键词<input v-model="training.form.trigger_keywords" maxlength="500" placeholder="例如：R8采购，影像设备，三脚架（用逗号分隔）" /></label>
            <label>教档案秘书怎么处理
              <textarea v-model="training.form.instruction" rows="10" maxlength="12000"
                placeholder="写清楚这个场景要哪些材料、如何筛选、缺什么要怎么提醒、推荐使用什么水印等。"></textarea>
            </label>
            <p class="training-tip">匹配规则：用户问题命中任一触发关键词时，这条笔记会随本轮请求交给 AI，并优先于通用知识库。</p>
            <p v-if="training.error" class="message-export-error">{{ training.error }}</p>
            <div class="training-actions">
              <button v-if="training.form.id" class="secondary-btn danger-text" type="button" @click="deleteTrainingNote">删除笔记</button>
              <span></span>
              <button class="secondary-btn" type="button" @click="newTrainingNote">清空</button>
              <button class="primary-btn" type="submit" :disabled="training.saving">{{ training.saving ? '保存中…' : '保存培训笔记' }}</button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <!-- 详情 / 字段编辑 -->
    <div v-if="detail.open" class="modal-mask" @click.self="closeDetail">
      <div class="modal">
        <header class="modal-head">
          <div><strong>{{ detail.file_name }}</strong><span class="conf" v-if="detail.ai_confidence">AI 置信 {{ detail.ai_confidence }}</span></div>
          <button class="icon-btn" @click="closeDetail"><X :size="18" /></button>
        </header>
        <div class="modal-body">
          <label class="edit-field">
            <span>资料类型</span>
            <select v-model="detail.document_type">
              <option v-for="t in meta.types" :key="t.key" :value="t.key">{{ t.label }}</option>
            </select>
          </label>
          <label v-for="f in detailFields" :key="f.source" class="edit-field">
            <span>{{ f.label }}</span>
            <input v-model="detail.values[f.source]" :placeholder="f.label" />
          </label>
          <p v-if="detail.error" class="error-text">{{ detail.error }}</p>
        </div>
        <footer class="modal-foot">
          <button class="ghost-btn" :disabled="detail.busy" @click="recognizeInDetail"><Sparkles :size="15" />重新识别</button>
          <span class="spacer"></span>
          <button class="secondary-btn" :disabled="detail.busy" @click="confirmDetail('rejected')">驳回</button>
          <button class="primary-btn" :disabled="detail.busy" @click="confirmDetail('confirmed')"><CheckCircle2 :size="16" />确认入库</button>
        </footer>
      </div>
    </div>
  </main>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import {
  Archive,
  BookOpenCheck,
  CheckCircle2,
  Copy,
  ExternalLink,
  FileText,
  Files,
  Fingerprint,
  FolderOpen,
  FolderCog,
  FolderInput,
  FolderSearch,
  Gauge,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  LockKeyhole,
  Pencil,
  Plus,
  RefreshCw,
  Settings,
  ShoppingCart,
  ShieldCheck,
  Sparkles,
  Trash2,
  Unlock,
  Wifi,
  X,
} from 'lucide-vue-next'

const api = window.aidocAPI
const booting = ref(true)
const busy = ref(false)

const state = reactive({
  serial: '',
  rawSerial: '',
  hasPassword: false,
  unlocked: false,
  libraryDir: '',
  online: false,
  isMember: true,   // AI 资料员聊天为会员功能；服务器返回 is_member=false 时锁定，默认开放便于测试
  quota: { free: 30, paid: 0, available: 30, used: 0, unit: 'point' },
  billing: {
    contact_wechat: '18033086531', default_points: 30, overdraft_limit: 20,
    packages: [
      { points: 50, standard_price: null, launch_price: 2.99, once_per_device: true },
      { points: 200, standard_price: 29.9, launch_price: 9.9, once_per_device: false },
      { points: 500, standard_price: 79.9, launch_price: 19.9, once_per_device: false },
      { points: 1000, standard_price: 159.9, launch_price: 29.9, once_per_device: false },
    ],
    rules: [
      'JPG、PNG等图片识别：每张1积分', 'PDF、Word识别：每页1积分',
      'AI智能查找或连续追问：每次成功回答1积分', '合同生成：按最终页数每页2积分',
      '任务处理失败、未找到资料或仅进行限制提醒：不扣积分',
    ],
  },
})

const passwordForm = reactive({
  password: '',
  confirm: '',
  error: '',
})

const summary = reactive({
  documents: 0,
  pages: 0,
  recent: [],
})

const scan = reactive({
  sourceDir: '',
  recursive: true,
  importMode: 'copy',
  running: false,
  result: null,
  liveItems: [],
})

const progress = reactive({
  stage: '',
  stageLabel: '',
  currentFile: '',
  donePages: 0,
  totalPages: 0,
  successPages: 0,
  skippedPages: 0,
  failedPages: 0,
})

const canStartScan = computed(() => Boolean(state.libraryDir && scan.sourceDir))
const progressPercent = computed(() => {
  if (!progress.totalPages) return scan.running ? 8 : 0
  return Math.min(100, Math.round((progress.donePages / progress.totalPages) * 100))
})
const recentItems = computed(() => {
  if (scan.result?.items?.length) return [...scan.result.items].reverse().slice(0, 14)
  return summary.recent || []
})

function resetProgress() {
  Object.assign(progress, {
    stage: '',
    stageLabel: '',
    currentFile: '',
    donePages: 0,
    totalPages: 0,
    successPages: 0,
    skippedPages: 0,
    failedPages: 0,
  })
}

async function backend(cmd, args = {}) {
  // 深拷成普通对象：Vue 响应式参数是 Proxy，直接走 IPC 会报 "An object could not be cloned"。
  const plain = JSON.parse(JSON.stringify(args ?? {}))
  const result = await api.backend(cmd, plain)
  if (!result.ok) throw new Error(result.error || '处理失败')
  return result.data
}

async function loadState() {
  const data = await backend('get_state')
  state.serial = data.serial || ''
  state.rawSerial = data.raw_serial || ''
  state.hasPassword = Boolean(data.has_password)
  state.unlocked = Boolean(data.unlocked)
  state.libraryDir = data.library_dir || ''
  state.quota = data.quota || state.quota
  state.billing = data.billing || state.billing
}

async function registerDevice() {
  const data = await backend('register')
  state.online = Boolean(data.online)
  state.serial = data.serial || state.serial
  state.quota = data.quota || state.quota
  state.billing = data.billing || state.billing
}

async function syncPoints() {
  try {
    const data = await backend('sync_quota')
    state.online = Boolean(data.online)
    state.quota = data.quota || state.quota
    state.billing = data.billing || state.billing
  } catch {}
}

function openPoints() {
  view.value = 'points'
  syncPoints()
}

async function copyWechat() {
  await api.copy(state.billing.contact_wechat || '18033086531')
  window.alert('微信号已复制。添加时请备注“AI档案积分充值”。')
}

async function refreshSummary() {
  if (!state.unlocked) return
  try {
    const data = await backend('library_summary')
    state.libraryDir = data.library_dir || state.libraryDir
    summary.documents = data.documents || 0
    summary.pages = data.pages || 0
    summary.recent = data.recent || []
  } catch {
    summary.documents = 0
    summary.pages = 0
    summary.recent = []
  }
}

async function setPassword() {
  passwordForm.error = ''
  if (passwordForm.password.length < 4) {
    passwordForm.error = '至少输入 4 位。'
    return
  }
  if (passwordForm.password !== passwordForm.confirm) {
    passwordForm.error = '两次密码不一致。'
    return
  }
  busy.value = true
  try {
    const data = await backend('set_password', { password: passwordForm.password })
    state.hasPassword = Boolean(data.has_password)
    state.unlocked = Boolean(data.unlocked)
    passwordForm.password = ''
    passwordForm.confirm = ''
    await refreshSummary()
  } catch (error) {
    passwordForm.error = error.message
  } finally {
    busy.value = false
  }
}

async function verifyPassword() {
  passwordForm.error = ''
  busy.value = true
  try {
    const data = await backend('verify_password', { password: passwordForm.password })
    if (!data.unlocked) {
      passwordForm.error = '密码不正确。'
      return
    }
    state.unlocked = true
    passwordForm.password = ''
    await refreshSummary()
  } catch (error) {
    passwordForm.error = error.message
  } finally {
    busy.value = false
  }
}

async function chooseLibrary() {
  const selected = await api.pickFolder({
    title: '选择 AI 档案资料库保存位置',
    defaultPath: state.libraryDir || undefined,
  })
  if (!selected) return
  const data = await backend('set_library_dir', { path: selected })
  state.libraryDir = data.library_dir
  await refreshSummary()
}

async function chooseSource() {
  const selected = await api.pickFolder({
    title: '选择要导入整理的资料文件夹',
    defaultPath: scan.sourceDir || state.libraryDir || undefined,
  })
  if (selected) scan.sourceDir = selected
}

// ── 拖拽 / 选择文件上传：拖进来或点选择，自动进资料库 ──
const dragOver = ref(false)
async function importPaths(paths) {
  const list = (paths || []).filter(Boolean)
  if (!list.length) return
  if (!state.libraryDir) {
    await chooseLibrary()
    if (!state.libraryDir) return
  }
  if (scan.running) return
  scan.running = true
  scan.result = null
  resetProgress()
  progress.stage = 'import'
  progress.stageLabel = '正在导入资料库'
  try {
    const result = await backend('import_files', { paths: list, import_mode: scan.importMode })
    scan.result = result
    progress.stage = 'done'
    progress.stageLabel = '已完成'
    progress.donePages = result.billable_pages + result.skipped_pages + result.failed_pages
    progress.totalPages = result.total_pages
    progress.successPages = result.billable_pages
    progress.skippedPages = result.skipped_pages
    progress.failedPages = result.failed_pages
    await refreshSummary()
    await switchToLibrary()   // 导入完直接去识别队列
  } catch (error) {
    progress.stage = 'failed'
    progress.stageLabel = '导入失败'
    progress.currentFile = error.message
    window.alert('导入失败：' + error.message)
  } finally {
    scan.running = false
  }
}
function onDropFiles(e) {
  dragOver.value = false
  const files = Array.from((e.dataTransfer && e.dataTransfer.files) || [])
  const paths = files.map((f) => api.getPathForFile(f))
  importPaths(paths)
}
async function pickAndImport() {
  const paths = await api.pickFiles({})
  importPaths(paths)
}

async function startScan() {
  if (!canStartScan.value || scan.running) return
  scan.running = true
  scan.result = null
  resetProgress()
  try {
    const result = await backend('scan_folder', {
      path: scan.sourceDir,
      recursive: scan.recursive,
      import_mode: scan.importMode,
    })
    scan.result = result
    progress.stage = 'done'
    progress.stageLabel = '已完成'
    progress.donePages = result.billable_pages + result.skipped_pages + result.failed_pages
    progress.totalPages = result.total_pages
    progress.successPages = result.billable_pages
    progress.skippedPages = result.skipped_pages
    progress.failedPages = result.failed_pages
    await refreshSummary()
  } catch (error) {
    progress.stage = 'failed'
    progress.stageLabel = '任务失败'
    progress.currentFile = error.message
  } finally {
    scan.running = false
  }
}

async function openPath(path) {
  if (!path) return
  await api.openExternalPath(path)
}

async function copySerial() {
  await api.copy(state.serial || '')
}

function applyProgress(message) {
  if (message.event === 'aidoc_recognize') {
    if (message.file) recog.current = message.file
    if (message.stage_label) recog.stageLabel = message.stage_label
    return
  }
  if (message.event !== 'aidoc_progress') return
  progress.stage = message.stage || progress.stage
  progress.stageLabel = message.stage_label || progress.stageLabel
  progress.currentFile = message.current_file || progress.currentFile
  progress.donePages = Number(message.done_pages ?? progress.donePages ?? 0)
  progress.totalPages = Number(message.total_pages ?? progress.totalPages ?? 0)
  progress.successPages = Number(message.success_pages ?? progress.successPages ?? 0)
  progress.skippedPages = Number(message.skipped_pages ?? progress.skippedPages ?? 0)
  progress.failedPages = Number(message.failed_pages ?? progress.failedPages ?? 0)
}

function statusLabel(status) {
  return {
    imported: '已导入',
    duplicate: '重复跳过',
    failed: '失败',
  }[status] || '已入库'
}

// ───────────── 识别队列 / 资料库 ─────────────
const view = ref('workbench')
const meta = reactive({ types: [], list_columns: [], profiles: {}, default_profile: [] })
const lib = reactive({
  docs: [],
  stats: { total: 0, unrecognized: 0, pending: 0, confirmed: 0, duplicate: 0 },
  filterStatus: '',
  filterType: '',
  onlyUnrecognized: false,
  loading: false,
  error: '',
  page: 1,
  perPage: 20,
  total: 0,
  totalPages: 1,
  jumpPage: 1,
})
const detail = reactive({
  open: false, id: 0, file_name: '', document_type: 'other',
  values: {}, ai_confidence: 0, busy: false, error: '',
})

// AI 识别进度（单份或一键批量都用它，让用户看见在干活）
const recog = reactive({
  running: false, total: 0, done: 0, current: '', stageLabel: '',
  aiOk: 0, aiFail: 0, lastError: '',
})
const recogPercent = computed(() => {
  if (!recog.total) return recog.running ? 10 : 0
  return Math.min(100, Math.round((recog.done / recog.total) * 100))
})

// 勾选选择：可任意多选（全选用于「统一确认」）；识别时内部限每批 10 个（识别慢、扣费）。
const MAX_RECOG = 10
const selected = reactive(new Set())
const selectedCount = computed(() => selected.size)
const anySelected = computed(() => selected.size > 0)
// 选中里「已识别待确认」的数量（决定「确认选中」按钮）
const selectedConfirmable = computed(() => lib.docs.filter((d) => selected.has(d.id) && d.recognized && d.review_status !== 'confirmed').length)
function toggleSelect(d) {
  if (selected.has(d.id)) selected.delete(d.id)
  else selected.add(d.id)
}
function selectUnrecognized() {
  selected.clear()
  for (const d of lib.docs) if (!d.recognized) selected.add(d.id)
}
function toggleSelectAll() {
  if (selected.size) { selected.clear(); return }
  for (const d of lib.docs) selected.add(d.id)
}

const unrecognizedDocs = computed(() => lib.docs.filter((d) => !d.recognized))
// 选中某个类型 → 列表换成该类型的专属字段列；「全部」→ 总预览 4 列。
const activeColumns = computed(() => {
  const prof = lib.filterType ? meta.profiles[lib.filterType] : null
  if (prof && prof.length) return prof.map((f) => ({ key: f.source, label: f.label }))
  return meta.list_columns
})
const gridStyle = computed(() => ({
  gridTemplateColumns: `34px 1.6fr repeat(${activeColumns.value.length || 4}, minmax(90px, 1fr)) 0.9fr 1.35fr`,
}))
const detailFields = computed(() => meta.profiles[detail.document_type] || meta.default_profile)

async function loadMeta() {
  if (meta.types.length) return
  const data = await backend('document_meta')
  meta.types = data.types || []
  meta.list_columns = data.list_columns || []
  meta.profiles = data.profiles || {}
  meta.default_profile = data.default_profile || []
}

async function loadDocs() {
  lib.loading = true
  lib.error = ''
  try {
    const args = {}
    if (!lib.onlyUnrecognized && lib.filterStatus) args.review_status = lib.filterStatus
    if (lib.onlyUnrecognized) args.only_unrecognized = true
    if (lib.filterType) args.document_type = lib.filterType
    args.page = lib.page
    args.per_page = lib.perPage
    const data = await backend('list_documents', args)
    const docs = (data.documents || []).map((x) => ({ ...x, busy: false }))
    lib.docs = docs
    lib.stats = data.stats || lib.stats
    lib.page = Number(data.pagination?.page || 1)
    lib.total = Number(data.pagination?.total || 0)
    lib.totalPages = Math.max(1, Number(data.pagination?.total_pages || 1))
    lib.jumpPage = lib.page
  } catch (error) {
    // 刷新失败不等于资料库为空。保留现有列表，避免用户误以为文件丢失。
    lib.error = error?.message || '无法读取本地资料库'
  } finally {
    lib.loading = false
  }
}

async function reloadAllDocsAfterRecognition() {
  // 识别会把「未识别」改成「待确认」，也可能改变资料类型。
  // 若沿用识别前筛选，刚处理完的文件会从当前列表消失，看起来像被删除。
  lib.onlyUnrecognized = false
  lib.filterStatus = ''
  lib.filterType = ''
  lib.page = 1
  await loadDocs()
}

async function switchToLibrary() {
  view.value = 'library'
  try {
    await loadMeta()
    await loadDocs()
  } catch (e) {
    /* 未设资料库时静默 */
  }
}

function setStatusFilter(status) {
  selected.clear()
  lib.onlyUnrecognized = false
  lib.filterStatus = status
  lib.page = 1
  loadDocs()
}
function setUnrecognized() {
  selected.clear()
  lib.onlyUnrecognized = true
  lib.filterStatus = ''
  lib.page = 1
  loadDocs()
}
function setTypeFilter(type) {
  selected.clear()
  lib.filterType = type
  lib.page = 1
  loadDocs()
}

function goLibraryPage(page) {
  selected.clear()
  lib.page = Math.max(1, Math.min(lib.totalPages, Number(page) || 1))
  loadDocs()
}

function jumpLibraryPage() {
  goLibraryPage(lib.jumpPage)
}

function reviewClass(d) {
  if (!d.recognized) return 'unrecognized'
  return { pending_review: 'pending', confirmed: 'confirmed', rejected: 'rejected' }[d.review_status] || 'pending'
}
function reviewLabel(d) {
  if (!d.recognized) return '未识别'
  return { pending_review: '待确认', confirmed: '已确认', rejected: '已驳回' }[d.review_status] || '待确认'
}

async function recognizeOne(d) {
  if (d.busy || recog.running) return
  d.busy = true
  Object.assign(recog, { running: true, total: 1, done: 0, current: d.file_name, stageLabel: '准备识别…', aiOk: 0, aiFail: 0, lastError: '' })
  try {
    const r = await backend('analyze_document', { id: d.id })
    recog.done = 1
    if (r.ai_available) recog.aiOk = 1
    else { recog.aiFail = 1; recog.lastError = r.ai_error || 'AI 未识别' }
    await reloadAllDocsAfterRecognition()
  } catch (error) {
    recog.lastError = error.message
    alert('识别失败：' + error.message)
  } finally {
    recog.running = false
    d.busy = false
  }
}
async function confirmOne(d) {
  if (d.busy || recog.running) return
  d.busy = true
  try {
    const r = await backend('confirm_document', {
      id: d.id, document_type: d.document_type, values: d.values || {}, review_status: 'confirmed',
    })
    await loadDocs()
    if (r.moved_to) recog.lastError = '' // 清掉旧提示
  } catch (e) {
    window.alert('确认失败：' + e.message)
  } finally {
    d.busy = false
  }
}
async function deleteOne(d) {
  if (d.busy || recog.running) return
  const confirmed = window.confirm(
    `确定永久删除“${d.file_name}”吗？\n\n` +
    '将删除资料库中的实际文件和资料记录，无法恢复。\n' +
    '复制管理：保留导入前的库外原文件；仅建索引：会删除被索引的原文件。'
  )
  if (!confirmed) return
  d.busy = true
  try {
    await backend('delete_document', { id: d.id })
    selected.delete(d.id)
    if (detail.open && detail.id === d.id) detail.open = false
    await loadDocs()
    await refreshSummary()
  } catch (error) {
    window.alert('删除失败：' + error.message)
  } finally {
    d.busy = false
  }
}
async function recognizeSelected() {
  if (recog.running) return
  let targets = lib.docs.filter((d) => selected.has(d.id))
  if (!targets.length) return
  if (targets.length > MAX_RECOG) {
    if (!window.confirm(`选了 ${targets.length} 个，识别较慢且按页扣费。这次先识别前 ${MAX_RECOG} 个，确定吗？`)) return
    targets = targets.slice(0, MAX_RECOG)
  }
  Object.assign(recog, { running: true, total: targets.length, done: 0, current: '', stageLabel: '准备识别…', aiOk: 0, aiFail: 0, lastError: '' })
  for (const d of targets) {
    recog.current = d.file_name
    try {
      const r = await backend('analyze_document', { id: d.id })
      if (r.ai_available) recog.aiOk++
      else { recog.aiFail++; if (r.ai_error) recog.lastError = r.ai_error }
    } catch (e) {
      recog.aiFail++
      recog.lastError = e.message
    }
    recog.done++
  }
  recog.running = false
  selected.clear()
  await reloadAllDocsAfterRecognition()
}
// 全选统一确认：把选中的「已识别待确认」一次性确认入库（各自规范重命名 + 归类移动），不调 AI、不扣费。
async function confirmSelected() {
  if (recog.running) return
  const targets = lib.docs.filter((d) => selected.has(d.id) && d.recognized && d.review_status !== 'confirmed')
  if (!targets.length) { window.alert('选中的文件里没有「待确认」的（请先识别）。'); return }
  Object.assign(recog, { running: true, total: targets.length, done: 0, current: '', stageLabel: '正在确认入库 + 归类…', aiOk: 0, aiFail: 0, lastError: '' })
  for (const d of targets) {
    recog.current = d.file_name
    try {
      await backend('confirm_document', { id: d.id, document_type: d.document_type, values: d.values || {}, review_status: 'confirmed' })
    } catch (e) {
      recog.aiFail++
      recog.lastError = e.message
    }
    recog.done++
  }
  recog.running = false
  selected.clear()
  await loadDocs()
}
async function recognizeAll() {
  if (recog.running) return
  const targets = unrecognizedDocs.value.slice()
  if (!targets.length) return
  Object.assign(recog, { running: true, total: targets.length, done: 0, current: '', stageLabel: '准备识别…', aiOk: 0, aiFail: 0, lastError: '' })
  for (const d of targets) {
    recog.current = d.file_name
    try {
      const r = await backend('analyze_document', { id: d.id })
      if (r.ai_available) recog.aiOk++
      else { recog.aiFail++; if (r.ai_error) recog.lastError = r.ai_error }
    } catch (e) {
      recog.aiFail++
      recog.lastError = e.message
    }
    recog.done++
  }
  recog.running = false
  await reloadAllDocsAfterRecognition()
}

async function openDetail(id) {
  detail.error = ''
  try {
    const data = await backend('get_document', { id })
    detail.id = data.id
    detail.file_name = data.file_name
    detail.document_type = data.document_type || 'other'
    detail.ai_confidence = data.ai_confidence || 0
    const values = {}
    for (const row of data.profile || []) values[row.source] = row.value || ''
    detail.values = values
    detail.open = true
  } catch (error) {
    alert('打开失败：' + error.message)
  }
}
function closeDetail() {
  detail.open = false
}
async function recognizeInDetail() {
  detail.busy = true
  detail.error = ''
  try {
    await backend('analyze_document', { id: detail.id })
    await reloadAllDocsAfterRecognition()
    await openDetail(detail.id)
  } catch (error) {
    detail.error = '识别失败：' + error.message
  } finally {
    detail.busy = false
  }
}
async function confirmDetail(status) {
  detail.busy = true
  detail.error = ''
  try {
    await backend('confirm_document', {
      id: detail.id,
      document_type: detail.document_type,
      values: detail.values,
      review_status: status,
    })
    detail.open = false
    await loadDocs()
  } catch (error) {
    detail.error = '保存失败：' + error.message
  } finally {
    detail.busy = false
  }
}

// ── AI 资料员：描述要办的事 → 匹配材料 → 复制到一个文件夹 ──
const finder = reactive({ query: '', loading: false, results: [], neededTypes: [], picked: new Set(), gathered: '' })
async function findMaterials() {
  if (finder.loading) return
  finder.loading = true
  finder.gathered = ''
  try {
    const r = await backend('find_materials', { query: finder.query })
    finder.results = r.results || []
    finder.neededTypes = r.needed_types || []
    finder.picked = new Set(finder.results.map((x) => x.id))  // 默认全选匹配到的
  } catch (e) {
    window.alert('查找失败：' + e.message)
  } finally {
    finder.loading = false
  }
}
function togglePick(id) {
  if (finder.picked.has(id)) finder.picked.delete(id)
  else finder.picked.add(id)
}
async function gatherMaterials() {
  const ids = Array.from(finder.picked)
  if (!ids.length) { window.alert('请先勾选要整理的材料。'); return }
  finder.loading = true
  try {
    const r = await backend('gather_to_folder', { ids })
    finder.gathered = r.dir
    await api.openExternalPath(r.dir)
    await loadCacheInfo()
  } catch (e) {
    window.alert('整理失败：' + e.message)
  } finally {
    finder.loading = false
  }
}

// 整理缓存：每次「整理到文件夹」会复制一份副本到临时目录，积累后可一键清理（不动原合同）
const cache = reactive({ count: 0, bytes: 0, over: false })
function fmtSize(b) {
  if (!b) return '0 MB'
  if (b >= 1024 ** 3) return (b / 1024 ** 3).toFixed(2) + ' GB'
  return (b / 1024 ** 2).toFixed(1) + ' MB'
}
async function loadCacheInfo() {
  try {
    const r = await backend('cache_info')
    cache.count = r.count || 0
    cache.bytes = r.bytes || 0
    cache.over = !!r.over_limit
  } catch {}
}
async function clearCache() {
  if (!cache.count) return
  if (!window.confirm(`确定清理 ${cache.count} 个整理缓存文件夹（${fmtSize(cache.bytes)}）吗？\n这些只是整理时复制出来的副本，不影响资料库和原合同。`)) return
  try {
    const r = await backend('clear_cache')
    await loadCacheInfo()
    let msg = `已清理 ${r.removed} 个文件夹，释放 ${fmtSize(r.freed_bytes)}。`
    if (r.locked) msg += `\n有 ${r.locked} 个正在被打开/占用，关掉文件夹窗口后再清一次即可。`
    window.alert(msg)
  } catch (e) {
    window.alert('清理失败：' + e.message)
  }
}
async function openFinder() {
  view.value = 'finder'
  loadCacheInfo()
  loadTrainingNotes()
  loadTemplateResources()
  await loadConversations()
  if (!chat.messages.length && conversations.items.length) await loadConversation(conversations.items[0].id)
  if (!chat.messages.length) newConversation()
}

// ── AI 资料员·聊天对话（微信机器人式：回车发送 / Shift+回车换行）──
const resources = reactive({
  open: false, loading: false, rebuilding: false, saving: false,
  templates: [], active: 0, error: '',
  form: { id: 0, name: '', type_label: '', status: '', source_file_name: '', template_text: '', enabled: true, variables: [] },
})

function editTemplateResource(item) {
  Object.assign(resources.form, {
    id: item.id,
    name: item.name || '',
    type_label: item.type_label || '',
    status: item.status || 'active',
    source_file_name: item.source_file_name || '',
    template_text: item.template_text || '',
    enabled: item.enabled !== false,
    variables: item.variables || [],
  })
  resources.error = ''
}

async function loadTemplateResources() {
  if (!state.unlocked || resources.loading) return
  resources.loading = true
  try {
    const result = await backend('templates_list')
    resources.templates = result.templates || []
    resources.active = result.active || 0
    if (resources.form.id) {
      const current = resources.templates.find((item) => item.id === resources.form.id)
      if (current) editTemplateResource(current)
      else Object.assign(resources.form, { id: 0 })
    }
  } catch (e) {
    resources.error = e.message
  } finally {
    resources.loading = false
  }
}

async function openTemplateResources() {
  resources.open = true
  await loadTemplateResources()
  if (!resources.form.id && resources.templates.length) editTemplateResource(resources.templates[0])
}

async function rebuildTemplateResources() {
  if (resources.rebuilding) return
  resources.rebuilding = true
  resources.error = ''
  try {
    const result = await backend('templates_rebuild')
    await loadTemplateResources()
    if (!resources.form.id && resources.templates.length) editTemplateResource(resources.templates[0])
    window.alert(`已扫描 ${result.processed || 0} 份资料，资源池现已提炼/更新 ${result.templates || 0} 个模板。`)
  } catch (e) {
    resources.error = e.message
  } finally {
    resources.rebuilding = false
  }
}

async function saveTemplateResource() {
  if (!resources.form.id || resources.saving) return
  resources.saving = true
  resources.error = ''
  try {
    const result = await backend('template_save', {
      id: resources.form.id,
      name: resources.form.name,
      template_text: resources.form.template_text,
      enabled: resources.form.enabled,
    })
    await loadTemplateResources()
    editTemplateResource(result.template)
  } catch (e) {
    resources.error = e.message
  } finally {
    resources.saving = false
  }
}

async function deleteTemplateResource() {
  if (!resources.form.id) return
  if (!window.confirm(`确定删除模板“${resources.form.name}”吗？\n只删除资源池模板，不删除原始资料。`)) return
  try {
    await backend('template_delete', { id: resources.form.id })
    Object.assign(resources.form, { id: 0, name: '', template_text: '', variables: [] })
    await loadTemplateResources()
    if (resources.templates.length) editTemplateResource(resources.templates[0])
  } catch (e) {
    resources.error = e.message
  }
}

const training = reactive({
  open: false,
  loading: false,
  saving: false,
  notes: [],
  error: '',
  form: { id: 0, title: '', trigger_keywords: '', instruction: '', enabled: true },
})

function newTrainingNote() {
  Object.assign(training.form, { id: 0, title: '', trigger_keywords: '', instruction: '', enabled: true })
  training.error = ''
}

function editTrainingNote(note) {
  Object.assign(training.form, {
    id: note.id,
    title: note.title || '',
    trigger_keywords: note.trigger_keywords || '',
    instruction: note.instruction || '',
    enabled: note.enabled !== false,
  })
  training.error = ''
}

async function loadTrainingNotes() {
  if (!state.unlocked || training.loading) return
  training.loading = true
  try {
    const result = await backend('assistant_notes_list')
    training.notes = result.notes || []
  } catch (e) {
    training.error = e.message
  } finally {
    training.loading = false
  }
}

async function openTrainingNotes() {
  training.open = true
  await loadTrainingNotes()
  if (!training.form.id && training.notes.length) editTrainingNote(training.notes[0])
}

async function saveTrainingNote() {
  if (training.saving) return
  training.saving = true
  training.error = ''
  try {
    const result = await backend('assistant_note_save', {
      id: training.form.id || undefined,
      title: training.form.title,
      trigger_keywords: training.form.trigger_keywords,
      instruction: training.form.instruction,
      enabled: training.form.enabled,
    })
    await loadTrainingNotes()
    editTrainingNote(result.note)
  } catch (e) {
    training.error = e.message
  } finally {
    training.saving = false
  }
}

async function deleteTrainingNote() {
  if (!training.form.id) return
  if (!window.confirm(`确定删除培训笔记“${training.form.title}”吗？`)) return
  try {
    await backend('assistant_note_delete', { id: training.form.id })
    newTrainingNote()
    await loadTrainingNotes()
  } catch (e) {
    training.error = e.message
  }
}

const CHAT_GREETING = '你好，我是你的 AI 档案秘书👋 可以帮你查找档案、整理材料，也可以根据要求起草合同内容。默认只查询和回答；需要导出材料时，请先勾选下方“需要整理文件”，还可以选择给导出副本添加水印。'
const conversations = reactive({
  items: [], loading: false, currentId: '', currentTitle: '', dir: '', error: '',
})

function weekStart(value) {
  const date = value ? new Date(value) : new Date()
  const safe = Number.isNaN(date.getTime()) ? new Date() : date
  safe.setHours(0, 0, 0, 0)
  const day = safe.getDay() || 7
  safe.setDate(safe.getDate() - day + 1)
  return safe
}

const chatGroups = computed(() => {
  const groups = new Map()
  const currentWeek = weekStart(new Date()).getTime()
  for (const item of conversations.items) {
    const start = weekStart(item.updated_at)
    const diff = Math.round((currentWeek - start.getTime()) / (7 * 86400000))
    const key = start.toISOString().slice(0, 10)
    const label = diff === 0 ? '本周' : diff === 1 ? '上周' : `${start.getFullYear()}年${start.getMonth() + 1}月${start.getDate()}日当周`
    if (!groups.has(key)) groups.set(key, { key, label, items: [] })
    groups.get(key).items.push(item)
  }
  return [...groups.values()]
})

function formatConversationAge(value) {
  const time = new Date(value).getTime()
  if (!time) return ''
  const seconds = Math.max(0, Math.floor((Date.now() - time) / 1000))
  if (seconds < 60) return '刚刚'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}小时`
  if (seconds < 86400 * 7) return `${Math.floor(seconds / 86400)}天`
  return `${Math.floor(seconds / (86400 * 7))}周`
}

async function loadConversations() {
  if (!state.unlocked || conversations.loading) return
  conversations.loading = true
  conversations.error = ''
  try {
    const result = await backend('assistant_conversations_list')
    conversations.items = result.conversations || []
    conversations.dir = result.dir || ''
  } catch (e) {
    conversations.error = e.message
  } finally {
    conversations.loading = false
  }
}

function newConversation() {
  if (chat.busy) return
  conversations.currentId = ''
  conversations.currentTitle = '新对话'
  chat.messages = []
  chat.input = ''
  pushMsg('ai', CHAT_GREETING)
}

function restoreSavedMessage(item) {
  return {
    id: ++chatSeq,
    role: item.role === 'user' ? 'user' : 'ai',
    text: item.text || '',
    created_at: item.created_at || '',
    materials: (item.materials || []).map((m) => ({ ...m, picked: m.picked !== false })),
    gathered: '', gathering: false, exportError: '', organize: Boolean(item.organize),
    useWatermark: Boolean(item.useWatermark), watermarkText: item.watermarkText || '',
    generatedDocument: item.generated_document || null,
  }
}

async function loadConversation(id) {
  if (!id || chat.busy) return
  conversations.error = ''
  try {
    const result = await backend('assistant_conversation_get', { id })
    const data = result.conversation || {}
    conversations.currentId = data.id || id
    conversations.currentTitle = data.title || '未命名对话'
    chat.messages = (data.messages || []).map(restoreSavedMessage)
    chat.input = ''
    nextTick(() => { const el = document.querySelector('.chat-scroll'); if (el) el.scrollTop = el.scrollHeight })
  } catch (e) {
    conversations.error = e.message
    await loadConversations()
  }
}

async function saveCurrentConversation() {
  const messages = chat.messages.filter((m) => m.text && !m.gathering)
  if (!messages.some((m) => m.role === 'user')) return
  const result = await backend('assistant_conversation_save', {
    id: conversations.currentId || undefined,
    title: conversations.currentTitle || undefined,
    messages,
  })
  const saved = result.conversation || {}
  conversations.currentId = saved.id || conversations.currentId
  conversations.currentTitle = saved.title || conversations.currentTitle
  conversations.dir = result.dir || conversations.dir
  await loadConversations()
}

async function renameConversation(item) {
  const title = window.prompt('修改对话名称', item.title || '')
  if (title === null || !title.trim()) return
  try {
    await backend('assistant_conversation_rename', { id: item.id, title: title.trim() })
    if (conversations.currentId === item.id) conversations.currentTitle = title.trim()
    await loadConversations()
  } catch (e) {
    conversations.error = e.message
  }
}

async function deleteConversation(item) {
  if (!window.confirm(`确定删除对话“${item.title}”吗？\n删除后无法恢复。`)) return
  try {
    await backend('assistant_conversation_delete', { id: item.id })
    if (conversations.currentId === item.id) newConversation()
    await loadConversations()
  } catch (e) {
    conversations.error = e.message
  }
}

async function openConversationFolder() {
  if (!conversations.dir) await loadConversations()
  if (conversations.dir) await openPath(conversations.dir)
}

const chat = reactive({
  messages: [], input: '', busy: false,
  needOrganize: false, useWatermark: false, watermarkText: '',
})
let chatSeq = 0
function pushMsg(role, text, materials, extra = {}) {
  chat.messages.push({
    id: ++chatSeq, role, text,
    created_at: new Date().toISOString(),
    materials: (materials || []).map((m) => ({ ...m, picked: true })),
    gathered: '', gathering: false, exportError: '', organize: false, useWatermark: false, watermarkText: '',
    generatedDocument: null,
    ...extra,
  })
  nextTick(() => { const el = document.querySelector('.chat-scroll'); if (el) el.scrollTop = el.scrollHeight })
  return chat.messages[chat.messages.length - 1]
}
async function sendChat() {
  const text = chat.input.trim()
  if (!text || chat.busy) return
  const options = {
    organize: Boolean(chat.needOrganize),
    useWatermark: Boolean(chat.needOrganize && chat.useWatermark),
    watermarkText: chat.needOrganize && chat.useWatermark ? chat.watermarkText.trim() : '',
  }
  chat.input = ''
  pushMsg('user', text)
  chat.busy = true
  try {
    await saveCurrentConversation()
  } catch (e) {
    conversations.error = '聊天记录暂未保存：' + e.message
  }
  const reply = pushMsg('ai', options.organize ? '正在核对并准备材料…' : '正在核对资料库…', [], options)
  try {
    const history = chat.messages
      .filter((m) => m !== reply)
      .slice(-12, -1)
      .map((m) => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.text }))
    const r = await backend('assistant_chat', {
      message: text,
      history,
      need_organize: options.organize,
      use_watermark: options.useWatermark,
      watermark_text: options.watermarkText,
    })
    reply.text = r.reply || '我已经核对了当前库存。'
    reply.materials = options.organize ? (r.materials || []).map((x) => ({ ...x, picked: true })) : []
    if (r.contract_job) {
      reply.text += '\n\n正在根据库存模板生成新合同文件…'
      try {
        const generated = await backend('generate_contract', { job: r.contract_job })
        reply.generatedDocument = generated
        // 模板合同只用于生成，不再作为“整理材料”复制，避免用户再次打开旧合同。
        reply.materials = reply.materials.filter((item) => item.id !== generated.source_document_id)
        reply.text = reply.text.replace('\n\n正在根据库存模板生成新合同文件…', '')
        reply.text += `\n\n✓ 已生成新合同：${generated.file_name}`
        await loadCacheInfo()
      } catch (generateError) {
        reply.text = reply.text.replace('\n\n正在根据库存模板生成新合同文件…', '')
        reply.text += '\n\n合同文件未生成：' + generateError.message
      }
    } else if (r.document_job) {
      reply.text += '\n\n正在生成新文书文件…'
      try {
        const generated = await backend('generate_document', { job: r.document_job })
        reply.generatedDocument = generated
        reply.text = reply.text.replace('\n\n正在生成新文书文件…', '')
        reply.text += `\n\n✓ 已生成新文书：${generated.file_name}`
        await loadCacheInfo()
      } catch (generateError) {
        reply.text = reply.text.replace('\n\n正在生成新文书文件…', '')
        reply.text += '\n\n文书文件未生成：' + generateError.message
      }
    }
    if (options.useWatermark && r.watermark_text) {
      reply.watermarkText = r.watermark_text
      chat.watermarkText = r.watermark_text
    }
    reply.trainingNotesUsed = r.training_notes_used || []
  } catch (e) {
    reply.text = '出错了：' + e.message
  } finally {
    chat.busy = false
    try {
      await saveCurrentConversation()
    } catch (e) {
      conversations.error = '聊天记录保存失败：' + e.message
    }
    nextTick(() => { const el = document.querySelector('.chat-scroll'); if (el) el.scrollTop = el.scrollHeight })
  }
}
function onChatKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat() }
}
async function openGeneratedDocument(msg) {
  const path = msg.generatedDocument?.file_path
  if (!path) return
  const opened = await api.openExternalPath(path)
  if (opened?.ok === false) {
    msg.generatedDocument = null
    msg.text += '\n\n生成的合同缓存已被清理，请重新生成。'
  }
}
async function gatherFromMsg(msg) {
  if (msg.gathering) return
  if (msg.gathered) {
    const opened = await api.openExternalPath(msg.gathered)
    if (opened?.ok === false) {
      msg.exportError = opened.error || '整理文件夹已被删除，请重新整理。'
      msg.gathered = ''
    }
    return
  }
  const ids = (msg.materials || []).filter((m) => m.picked).map((m) => m.id)
  if (!ids.length) { msg.exportError = '请先勾选要整理的材料。'; return }
  msg.gathering = true
  msg.exportError = ''
  try {
    const r = await backend('gather_to_folder', {
      ids,
      use_watermark: Boolean(msg.useWatermark),
      watermark_text: msg.useWatermark ? (msg.watermarkText || '').trim() : '',
    })
    msg.gathered = r.dir
    const opened = await api.openExternalPath(r.dir)
    if (opened?.ok === false) throw new Error(opened.error || '无法打开整理文件夹')
    await loadCacheInfo()
    const wm = msg.useWatermark ? `，其中 ${r.watermarked || 0} 份已添加水印` : ''
    const skipped = (r.watermark_skipped || []).length ? `\n提示：${r.watermark_skipped.join('；')}` : ''
    pushMsg('ai', `✓ 已把 ${r.count || ids.length} 份材料整理到一个文件夹${wm}并打开：\n${r.dir}${skipped}`)
    try { await saveCurrentConversation() } catch (saveError) { conversations.error = '聊天记录保存失败：' + saveError.message }
  } catch (e) {
    msg.exportError = '整理失败：' + e.message
  } finally {
    msg.gathering = false
  }
}

onMounted(async () => {
  const off = api.onBackendEvent(applyProgress)
  window.addEventListener('beforeunload', off, { once: true })
  try {
    await loadState()
    await registerDevice()
    // 提前载入各类型版面字段，保证详情页任何时候都能按类型显示不同字段。
    try { await loadMeta() } catch {}
    if (state.unlocked) await refreshSummary()
  } finally {
    booting.value = false
  }
})
</script>
