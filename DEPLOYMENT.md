# ShareClaw 正式环境部署指南

## 1. 适用范围

本文适用于以下场景：

- ShareClaw 与 OpenClaw 部署在同一台 Linux 服务器
- 使用 `local` 本地模式
- ShareClaw 需要以后台常驻服务运行
- 正式环境通过 Nginx 对外提供访问入口

本文以当前项目的实际实现为准，推荐采用以下运行方式：

- **与 OpenClaw 使用同一个 Linux 用户运行**
- **使用 `systemd --user` 托管 `shareclaw serve`**
- **通过 Nginx 反向代理对外暴露服务**

> 说明：当前版本默认 Web 启动入口是 `shareclaw serve`。本文不额外引入未纳入项目默认依赖的 WSGI 服务端，以确保文档与当前代码行为一致。

---

## 2. 部署原理与关键约束

本地模式下，ShareClaw 会直接操作 OpenClaw 的本地文件，并通过用户级 systemd 管理 OpenClaw Gateway。因此必须满足以下约束：

- ShareClaw 与 OpenClaw **必须使用同一个 Linux 用户**运行
- `openclaw` 命令必须在该用户的 `PATH` 中可执行
- `openclaw-gateway` 必须是**用户级服务**，并且以下命令能正常执行：

```bash
systemctl --user restart openclaw-gateway
systemctl --user is-active openclaw-gateway
```

- ShareClaw 运行用户必须对以下路径具备读写权限：
  - `OPENCLAW_HOME/openclaw.json`
  - `OPENCLAW_HOME/openclaw-weixin/accounts.json`
  - `SHARECLAW_HOME/accounts_queue.json`

如果 `openclaw-gateway` 当前是系统级服务，而不是用户级服务，那么**当前版本的 ShareClaw 本地模式不建议直接上线**，因为代码内部调用的是 `systemctl --user`。

---

## 3. 推荐部署拓扑

```text
Browser
   |
   v
Nginx (80/443)
   |
   v
127.0.0.1:9000 -> ShareClaw (`shareclaw serve`)
                     |
                     +-> 读写 ~/.openclaw/openclaw.json
                     +-> 读写 ~/.openclaw/openclaw-weixin/accounts.json
                     +-> 读写 ~/.shareclaw/accounts_queue.json
                     +-> 调用 `openclaw channels login --channel openclaw-weixin`
                     +-> 调用 `systemctl --user restart openclaw-gateway`
```

---

## 4. 目录规划建议

以下示例以部署用户 `ubuntu` 为例，请按实际用户名和目录调整。

建议目录如下：

```text
/opt/shareclaw/ShareClaw                 # 项目源码目录
/opt/shareclaw/venv                      # Python 虚拟环境
/home/ubuntu/.config/shareclaw/          # 环境变量文件目录
/home/ubuntu/.config/systemd/user/       # 用户级 systemd service 目录
/home/ubuntu/.openclaw/                  # OpenClaw 主目录
/home/ubuntu/.shareclaw/                 # ShareClaw 数据目录
```

---

## 5. 前置条件检查

正式部署前，请先以 **OpenClaw 实际运行用户** 执行以下检查。

### 5.1 检查 OpenClaw 命令

```bash
which openclaw
openclaw --help
```

### 5.2 检查 OpenClaw 用户级服务

```bash
systemctl --user status openclaw-gateway
systemctl --user is-active openclaw-gateway
```

期望结果中，`is-active` 返回：

```text
active
```

### 5.3 检查 OpenClaw 配置目录

```bash
ls -lah /home/ubuntu/.openclaw
ls -lah /home/ubuntu/.openclaw/openclaw-weixin
```

至少应能看到：

- `/home/ubuntu/.openclaw/openclaw.json`
- `/home/ubuntu/.openclaw/openclaw-weixin/accounts.json`

### 5.4 启用用户级服务开机常驻

为了让 `systemd --user` 在服务器重启后依然自动拉起服务，建议执行：

```bash
sudo loginctl enable-linger ubuntu
```

---

## 6. 安装 ShareClaw

推荐使用**源码 + 虚拟环境**的方式部署，便于后续升级和回滚。

### 6.1 创建安装目录

```bash
sudo mkdir -p /opt/shareclaw
sudo chown -R ubuntu:ubuntu /opt/shareclaw
```

### 6.2 拉取代码

```bash
git clone https://github.com/gardennchen/ShareClaw.git /opt/shareclaw/ShareClaw
```

### 6.3 创建虚拟环境并安装

```bash
python3 -m venv /opt/shareclaw/venv
/opt/shareclaw/venv/bin/pip install -U pip
/opt/shareclaw/venv/bin/pip install -e /opt/shareclaw/ShareClaw
```

如果你的 `openclaw` 命令也安装在 Python 环境中，请确认它与 ShareClaw 使用的运行用户、运行环境一致。

---

