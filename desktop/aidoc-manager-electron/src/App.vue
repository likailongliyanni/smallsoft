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
          <button class="nav-item active"><LayoutDashboard :size="18" />工作台</button>
          <button class="nav-item"><FolderInput :size="18" />资料导入</button>
          <button class="nav-item"><ListChecks :size="18" />识别队列</button>
          <button class="nav-item"><CreditCard :size="18" />页数额度</button>
          <button class="nav-item"><Settings :size="18" />本地设置</button>
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
              <small>可用额度</small>
              <strong>{{ state.quota.available }} 页</strong>
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
            <div class="panel-head">
              <div>
                <p class="eyebrow">导入向导</p>
                <h2>选择文件夹，按页整理</h2>
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

            <div class="field-group">
              <label>要导入的资料文件夹</label>
              <div class="path-row">
                <input :value="scan.sourceDir || '请选择供应商资料、证件资料或下载目录'" readonly />
                <button class="secondary-btn" :disabled="scan.running" @click="chooseSource">
                  <FolderSearch :size="16" />
                  选择
                </button>
              </div>
            </div>

            <div class="option-row">
              <label class="check-line">
                <input v-model="scan.recursive" type="checkbox" />
                <span>包含子文件夹</span>
              </label>
              <div class="segmented">
                <button :class="{ active: scan.importMode === 'copy' }" :disabled="scan.running" @click="scan.importMode = 'copy'">复制管理</button>
                <button :class="{ active: scan.importMode === 'index' }" :disabled="scan.running" @click="scan.importMode = 'index'">仅建索引</button>
              </div>
            </div>

            <div class="start-row">
              <button class="primary-btn large" :disabled="scan.running || !canStartScan" @click="startScan">
                <Sparkles :size="18" />
                开始扫描整理
              </button>
              <p>{{ scan.running ? '正在处理，请保持软件打开。' : '免费赠送 50 页，按成功识别页数扣费。' }}</p>
            </div>
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
              <span>本次导入 {{ scan.result.created_documents }} 份，成功计费页 {{ scan.result.billable_pages }} 页。</span>
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
      </section>
    </template>
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Archive,
  BookOpenCheck,
  CheckCircle2,
  Copy,
  CreditCard,
  ExternalLink,
  FileText,
  Files,
  Fingerprint,
  FolderCog,
  FolderInput,
  FolderSearch,
  Gauge,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  LockKeyhole,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sparkles,
  Unlock,
  Wifi,
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
  quota: { free: 50, paid: 0, available: 50, used: 0, unit: 'page' },
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
  const result = await api.backend(cmd, args)
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
}

async function registerDevice() {
  const data = await backend('register')
  state.online = Boolean(data.online)
  state.serial = data.serial || state.serial
  state.quota = data.quota || state.quota
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

onMounted(async () => {
  const off = api.onBackendEvent(applyProgress)
  window.addEventListener('beforeunload', off, { once: true })
  try {
    await loadState()
    await registerDevice()
    if (state.unlocked) await refreshSummary()
  } finally {
    booting.value = false
  }
})
</script>
