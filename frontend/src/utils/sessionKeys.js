// 会话能力令牌的本地存储
//
// 背景：会话接口现在要求「谁持有令牌谁才能读」。令牌由后端在首次对话时签发
// （响应里的 sessionKey），前端必须把它按 sessionId 存下来，后续读消息、
// 删会话、刷新列表时带上，否则拿不到自己的历史。
//
// 为什么放 localStorage 而不是内存：刷新页面后仍要能恢复自己的会话列表。

const STORAGE_KEY = 'smc.sessionKeys'

function readAll() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const obj = raw ? JSON.parse(raw) : {}
    return obj && typeof obj === 'object' ? obj : {}
  } catch {
    return {}
  }
}

function writeAll(map) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
  } catch {
    // 隐私模式/配额满时静默降级：会话仍可用，只是刷新后列表可能不全
  }
}

/** 保存某会话的令牌 */
export function saveSessionKey(sessionId, sessionKey) {
  if (!sessionId || !sessionKey) return
  const all = readAll()
  if (all[sessionId] === sessionKey) return
  all[sessionId] = sessionKey
  writeAll(all)
}

/** 取某会话的令牌（没有则空串） */
export function getSessionKey(sessionId) {
  if (!sessionId) return ''
  return readAll()[sessionId] || ''
}

/** 删除某会话的令牌 */
export function removeSessionKey(sessionId) {
  if (!sessionId) return
  const all = readAll()
  if (sessionId in all) {
    delete all[sessionId]
    writeAll(all)
  }
}

/** 所有已持有令牌的会话（用于向服务端声明"我有哪些会话"） */
export function allSessionKeys() {
  return Object.values(readAll()).filter(Boolean)
}