## 7. 配置环境变量

### 7.1 创建环境文件目录

```bash
mkdir -p /home/ubuntu/.config/shareclaw
```

### 7.2 创建环境变量文件

创建文件：

```text
/home/ubuntu/.config/shareclaw/shareclaw.env
```

内容如下：

```bash
SHARECLAW_MODE=local
OPENCLAW_HOME=/home/ubuntu/.openclaw
SHARECLAW_HOME=/home/ubuntu/.shareclaw
SHARECLAW_MAX_QUEUE_SIZE=6
PORT=9000
```

### 7.3 重要说明

- 当前版本**不会自动加载项目目录下的 `.env` 文件**
- 正式环境请通过以下任一方式注入环境变量：
  - `systemd` 的 `EnvironmentFile=`
  - 手动 `export`
- 在 `systemd` 环境文件中，**不要使用 `~`**，必须写**绝对路径**

---

## 8. 先做一次前台启动验证

在配置后台服务前，建议先手工前台启动一次，确认环境正确。

```bash
export SHARECLAW_MODE=local
export OPENCLAW_HOME=/home/ubuntu/.openclaw
export SHARECLAW_HOME=/home/ubuntu/.shareclaw
export SHARECLAW_MAX_QUEUE_SIZE=6
export PATH=/home/ubuntu/.local/bin:/opt/shareclaw/venv/bin:/usr/local/bin:/usr/bin:/bin

/opt/shareclaw/venv/bin/shareclaw serve --host 127.0.0.1 --port 9000
```

另开一个终端验证健康检查：

```bash
curl http://127.0.0.1:9000/health
```

期望返回：

```json
{"status":"ok"}
```

如果这里不通，请先不要继续配置后台服务，优先排查环境变量、`PATH`、OpenClaw 权限和 `openclaw-gateway` 状态。

---

## 9. 配置 `systemd --user` 后台服务

### 9.1 创建用户级 service 目录

```bash
mkdir -p /home/ubuntu/.config/systemd/user
```

### 9.2 创建 service 文件

创建文件：

```text
/home/ubuntu/.config/systemd/user/shareclaw.service
```

内容如下：

```ini
[Unit]
Description=ShareClaw Web Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/home/ubuntu/.config/shareclaw/shareclaw.env
Environment=PATH=/home/ubuntu/.local/bin:/opt/shareclaw/venv/bin:/usr/local/bin:/usr/bin:/bin
WorkingDirectory=/opt/shareclaw/ShareClaw
ExecStart=/opt/shareclaw/venv/bin/shareclaw serve --host 127.0.0.1 --port 9000
Restart=always
RestartSec=3
TimeoutStopSec=20

[Install]
WantedBy=default.target
```

### 9.3 启动并设置开机自启

```bash
systemctl --user daemon-reload
systemctl --user enable --now shareclaw
systemctl --user status shareclaw
```

### 9.4 查看日志

```bash
journalctl --user -u shareclaw -f
```

---

## 10. 配置 Nginx 反向代理

正式环境建议仅让 ShareClaw 监听本机回环地址 `127.0.0.1:9000`，再由 Nginx 对外提供访问。

### 10.1 示例配置

以下以域名 `shareclaw.example.com` 为例：

```nginx
server {
    listen 80;
    server_name shareclaw.example.com;

    location /rotate {
        proxy_pass http://127.0.0.1:9000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        add_header X-Accel-Buffering no;
    }

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```

### 10.2 SSE 特别说明

`/rotate` 接口使用的是 **SSE 流式返回**，因此 Nginx 必须关闭缓冲，否则前端可能无法实时看到：

- 轮转进度
- 二维码输出
- 最终完成事件

也就是说，以下配置非常关键：

```nginx
proxy_buffering off;
add_header X-Accel-Buffering no;
proxy_read_timeout 3600s;
```

### 10.3 HTTPS 建议

正式环境建议为 Nginx 配置 HTTPS 证书，例如通过 Certbot 或现有网关统一接入 TLS。

---

## 11. 启动后验证

### 11.1 验证本地服务

```bash
curl http://127.0.0.1:9000/health
```

### 11.2 验证 Nginx 代理

```bash
curl http://shareclaw.example.com/health
```

### 11.3 浏览器验证

打开以下地址：

```text
http://shareclaw.example.com/
```

你应能访问到前端页面。

### 11.4 接口列表

当前版本主要接口如下：

- `GET /`：前端测试页面
- `GET /health`：健康检查
- `GET|POST /rotate`：坐席轮转 SSE 接口
- `GET /logo.png`：前端 Logo 资源

---

## 12. 日常运维命令

### 12.1 查看服务状态

```bash
systemctl --user status shareclaw
systemctl --user status openclaw-gateway
```

### 12.2 重启服务

```bash
systemctl --user restart shareclaw
systemctl --user restart openclaw-gateway
```

### 12.3 查看实时日志

