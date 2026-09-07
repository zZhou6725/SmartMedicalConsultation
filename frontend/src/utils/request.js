import axios from 'axios'

// axios 实例：统一 baseURL、拦截器
const request = axios.create({
  baseURL: '/api',     // 所有请求走 /api（Vite 代理转发到后端 8000）
  timeout: 10000,
})

// 请求拦截器：以后加鉴权时从这里塞 token；现在留占位
request.interceptors.request.use(
  (config) => {
    // const token = localStorage.getItem('token')
    // if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  },
  (error) => Promise.reject(error),
)

// 响应拦截器：剥掉 axios 外壳，直接返回后端 {code,msg,data}
request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    // 401 等 HTTP 错误统一处理（以后接登录）
    console.error('http error:', error)
    return Promise.reject(error)
  },
)

export default request