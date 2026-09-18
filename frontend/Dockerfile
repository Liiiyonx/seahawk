# 探海灵眸 SeaSight — 前端镜像（多阶段构建）
#
# 为什么用多阶段：node_modules 有 200MB+，但运行时只需要 dist/ 里的
# 几百 KB 静态文件。单阶段镜像会把整个工具链打进生产环境，既臃肿
# 又扩大攻击面。多阶段后运行镜像只有 nginx:alpine 的 ~10MB。
#
# 两种用法：
#   1. 生产/试点：构建静态产物，由 nginx 托管（本文件的最终阶段）
#   2. 开发：compose 里覆盖 command 为 `npm run dev`
#      —— 开发阶段挂了源码卷，需要完整 node 环境，
#         所以 compose 里显式指定了 --target 或直接跑 node 镜像。

# ======================================================================
# 阶段 1：构建
# ======================================================================
FROM node:22-alpine AS builder

WORKDIR /app

# 用国内镜像源加速（渔港/校园网环境下 npm 官方源常常超时）
RUN npm config set registry https://registry.npmmirror.com

# ★ 先 COPY 依赖清单再 install —— 利用 Docker 层缓存。
#   只要 package.json 没变，改源码时这层不会重跑，
#   构建时间从两分钟降到几秒。
COPY package.json package-lock.json* ./

# 有 lock 文件用 npm ci（可复现、更快）；没有则退回 npm install
RUN if [ -f package-lock.json ]; then \
        npm ci --no-audit --no-fund; \
    else \
        npm install --no-audit --no-fund; \
    fi

# 再 COPY 源码（.dockerignore 会挡掉 node_modules/dist）
COPY . .

RUN npm run build

# ======================================================================
# 阶段 2：开发环境（compose 开发模式用这个）
#   保留 node_modules 与源码，跑 vite dev server 做热更新
# ======================================================================
FROM node:22-alpine AS dev

WORKDIR /app

RUN npm config set registry https://registry.npmmirror.com

COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then \
        npm ci --no-audit --no-fund; \
    else \
        npm install --no-audit --no-fund; \
    fi

COPY . .

EXPOSE 5173

# --host 0.0.0.0 必须加：默认 vite 只监听 localhost，
# 容器外（宿主机浏览器）访问不到，表现为"端口映射了但连不上"。
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ======================================================================
# 阶段 3：生产运行（默认目标）
#   只搬 dist/ + nginx 配置，运行时不带 node
# ======================================================================
FROM nginx:1.27-alpine AS production

ENV TZ=Asia/Shanghai

RUN apk add --no-cache tzdata curl \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

# 静态产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 站点配置：SPA 回退 + API 代理 + WS 升级 + 视频流不缓冲
# ★ 生产环境请改用 deploy/nginx/seasight.conf（那份按真实拓扑写了
#   上游地址与安全头），这里的精简版只保证容器内能独立跑起来。
RUN printf '%s\n' \
    'server {' \
    '    listen 80;' \
    '    server_name _;' \
    '    root /usr/share/nginx/html;' \
    '    index index.html;' \
    '    charset utf-8;' \
    '' \
    '    gzip on;' \
    '    gzip_vary on;' \
    '    gzip_min_length 1024;' \
    '    gzip_types text/css text/javascript application/javascript application/json image/svg+xml;' \
    '' \
    '    # SPA 回退：不写则刷新子页面 404' \
    '    location / {' \
    '        try_files $uri $uri/ /index.html;' \
    '    }' \
    '' \
    '    # 带 hash 的产物可长期强缓存' \
    '    location /assets/ {' \
    '        expires 1y;' \
    '        add_header Cache-Control "public, immutable";' \
    '    }' \
    '' \
    '    location /api/ {' \
    '        proxy_pass http://backend:8000;' \
    '        proxy_set_header Host $host;' \
    '        proxy_set_header X-Real-IP $remote_addr;' \
    '        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;' \
    '    }' \
    '' \
    '    # WebSocket：三行升级头 + 长超时（默认 60s 会掐断空闲连接）' \
    '    location /ws/ {' \
    '        proxy_pass http://backend:8000;' \
    '        proxy_http_version 1.1;' \
    '        proxy_set_header Upgrade $http_upgrade;' \
    '        proxy_set_header Connection "upgrade";' \
    '        proxy_read_timeout 3600s;' \
    '        proxy_buffering off;' \
    '    }' \
    '}' \
    > /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
