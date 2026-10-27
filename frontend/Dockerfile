# 前端镜像：Vite 构建 + Nginx 托管静态资源，并反代 /api 到后端
# 前端代码里所有接口都是相对路径（/api/...），因此不需要注入后端地址。

# ---- 构建阶段 ----
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- 运行阶段 ----
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD wget -q --spider http://localhost/healthz || exit 1
CMD ["nginx", "-g", "daemon off;"]
