import request from '@/utils/request'

// 对话接口（POST /api/chat）
export function sendChatMessage(params) {
  return request({
    url: '/chat',
    method: 'POST',
    data: params,       // axios 自动 JSON 序列化，无需 stringify
  })
}

// 发送对话（SSE 流式 POST /api/chat/stream）
// 注意：流式用 fetch 才能读流（EventSource 只支持 GET，axios 读流不便）
export function sendChatMessageStream(params) {
  return fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

// 会话列表（GET /api/sessions）
export function getSessions(params) {
  return request({ url: '/sessions', method: 'GET', params })
}

// 会话消息（GET /api/chat/messages）
export function getMessages(sessionId) {
  return request({ url: '/chat/messages', method: 'GET', params: { sessionId } })
}