```bash
journalctl --user -u shareclaw -f
journalctl --user -u openclaw-gateway -f
```

### 12.4 查看当前监听端口

```bash
ss -lntp | grep 9000
```

---

## 13. 数据文件位置说明

本地模式下，ShareClaw / OpenClaw 关键文件位置如下：

### 13.1 OpenClaw 配置文件

```text
OPENCLAW_HOME/openclaw.json
```

默认示例：

```text
/home/ubuntu/.openclaw/openclaw.json
```

### 13.2 OpenClaw 账号文件

```text
OPENCLAW_HOME/openclaw-weixin/accounts.json
```

默认示例：

```text
/home/ubuntu/.openclaw/openclaw-weixin/accounts.json
```

### 13.3 ShareClaw 队列文件

```text
SHARECLAW_HOME/accounts_queue.json
```

默认示例：

```text
/home/ubuntu/.shareclaw/accounts_queue.json
```

---

## 14. 常见问题排查

### 14.1 `systemctl --user restart openclaw-gateway` 失败

重点检查：

- ShareClaw 是否与 OpenClaw 使用同一用户运行
- `openclaw-gateway` 是否确实是用户级 service
- 是否已执行 `loginctl enable-linger <user>`
- 当前用户是否能直接执行：

```bash
systemctl --user restart openclaw-gateway
```

### 14.2 后台服务启动成功，但轮转时报找不到 `openclaw`

这是典型的 `PATH` 问题。请检查 `shareclaw.service` 中的：

```ini
Environment=PATH=...
```

确认其中包含 `openclaw` 所在目录。

### 14.3 `.env` 文件明明存在，但配置没有生效

当前版本不会自动读取项目目录中的 `.env`。正式环境必须通过以下方式注入：

- `EnvironmentFile=`
- 手动 `export`

### 14.4 `/rotate` 无法实时输出进度或二维码

通常是 Nginx 开启了缓冲。请检查 `/rotate` 的反向代理配置中是否包含：

```nginx
proxy_buffering off;
add_header X-Accel-Buffering no;
proxy_read_timeout 3600s;
```

### 14.5 访问首页正常，但轮转失败

优先检查以下项目：

- `/home/ubuntu/.openclaw/openclaw.json` 是否存在
- `/home/ubuntu/.openclaw/openclaw-weixin/accounts.json` 是否存在且格式正确
- `openclaw channels login --channel openclaw-weixin` 是否可手工执行
- `openclaw-gateway` 当前是否为 `active`

### 14.6 服务重启后没有自动拉起

请检查：

```bash
systemctl --user is-enabled shareclaw
sudo loginctl show-user ubuntu
```

确认：

- `shareclaw` 已 `enable`
- 已启用 `linger`

---

## 15. 不推荐的部署方式

基于当前实现，以下方式不建议直接用于正式环境：

- **直接用 root 运行 ShareClaw**
  - 原因：本地模式内部依赖 `systemctl --user`，root 的系统级服务上下文通常与 OpenClaw 用户上下文不一致

- **把 ShareClaw 做成系统级 service，但 OpenClaw 仍是用户级 service**
  - 原因：ShareClaw 无法稳定管理目标用户下的 `openclaw-gateway`

- **只把环境变量写进项目目录 `.env`，却没有显式加载**
  - 原因：当前版本不会自动读取 `.env`

---

## 16. 上线检查清单

上线前建议逐项确认：

- [ ] ShareClaw 与 OpenClaw 由同一个 Linux 用户运行
- [ ] `systemctl --user status openclaw-gateway` 正常
- [ ] `openclaw` 命令在服务 `PATH` 中可执行
- [ ] `OPENCLAW_HOME` 与 `SHARECLAW_HOME` 使用绝对路径
- [ ] `curl http://127.0.0.1:9000/health` 正常
- [ ] `systemctl --user status shareclaw` 正常
- [ ] Nginx 已配置 `/rotate` 的 SSE 无缓冲代理
- [ ] 已启用 `loginctl enable-linger <user>`
- [ ] 浏览器访问 `/`、`/health`、`/rotate` 均已验证

---

## 17. 附：最小可用部署步骤

如果你已经具备 OpenClaw 运行环境，只想快速落地正式环境，最小步骤如下：

1. 安装 ShareClaw 到虚拟环境
2. 创建 `/home/ubuntu/.config/shareclaw/shareclaw.env`
3. 创建 `/home/ubuntu/.config/systemd/user/shareclaw.service`
4. 执行：

```bash
systemctl --user daemon-reload
systemctl --user enable --now shareclaw
sudo loginctl enable-linger ubuntu
```

5. 配置 Nginx 代理到 `127.0.0.1:9000`
6. 验证：

```bash
curl http://127.0.0.1:9000/health
curl http://shareclaw.example.com/health
```

至此，即可完成本地模式下 ShareClaw 的正式环境部署。
