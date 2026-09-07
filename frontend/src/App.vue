<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'                 // 全局消息提示
import { sendChatMessage } from '@/api/chatApi'          // 复用 request 封装
import {
  ChatDotRound, Plus, OfficeBuilding, FirstAidKit, Reading,
  Refresh, Promotion, WarningFilled, EditPen,
} from '@element-plus/icons-vue'

const messages = ref([])         // 消息列表
const inputText = ref('')        // 输入内容
const sessionId = ref(null)      // 会话id，首次为空，后端返回后保存

// 发送消息
async function send() {
  const text = inputText.value.trim()
  if (!text) return                 // 空内容不发
  messages.value.push({ role: 'user', content: text })   // 用户消息立即上屏（右对齐）
  inputText.value = ''              // 清空输入框
  const reply = await getReply(text)      // 获取 AI 回复
  messages.value.push({ role: 'assistant', content: reply })  // 追加 AI 消息（左对齐）
}

// 回复消息
async function getReply(text) {
  try {
    const reqBody = { message: text }
    if (sessionId.value) reqBody.sessionId = sessionId.value   // 有会话id就带上
    const res = await sendChatMessage(reqBody)   // res 已是 {code,msg,data}
    if (res.code === 1) {
      sessionId.value = res.data.sessionId        // 保存会话id
      return res.data.reply
    } else {
      ElMessage.error(res.msg || '请求失败')
      return ''
    }
  } catch (err) {
    console.error('请求异常:', err)
    ElMessage.error('网络异常，请检查后端服务')
    return ''
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
        <el-button type="primary" class="new-chat gbtn"><el-icon :size="16"><Plus/></el-icon><span>开启新对话</span></el-button>

        <div class="side-title">对话历史</div>
        <div class="history-item sel"><el-icon :size="14"><ChatDotRound/></el-icon><span>我最近头痛、头晕，应该挂什么科？</span></div>
        <div class="history-item"><el-icon :size="14"><ChatDotRound/></el-icon><span>我腰疼，手麻，怎么办</span></div>
        <div class="history-item"><el-icon :size="14"><ChatDotRound/></el-icon><span>什么是糖尿病？</span></div>

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

        <el-main class="chat">
          <!-- 6) v-for：根据 messages 动态渲染消息，:class 按角色区分左右 -->
          <div v-for="(msg, i) in messages" :key="i" class="msg" :class="msg.role">
            <template v-if="msg.role === 'assistant'">
              <div class="avatar"><el-icon :size="18" color="#fff"><FirstAidKit/></el-icon></div>
              <div class="bubble ai">{{ msg.content }}</div>
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
</style>