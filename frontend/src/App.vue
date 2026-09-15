<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { sendChatMessageStream, getSessions, getMessages, deleteSession } from '@/api/chatApi'
import {
  ChatDotRound, Plus, OfficeBuilding, FirstAidKit, Reading,
  Refresh, Promotion, WarningFilled, EditPen,Clock, CopyDocument, Delete,
} from '@element-plus/icons-vue'

const messages = ref([])         // 消息列表
const chatRef = ref(null)        // 聊天区容器引用


const inputText = ref('')        // 输入内容
const sessionId = ref(null)      // 会话id，首次为空，后端 meta 事件返回后保存

const sessions = ref([])         // 会话列表

// 滚动到聊天区底部
function scrollToBottom() {
  nextTick(() => {
    requestAnimationFrame(() => {          // 等下一帧，确保布局/高度已更新
      const el = chatRef.value?.$el || chatRef.value
      if (el) el.scrollTop = el.scrollHeight
    })
  })
}
// 拉取会话列表（左栏历史）
async function loadSessions() {
  try {
    const res = await getSessions({ page: 1, pageSize: 20 })
    if (res.code === 1) sessions.value = res.data.rows
  } catch (e) {
    console.error('拉会话列表失败', e)
  }
}

// 切换会话：拉取该会话消息并复原
async function switchSession(sid) {
  sessionId.value = sid
  try {
    const res = await getMessages(sid)
    if (res.code === 1) {
      messages.value = res.data.rows
      scrollToBottom()                                   // ← 加：切换会话后滚到底
    }
  } catch (e) {
    console.error('拉会话消息失败', e)
  }
}

// 开启新对话：清空聊天区、重置会话
function newChat() {
  messages.value = []
  sessionId.value = null
}

onMounted(loadSessions)          // 页面加载时拉一次会话列表

// 发送消息：改用 SSE 流式，AI 回复逐字上屏（打字效果）
async function send() {
  const text = inputText.value.trim()
  if (!text) return
  messages.value.push({ role: 'user', content: text })    // 用户消息立即上屏
  inputText.value = ''
  messages.value.push({ role: 'assistant', content: '' }) // 先放一条空助手消息
  const aiMsg = messages.value[messages.value.length - 1]
  scrollToBottom()

  const reqBody = { message: text }
  if (sessionId.value) reqBody.sessionId = sessionId.value   // ← 有会话id就带上

  try {
    const res =  await sendChatMessageStream(reqBody)
    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop()
      for (const evt of events) {
        const line = evt.split('\n').find(l => l.startsWith('data: '))
        if (!line) continue
        const data = JSON.parse(line.slice(6))
        if (data.type === 'meta') {
          sessionId.value = data.sessionId    // 从 meta 里拿并保存
        } else if (data.type === 'delta') {
          aiMsg.content += data.content
          scrollToBottom()
        } else if (data.type === 'done') {
          aiMsg.symptoms = data.symptoms
          aiMsg.department = data.department
          aiMsg.disclaimer = data.disclaimer
          aiMsg.medReminder = data.medReminder
          aiMsg.consumeTime = data.consumeTime
        }
      }
    }
    loadSessions()      // 流式结束后刷新会话列表
    scrollToBottom()      // ← 流式完成后再滚一次，保证停在最底部
  } catch (err) {
    console.error('流式请求异常:', err)
    ElMessage.error('网络异常，请检查后端服务')
    aiMsg.content = '（请求失败，请稍后重试）'
  }
}

// 复制 AI 回复文本
async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)   // 写入剪贴板
    ElMessage.success('复制成功')
  } catch (e) {
    ElMessage.error('复制失败，请手动复制')
  }
}
// 删除会话
async function deleteChat(sid) {
  try {
    await ElMessageBox.confirm(
  '删除后，聊天记录将不可恢复。',      // 内容
  '确定删除对话？',                    // 标题
  {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    confirmButtonClass: 'el-button--danger',   // 让"删除"按钮是红色
  }
    )
  } catch {
    return                                   // 用户取消
  }
  try {
    await deleteSession(sid)
    ElMessage.success('已删除')
    if (sid === sessionId.value) newChat()   // 删的是当前会话 → 清空聊天区
    loadSessions()                           // 刷新列表
  } catch (e) {
    console.error('删除失败', e)
    ElMessage.error('删除失败')
  }
}

</script>

