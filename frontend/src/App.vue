<script setup>
import { ChatDotRound, Plus, OfficeBuilding, FirstAidKit, Reading, Refresh, Promotion, WarningFilled, EditPen, Clock, CopyDocument } from '@element-plus/icons-vue'
// P0-2 静态骨架：对齐「理想项目界面」原型（手册 16.5）
</script>

<template>
  <el-container class="app">
    <el-container class="body">
      <!-- 左侧：圆角浮动卡片 -->
      <el-aside width="250px" class="sidebar">
        <!-- 品牌头 -->
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
        <div class="feature">
          <div class="feature-ico"><el-icon :size="16"><OfficeBuilding/></el-icon></div>
          <div>
            <div class="feature-name">看病挂号</div>
            <div class="feature-desc">症状/疾病 推荐就诊科室</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-ico"><el-icon :size="16"><FirstAidKit/></el-icon></div>
          <div>
            <div class="feature-name">用药建议</div>
            <div class="feature-desc">药物/副作用/禁忌</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-ico"><el-icon :size="16"><Reading/></el-icon></div>
          <div>
            <div class="feature-name">医学知识</div>
            <div class="feature-desc">疾病科普与解读</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-ico"><span class="alert">!</span></div>
          <div>
            <div class="feature-name">急症识别</div>
            <div class="feature-desc">危险信号即时预警</div>
          </div>
        </div>

        <!-- 系统状态卡片 -->
        <div class="status-panel">
          <div class="status-title">系统状态 <el-icon class="refresh" :size="14"><Refresh/></el-icon></div>
          <div class="status-row"><span class="dot on"></span>Neo4j 图谱<span class="ok">正常</span></div>
          <div class="status-row"><span class="dot on"></span>向量索引<span class="ok">正常</span></div>
          <div class="status-row"><span class="dot on"></span>Agent 系统<span class="ok">正常</span></div>
        </div>

        <div class="version">v1.0.0 · 仅供参考，请遵医嘱</div>
      </el-aside>

      <!-- 右侧卡片：警示条 + 对话区 + 输入区 -->
      <el-container class="right">
        <el-header class="warn-bar">
          <el-icon class="warn-ico"><WarningFilled/></el-icon>
          <span>本系统仅供健康咨询与就医指导，不能替代专业医疗诊断。身体不适请及时就医，切勿自行用药。</span>
        </el-header>
        <el-main class="chat">
          <div class="msg user">
            <div class="bubble">我最近头痛、头晕，应该挂什么科？</div>
          </div>

          <div class="msg assistant">
            <div class="avatar"><el-icon :size="18" color="#fff"><FirstAidKit/></el-icon></div>
            <div class="ai-body">
              <div class="card">
                <div class="card-title">智慧问诊AGENT系统</div>
                <div class="advice-title">💡 就医建议：</div>
                <ul class="advice">
                  <li>携带医保卡、身份证及既往病历、影像资料（如CT/MRI）和近期检查报告。</li>
                  <li>记录头痛/头晕发作的时间、频率、持续时间及诱发因素，以便医生准确判断。</li>
                  <li>就诊前避免剧烈运动，保持情绪平稳；若伴有恶心呕吐或视物旋转，请家属陪同以防跌倒。</li>
                  <li>可能涉及血压测量、神经系统查体、头颅影像学检查（CT/MRI）及血液化验等评估。</li>
                </ul>
                <div class="row"><span class="label">症状</span><el-tag size="small">头痛</el-tag><el-tag size="small">头晕</el-tag></div>
                <div class="row"><span class="label">推荐科室</span><el-tag size="small" class="dept">神经内科</el-tag></div>
                <div class="disclaimer">重要声明：本建议仅供参考，不能替代专业医疗诊断。请及时就医，谨遵医嘱用药！</div>
              </div>
              <div class="card-footer">
                <div class="footer-left">
                  <span class="ms"><el-icon><Clock/></el-icon> 8374 ms</span>
                  <span class="link pill">看病挂号</span>
                </div>
                <span class="link copy"><el-icon><CopyDocument/></el-icon> 复制</span>
              </div>
            </div>
          </div>
        </el-main>

        <el-footer class="input-bar" height="76px">
          <el-input placeholder="请描述您的症状或健康问题，回车发送...">
            <template #prefix><el-icon><EditPen/></el-icon></template>
          </el-input>
          <el-button type="primary" class="send gbtn"><el-icon :size="16"><Promotion/></el-icon><span>发送</span></el-button>
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

