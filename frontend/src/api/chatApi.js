import request from '@/utils/request'

// 对话接口（POST /api/chat）
export function sendChatMessage(params) {
  return request({
    url: '/chat',
    method: 'POST',
    data: params,       // axios 自动 JSON 序列化，无需 stringify
  })
}