<template>
  <el-container class="app">
    <el-container class="body">
      <!-- 左侧卡片 -->
      <el-aside width="250px" class="sidebar">
        <div class="brand">
          <div class="brand-logo"><el-icon :size="20" color="#fff"><FirstAidKit/></el-icon></div>
          <div>
            <div class="brand-name">智慧问诊Agent系统</div>
            <div class="brand-sub">智能医疗 · 知识图谱驱动</div>
          </div>
        </div>
        <el-button type="primary" class="new-chat gbtn" @click="newChat"><el-icon :size="16"><Plus/></el-icon><span>开启新对话</span></el-button>

        <div class="side-title">对话历史</div>
        <div v-for="s in sessions" :key="s.sessionId" class="history-item" :class="{ sel: s.sessionId === sessionId }" @click="switchSession(s.sessionId)">
          <el-icon :size="14">
            <ChatDotRound/>
          </el-icon>
          <span class="item-title">{{ s.title }}</span>
          <el-icon class="del" :size="14" @click.stop="deleteChat(s.sessionId)">
            <Delete/>
          </el-icon>
        </div>


        <div class="side-title">我能帮你</div>
        <div class="feature"><div class="feature-ico"><el-icon :size="16"><OfficeBuilding/></el-icon></div><div><div class="feature-name">看病挂号</div><div class="feature-desc">症状/疾病 推荐就诊科室</div></div></div>
        <div class="feature"><div class="feature-ico"><el-icon :size="16"><FirstAidKit/></el-icon></div><div><div class="feature-name">用药建议</div><div class="feature-desc">药物/副作用/禁忌</div></div></div>
        <div class="feature"><div class="feature-ico"><el-icon :size="16"><Reading/></el-icon></div><div><div class="feature-name">医学知识</div><div class="feature-desc">疾病科普与解读</div></div></div>
        <div class="feature"><div class="feature-ico"><span class="alert">!</span></div><div><div class="feature-name">急症识别</div><div class="feature-desc">危险信号即时预警</div></div></div>

        <div class="status-panel">
          <div class="status-title">系统状态 <el-icon class="refresh" :size="14"><Refresh/></el-icon></div>
          <div class="status-row"><span class="dot on"></span>Neo4j 图谱<span class="ok">正常</span></div>
          <div class="status-row"><span class="dot on"></span>向量索引<span class="ok">正常</span></div>
          <div class="status-row"><span class="dot on"></span>Agent 系统<span class="ok">正常</span></div>
        </div>
        <div class="version">v1.0.0 · 仅供参考，请遵医嘱</div>
      </el-aside>

      <!-- 右侧卡片 -->
      <el-container class="right">
        <el-header class="warn-bar">
          <el-icon class="warn-ico"><WarningFilled/></el-icon>
          <span>本系统仅供健康咨询与就医指导，不能替代专业医疗诊断。身体不适请及时就医，切勿自行用药。</span>
        </el-header>


        <el-main class="chat" ref="chatRef">
          <!-- 6) v-for：根据 messages 动态渲染消息，:class 按角色区分左右 -->
          <div v-for="(msg, i) in messages" :key="i" class="msg" :class="msg.role">
            <template v-if="msg.role === 'assistant'">
              <div class="avatar">
                <el-icon :size="18" color="#fff">
                  <FirstAidKit/>
                </el-icon>
              </div>
              <div class="ai-body">
                <div class="card">
                  <div class="card-title">智慧问诊AGENT系统</div>
                  <div class="advice-title">💡 就医建议：</div>
                  <div class="card-text">{{ msg.content }}</div>

                  <div v-if="msg.symptoms && msg.symptoms.length" class="row">
                    <span class="label">症状</span>
                    <el-tag v-for="s in msg.symptoms" :key="s" size="small">{{ s }}</el-tag>
                  </div>

                  <div v-if="msg.department" class="row">
                    <span class="label">推荐科室</span>
                    <el-tag size="small" class="dept">{{ msg.department }}</el-tag>
                  </div>

                  <div v-if="msg.disclaimer" class="disclaimer">
                    <span class="ball">🔴</span><el-icon class="warn-icon"><WarningFilled/></el-icon>
                    {{ msg.disclaimer }}
                  </div>
                  <div v-if="msg.medReminder" class="med-reminder">{{ msg.medReminder }}</div>
                </div>

                <div class="card-footer">
                  <span v-if="msg.consumeTime" class="ms"><el-icon><Clock/></el-icon>{{ msg.consumeTime }} ms</span>
                  <span class="copy" @click="copy(msg.content)"><el-icon><CopyDocument/></el-icon> 复制</span>
                </div>
              </div>
            </template>
            <template v-else>
              <div class="bubble user">{{ msg.content }}</div>
            </template>
          </div>
        </el-main>

        <el-footer class="input-bar" height="76px">
          <!-- 7) v-model 绑定输入内容；@keyup.enter 回车发送 -->
          <el-input v-model="inputText" placeholder="请描述您的症状或健康问题，回车发送" @keyup.enter="send()">
            <template #prefix><el-icon><EditPen/></el-icon></template>
          </el-input>
          <!-- 8) @click 发送按钮 -->
          <el-button type="primary" class="send gbtn" @click="send()"><el-icon :size="16"><Promotion/></el-icon><span>发送</span></el-button>
        </el-footer>
      </el-container>
    </el-container>
  </el-container>