/* ---------- 左侧：圆角浮动卡片 ---------- */
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
.history-item.sel .el-icon { color: #2f9e8f; }
.history-item:hover { background: #f5f7fa; }
.history-item.sel { background: #eef7f5; color: #155e52; font-weight: 600; }

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
/* 异常状态样式（后续当某个组件异常时给行加 bad 类） */
.status-row.bad .dot { background: #e74c3c; }
.status-row.bad .ok { background: #fde3e0; color: #e74c3c; }
.version { margin-top: 12px; font-size: 12px; color: #7fb8a8; text-align: center; }

/* ---------- 右侧 ---------- */
.right { flex: 1; background: #fff; border-radius: 16px; border: 1px solid #e3eeeb; display: flex; flex-direction: column; overflow: hidden; }
.chat { background: #fff; display: flex; flex-direction: column; overflow-y: auto; padding: 24px 28px; }
.msg { display: flex; margin-bottom: 18px; }
.msg.user { justify-content: flex-end; }
.bubble { background-image: linear-gradient(135deg, #3bb6a5, #26847a); color: #fff; padding: 11px 16px; border-radius: 12px; max-width: 70%; }

.msg.assistant { align-items: flex-start; gap: 12px; }
.avatar { width: 34px; height: 34px; border-radius: 8px; background-image: linear-gradient(135deg, #3bb6a5, #26847a); flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
.ai-body { flex: 1; display: flex; flex-direction: column; }
.card { width: 100%; background: #fff; border: 1px solid #ebeef5; border-left: 4px solid #1fc0a5; border-radius: 12px; padding: 16px 18px; box-sizing: border-box; }
.card-title { font-size: 12px; color: #155e52; letter-spacing: .5px; margin-bottom: 10px; }
.advice-title { font-weight: 600; color: #1f2d3d; margin-bottom: 6px; }
.advice { margin: 0 0 12px; padding-left: 18px; font-size: 14px; color: #303133; line-height: 1.7; }
.advice li::marker { color: #1fc0a5; }
.row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.row .label { font-size: 12px; color: #155e52; }
.row .dept { background: #eef7f5; border-color: #2f9e8f; color: #2f9e8f; }
.disclaimer { background: #fff3e0; color: #e0813d; border-radius: 8px; padding: 8px 12px; font-size: 13px; margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }
.disclaimer .info-ico { width: 15px; height: 15px; border: 2px solid #e0813d; color: #e0813d; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; font-style: italic; flex-shrink: 0; }
.disclaimer .red-dot { width: 13px; height: 13px; border-radius: 50%; background: #e54d42; flex-shrink: 0; }
.disclaimer .el-icon { flex-shrink: 0; }
.card-footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; font-size: 12px; color: #909399; margin-top: 8px; }
.card-footer .footer-left { display: flex; align-items: center; gap: 16px; }
.card-footer .ms { display: flex; align-items: center; gap: 4px; }
.card-footer .el-icon { flex-shrink: 0; }
.card-footer .link { color: #2f9e8f; cursor: pointer; display: flex; align-items: center; gap: 4px; }
.card-footer .link.pill { background: #e4f4ec; color: #155e52; border-radius: 999px; padding: 3px 12px; font-weight: 600; }

.input-bar { background: #fff; border-top: 1px solid #ebeef5; display: flex; align-items: center; gap: 12px; padding: 14px 20px; box-sizing: border-box; --el-component-size: 40px; }
.input-bar .el-input { flex: 1; --el-input-height: 40px; --el-input-border-radius: 10px; }
.input-bar .el-input .el-input__wrapper { height: 40px; min-height: 40px; border-radius: 10px !important; box-sizing: border-box; }
.input-bar .el-button { margin: 0; }
.send { height: 40px; border-radius: 10px; box-sizing: border-box; }
.send .el-icon { margin-right: 4px; }
</style>
