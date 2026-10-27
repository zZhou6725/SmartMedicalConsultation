import request from '@/utils/request'
import { allSessionKeys, getSessionKey } from '@/utils/sessionKeys'

// 会话令牌请求头：只有持有令牌才能读写对应会话（服务端强制）。
function keyHeader(sessionId) {
  const key = getSessionKey(sessionId)
  return key ? { 'X-Session-Key': key } : {}
}

// 对话接口（POST /api/chat）
export function sendChatMessage(params) {
  return request({
    url: '/chat',
    method: 'POST',
    data: params,       // axios 自动 JSON 序列化，无需 stringify
    headers: keyHeader(params && params.sessionId),
  })
}

// 发送对话（SSE 流式 POST /api/chat/stream）
// 注意：流式用 fetch 才能读流（EventSource 只支持 GET，axios 读流不便）
export function sendChatMessageStream(params) {
  return fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...keyHeader(params && params.sessionId) },
    body: JSON.stringify(params),
  })
}

// 会话列表（GET /api/sessions）
// 非管理员只能看到自己持有令牌的会话，所以要主动声明"我有哪些令牌"。
export function getSessions(params) {
  const keys = allSessionKeys()
  return request({
    url: '/sessions',
    method: 'GET',
    params,
    headers: keys.length ? { 'X-Session-Keys': keys.join(',') } : {},
  })
}

// 会话消息（GET /api/chat/messages）
export function getMessages(sessionId) {
  return request({
    url: '/chat/messages',
    method: 'GET',
    params: { sessionId },
    headers: keyHeader(sessionId),
  })
}

// 删除会话（DELETE /api/sessions/{sessionId}）
export function deleteSession(sessionId) {
  return request({
    url: `/sessions/${sessionId}`,
    method: 'DELETE',
    headers: keyHeader(sessionId),
  })
}

// 系统状态（GET /api/system/status）：真实探活各组件 + 业务运行指标
export function getSystemStatus() {
  return request({ url: '/system/status', method: 'GET' })
}