</template>

<style scoped>
.app { height: 100vh; width: 100%; display: flex; flex-direction: column; background: #e9f1ef; --el-color-primary: #2f9e8f; --el-color-primary-light-3: #5cbaac; --el-color-primary-light-5: #8fd0c7; --el-color-primary-light-7: #c2e5df; --el-color-primary-light-8: #d9f0ec; --el-color-primary-light-9: #eef7f5; --el-color-primary-dark-2: #26847a; }
.warn-bar { margin: 16px 16px 4px; background: #fff3e0; color: #e0813d; border-radius: 10px; display: flex; align-items: center; justify-content: flex-start; gap: 8px; font-size: 13px; padding: 12px 16px; box-sizing: border-box; height: auto; min-height: 42px; }
.warn-bar .el-icon { flex-shrink: 0; }
.body { flex: 1; display: flex; flex-direction: row; gap: 20px; padding: 20px 24px 24px; overflow: hidden; box-sizing: border-box; max-width: 1120px; margin: 0 auto; width: 100%; }

.sidebar { background: #fff; border-radius: 16px; border: 1px solid #e3eeeb; padding: 20px 18px; display: flex; flex-direction: column; box-sizing: border-box; flex-shrink: 0; }
.brand { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.brand-logo { width: 32px; height: 32px; border-radius: 9px; background-image: linear-gradient(135deg, #3bb6a5, #26847a); display: flex; align-items: center; justify-content: center; }
.brand-name { font-size: 15px; font-weight: 700; color: #155e52; }
.brand-sub { font-size: 11px; color: #3f7f72; }
.new-chat { width: 100%; margin-bottom: 8px; height: 38px; border-radius: 9px; }
.new-chat .el-icon { margin-right: 4px; }
.gbtn { background-image: linear-gradient(135deg, #3bb6a5, #26847a); border: none; color: #fff; }
.gbtn:hover, .gbtn:focus { background-image: linear-gradient(135deg, #45c0ae, #2d9184); color: #fff; }

.side-title { font-size: 12px; color: #2f9e8f; margin: 8px 0 4px; font-weight: 600; }
.sidebar .side-title:first-of-type { margin-top: 2px; }
.history-item { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 6px; font-size: 12px; color: #303133; cursor: pointer; }
.history-item .el-icon { color: #909399; flex-shrink: 0; }
.history-item.sel { background: #eef7f5; color: #155e52; font-weight: 600; }
.history-item.sel .el-icon { color: #2f9e8f; }

.feature { display: flex; align-items: center; gap: 10px; padding: 8px 8px; border-radius: 6px; cursor: pointer; }
.feature:hover { background: #f5f7fa; }
.feature-ico { width: 28px; height: 28px; border-radius: 8px; background: #e4f4ec; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
.feature-ico .el-icon { color: #2f9e8f; }
.feature-ico .alert { width: 16px; height: 16px; border-radius: 50%; background: #155e52; color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; }
.feature-name { font-size: 12px; color: #303133; font-weight: 600; }
.feature-desc { font-size: 11px; color: #909399; }

.status-panel { margin-top: auto; background: #eef7f5; border: 1px solid #c2e5df; border-radius: 10px; padding: 12px 14px; }
.status-title { font-size: 13px; color: #909399; margin-bottom: 6px; display: flex; align-items: center; justify-content: space-between; }
.status-title .refresh { color: #2f9e8f; }
.status-row { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #303133; padding: 4px 0; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot.on { background: #2e8b57; }
.status-row .ok { margin-left: auto; background: #d9f2e6; color: #1fb565; border-radius: 999px; padding: 1px 8px; font-size: 12px; font-weight: 600; }
.version { margin-top: 12px; font-size: 12px; color: #7fb8a8; text-align: center; }

.right { flex: 1; background: #fff; border-radius: 16px; border: 1px solid #e3eeeb; display: flex; flex-direction: column; overflow: hidden; }
.chat { background: #fff; display: flex; flex-direction: column; overflow-y: auto; padding: 24px 28px; }
.msg { display: flex; margin-bottom: 18px; }
.msg.user { justify-content: flex-end; }
.msg.assistant { align-items: flex-start; gap: 12px; }
.avatar { width: 34px; height: 34px; border-radius: 8px; background-image: linear-gradient(135deg, #3bb6a5, #26847a); flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
.bubble.user { background-image: linear-gradient(135deg, #3bb6a5, #26847a); color: #fff; padding: 11px 16px; border-radius: 12px; max-width: 70%; }
.bubble.ai { background: #f5f7fa; border: 1px solid #ebeef5; border-left: 4px solid #1fc0a5; color: #303133; padding: 11px 16px; border-radius: 12px; max-width: 78%; }

.input-bar { background: #fff; border-top: 1px solid #ebeef5; display: flex; align-items: center; gap: 12px; padding: 14px 20px; box-sizing: border-box; --el-component-size: 40px; }
.input-bar .el-input { flex: 1; --el-input-height: 40px; --el-input-border-radius: 10px; }
.input-bar .el-input .el-input__wrapper { height: 40px; min-height: 40px; border-radius: 10px !important; box-sizing: border-box; }
.input-bar .el-button { margin: 0; }
.send { height: 40px; border-radius: 10px; box-sizing: border-box; }
.send .el-icon { margin-right: 4px; }

.ai-body { flex: 1; display: flex; flex-direction: column; }
.card { width: 100%; background: #fff; border: 1px solid #ebeef5; border-left: 4px solid #1fc0a5; border-radius: 12px; padding: 16px 18px; box-sizing: border-box; }
.card-title { font-size: 12px; color: #155e52; letter-spacing: .5px; margin-bottom: 10px; }
.card-text { font-size: 14px; color: #303133; line-height: 1.7; margin-bottom: 12px; }
.row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.row .label { font-size: 12px; color: #155e52; }
.row .dept { background: #eef7f5; border-color: #2f9e8f; color: #2f9e8f; }
.disclaimer { background: #fff3e0; color: #e0813d; border-radius: 8px; padding: 8px 12px; font-size: 13px; margin-bottom: 10px; }
.card-footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; font-size: 12px; color: #909399; margin-top: 8px; }
.card-footer .ms { display: flex; align-items: center; gap: 4px; }
.card-footer .copy { color: #2f9e8f; cursor: pointer; display: flex; align-items: center; gap: 4px; }
.med-reminder { background: #eef7f5; color: #155e52; border-radius: 8px; padding: 8px 12px; font-size: 13px; margin-bottom: 10px; }
.disclaimer { background: #fff3e0; color: #e0813d; border-radius: 8px; padding: 8px 12px; font-size: 13px; margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }
/* 红球 emoji：去掉自带行高，flex 居中 */
.disclaimer .ball { font-size: 12px; line-height: 1; display: inline-flex; align-items: center; flex-shrink: 0; }
/* Element Plus 图标：同样 flex 居中，大小对齐 */
.disclaimer .warn-icon { color: #e54d42; font-size: 15px; line-height: 1; display: inline-flex; align-items: center; flex-shrink: 0; }
.history-item .item-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-item .del { opacity: 0; transition: opacity .15s; flex-shrink: 0; }
.history-item:hover .del { opacity: 1; color: #f56c6c; }
</style>

<style>
:root {
  --el-color-primary: #2f9e8f;
  --el-color-primary-light-3: #5cbaac;
  --el-color-primary-light-5: #8fd0c7;
  --el-color-primary-light-7: #c2e5df;
  --el-color-primary-light-8: #d9f0ec;
  --el-color-primary-light-9: #eef7f5;
  --el-color-primary-dark-2: #26847a;
}
</style>