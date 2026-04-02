<p align="center">
  <img src="https://raw.githubusercontent.com/GardenChan/ShareClaw/main/shareclaw.png" alt="ShareClaw Logo" width="160">
</p>

<h1 align="center">ShareClaw（拼虾虾）</h1>

<p align="center">
  <em>拼虾虾，拼着养更划算 🦞</em>
</p>

<p align="center">
  <strong>让多人共养一只云端虾</strong>
</p>

<p align="center">
  <a href="./README.en.md">English</a> · <a href="#快速开始">快速开始</a> · <a href="#部署架构">部署架构</a> · <a href="./docs/openclaw-isolation-guide.md">隔离性指南</a> · <a href="./DEPLOYMENT.md">正式部署</a>
</p>

---

## 这个项目解决什么问题？

[OpenClaw](https://github.com/openclaw/openclaw) 是当下最火的开源 AI 助手框架，通过 [openclaw-weixin](https://github.com/Tencent/openclaw-weixin) 插件可以让 AI 接入微信。但问题来了——

> 🤔 想给自己微信加个 AI 助手，得先买台云服务器？配环境、装 OpenClaw、调插件、还得 7×24 运维？
>
> 🤔 好不容易搞定了，一台高配服务器就只跑一个微信号，算力闲置、钱包心疼？
>
> 🤔 朋友一看你的 AI 助手好酷，也想要一个，难道再买一台服务器？

**其实你不需要"买服务器"，你只需要"养一只虾"。** 🦞

ShareClaw（拼虾虾）要探索的，是一种全新的 AI 服务使用方式——**不卖服务器，卖 Agent**：

```
  ┌──────────────────────────────────────────────────────┐
  │                                                      │
  │   传统思路：1 人 = 1 台服务器 = ¥100+/月              │
  │   💸💸💸💸💸💸💸💸💸💸💸💸                         │
  │                                                      │
  │   拼虾虾：N 人共养 1 只虾 = 每人 ¥十几/月             │
  │   🦞 ← 一只虾，大家一起养，拼着养更划算！              │
  │                                                      │
  └──────────────────────────────────────────────────────┘
```

一台高配云服务器（一只虾 🦞）能同时挂载多个微信号，每个微信号对应一个**独立的 AI Agent**（独立人格、独立记忆、独立会话）。ShareClaw 就是这只虾的**管家**——管理谁来谁走、自动排队轮转、一键扫码接入，让多人轻松共享同一套 OpenClaw 服务。

### 这就像"拼多多"式的 AI 服务

| 你以为你需要的 | 你实际需要的 |
|---|---|
| 一台云服务器 | 一个能用的 AI 微信助手 |
| 懂 Linux、SSH、Docker | 扫个码就行 |
| 每月 ¥100+ 独占一台机器 | 每月 ¥十几，和朋友拼一只虾 |
| 自己运维、自己折腾 | 虾主帮你搞定一切 |

### 为什么好玩？

- 🦞 **养虾文化**：你不是在"租服务器"，你是在和朋友**一起养一只 AI 虾**。给它起名字，调教它的性格，看它在你的微信里活蹦乱跳
- 👥 **社交裂变**：朋友看到你微信里有个超酷的 AI 助手，一句"来拼虾啊"就能拉他入伙
- 💰 **虾主经济**：技术玩家部署一只虾，邀请身边的人来拼，大家分摊成本，虾主甚至能小赚一笔
- 🎮 **可玩性高**：通过 Dashboard 管理你的虾——看谁在用、还能容纳几人、费用自动分摊、一键踢人换人

### 更大的想象空间

ShareClaw 也在探索 **Agent 级别的云服务售卖模式**：

```
  传统云计算卖的是：        CPU / 内存 / 带宽
  ShareClaw 探索卖的是：    一个可用的 AI Agent 🤖
```

对终端用户来说，"我要一台 2C4G 的服务器"远不如"我要一个 AI 微信助手"来得直接。ShareClaw 把服务器、OpenClaw、插件、运维这些复杂度全部封装在"一只虾"的背后，**让 AI Agent 变成像水电一样开箱即用的服务**。

单台服务器是养虾，多台服务器集群就是**虾场**——ShareClaw 的多实例调度能力天然支持从"一只虾"扩展到"一个虾场"，自动把新用户分配到最空闲的那只虾上。

### 核心能力

| 能力 | 说明 |
|---|---|
| 🔄 **坐席自动轮转** | FIFO 队列管理，先到先用，满员自动踢出最早的用户 |
| 📱 **扫码即用** | Web 页面一键操作，展示二维码，扫码就能接入 AI 助手 |
| 🏗️ **多实例调度** | 多台服务器自动选择最空闲的，天然支持"虾场"扩容 |
| 🔒 **Agent 级隔离** | 每个微信号独立人格、记忆、会话，互不干扰 |
| 📡 **实时进度** | SSE 流式推送轮转每一步，全程透明 |
| 💰 **费用分摊** | Dashboard 内置成本分摊计算，拼虾账目一目了然 |

---

## 功能

- 🔄 **坐席轮转**：踢出最早的微信 → 登录新微信（二维码）→ 重启 Gateway
- 📡 **SSE 实时推送**：进度、二维码、结果全部流式推送到前端
- 🖥️ **Web 管理界面**：内置精美深色主题前端，开箱即用
- 📋 **FIFO 队列**：只踢出本项目管理的 account，保护手动添加的微信号
- 🌐 **多实例调度**：远程模式下自动选择队列最短的服务器
- 🔧 **CLI 工具**：`shareclaw serve` 一键启动

---

## 核心思想：一虾多人共用

> **拼虾虾，拼着养更划算。** 一台高规格云服务器上的 OpenClaw（🦞），同时服务多个人的微信。

OpenClaw 运行需要一台 24 小时在线的云服务器。对个人用户来说，独占一台服务器成本太高、利用率太低。ShareClaw（拼虾虾）的核心思想就是 **"一虾多人共用"**——让一只龙虾（一个 OpenClaw 实例）同时为多人工作：

```
                    ┌────────────────────────────────┐
  用户 A 的微信 ──▶ │                                │
  用户 B 的微信 ──▶ │   🦞 一台高规格云服务器          │
  用户 C 的微信 ──▶ │   OpenClaw + openclaw-weixin    │
  用户 D 的微信 ──▶ │                                │
  ...              │   ShareClaw 管理坐席轮转          │
                    └────────────────────────────────┘
```

既然多人共享，服务器就应该**选高规格**的（更多内存、更好的 CPU），一个人用不完的算力分摊给多人，**每人成本反而更低**。

### 应用场景

| 场景 | 说明 |
|---|---|
| **朋友合租** | 几个朋友合租一台高配云服务器，各自扫码接入自己的微信，共享 AI 助手能力，均摊服务器费用 |
| **家庭共享** | 一家人共用一个 OpenClaw 实例，爸妈、孩子各自用自己的微信号享受 AI 服务 |
| **团队内部服务** | 公司或工作室部署一套 OpenClaw，团队成员按需轮换接入，共享 AI 工具链 |
| **社区/开源组织** | 开源社区维护一个公共 OpenClaw 实例，成员自助扫码使用 |
| **教学演示** | 老师部署一套 OpenClaw，学生轮流扫码体验 AI 助手，无需每人配一台服务器 |
| **SaaS 化运营** | 以 OpenClaw 为基础提供 AI 微信助手服务，用 ShareClaw 管理多个客户的坐席接入 |

---

## 设计理念

### 围绕 OpenClaw 生态设计

ShareClaw 不是一个独立的微信管理工具。它紧密围绕 **OpenClaw + openclaw-weixin** 生态设计：

- 操作的是 OpenClaw 的 `accounts.json`（微信账号列表）
- 调用的是 `openclaw channels login`（微信登录命令）
- 管理的是 `openclaw-gateway`（OpenClaw 网关服务）
- 维护的是自己的 `accounts_queue.json`（FIFO 轮转队列）

### 后端抽象 —— 本地与远程统一

通过 `ClawBackend` 抽象基类，ShareClaw 将**本地文件操作**和**远程云 API 调用**统一为相同接口：

```
ClawBackend (抽象)
├── LocalBackend   → 文件系统 + subprocess（同机部署）
└── RemoteBackend  → 腾讯云 TAT 远程命令执行（跨机部署）
```

当前远程模式基于腾讯云（Lighthouse / CVM + TAT）实现，架构设计上预留了对其他云平台的扩展能力。

### 安全优先

- 远程写文件使用 **base64 编码传输**，避免 shell 注入
- 只踢出 ShareClaw 自己管理的 account，**不触碰**非本项目录入的微信号

---

## 部署架构

ShareClaw 支持两种部署模式，适应不同规模的使用场景。

### 架构一：本地模式（单服务器）

ShareClaw 与 OpenClaw 部署在**同一台云服务器**上，直接操作本地文件。

```
                    ┌─────────────────────────────────────┐
                    │          腾讯云 CVM / Lighthouse      │
                    │                                     │
  用户浏览器 ──────▶│  ShareClaw (Web + API)               │
                    │       │                             │
                    │       ├── 读写 accounts.json         │
                    │       ├── 读写 accounts_queue.json   │
                    │       ├── openclaw channels login    │
                    │       └── systemctl restart gateway  │
                    │                                     │
                    │  OpenClaw + openclaw-weixin          │
                    │       └── openclaw-gateway           │
                    └─────────────────────────────────────┘
```

**适用场景**：高规格云服务器的云端虾共养——共享极致体验，分摊资源成本，和朋友或家人共养共用一只虾！

### 架构二：远程模式（单 OpenClaw 实例）

ShareClaw 独立部署，通过**腾讯云 TAT** 远程管理另一台服务器上的 OpenClaw。

```
  ┌──────────────────┐          腾讯云 TAT API          ┌──────────────────────┐
  │  管理服务器        │ ─────────────────────────────▶ │  OpenClaw 服务器       │
  │                  │                                 │                      │
  │  ShareClaw       │    远程执行 Shell 命令            │  OpenClaw             │
  │  (Web + API)     │    ◀───────────────────────────  │  openclaw-weixin      │
  │                  │    返回执行结果                    │  openclaw-gateway     │
  └──────────────────┘                                 └──────────────────────┘
```

**适用场景**：ShareClaw 部署在公网可访问的服务器上，OpenClaw 运行在另一台机器。

### 架构三：远程模式（多 OpenClaw 实例）

ShareClaw 统一管理多台 OpenClaw 服务器，自动选择最空闲的实例。

```
  ┌──────────────────┐
  │                  │          ┌──────────────────────┐
  │  ShareClaw       │ ───────▶│  OpenClaw 实例 A       │ 队列: 3/6
  │  (Web + API)     │ │       │  openclaw-weixin      │
  │                  │ │       └──────────────────────┘
  │  ┌────────────┐  │ │
  │  │ 调度器      │  │ │       ┌──────────────────────┐
  │  │ 选最空闲    │──┘ ├─────▶│  OpenClaw 实例 B       │ 队列: 1/6 ← 选中
  │  └────────────┘    │       │  openclaw-weixin      │
  │                    │       └──────────────────────┘
  │                    │
  │                    │       ┌──────────────────────┐
  │                    └─────▶│  OpenClaw 实例 C       │ 队列: 5/6
  └──────────────────┘         │  openclaw-weixin      │
                               └──────────────────────┘
```

**调度策略**：查询所有实例的队列长度 → 选最短的 → 相同长度随机选 → 不健康的永久加入黑名单。

**适用场景**：团队或社区共享，需要管理多台 OpenClaw 服务器的微信坐席资源。

---

## 快速开始

### 前置条件

- 一台运行 [OpenClaw](https://github.com/openclaw/openclaw) 的云服务器
- 已安装 [openclaw-weixin](https://github.com/Tencent/openclaw-weixin) 插件并成功登录过微信
- Python >= 3.9

### 1. 安装

```bash
pip install shareclaw
```

### 2. 配置

复制 `.env.example` 为 `.env`，根据部署模式填入配置。

#### 本地模式（ShareClaw 与 OpenClaw 同机）

```bash
SHARECLAW_MODE=local
OPENCLAW_HOME=~/.openclaw          # 可选，默认 ~/.openclaw
SHARECLAW_HOME=~/.shareclaw        # 可选，默认 ~/.shareclaw
SHARECLAW_MAX_QUEUE_SIZE=6         # 可选，队列最大长度，默认 6
```

#### 远程模式（ShareClaw 独立部署）

```bash
SHARECLAW_MODE=remote
TENCENT_SECRET_ID=你的SecretId
TENCENT_SECRET_KEY=你的SecretKey
LIGHTHOUSE_INSTANCE_IDS=lhins-xxx1,lhins-xxx2   # 多个实例用逗号分隔
LIGHTHOUSE_REGION=ap-guangzhou                    # 可选，默认 ap-guangzhou
SHARECLAW_MAX_QUEUE_SIZE=6                        # 可选
```

### 3. 启动

```bash
shareclaw serve
```

默认监听 `0.0.0.0:9000`，可自定义：

```bash
shareclaw serve --port 8080 --host 127.0.0.1
```

### 4. 使用

打开浏览器访问 `http://<your-server>:9000`，点击「开始同步」即可。

---

## API

| 接口 | 方法 | 说明 |
|---|---|---|
| `/rotate` | GET / POST | 坐席轮转（SSE 流式返回） |
| `/health` | GET | 健康检查，返回 `{"status": "ok"}` |
| `/` | GET | Web 管理页面 |
| `/logo.png` | GET | Logo 静态资源 |

### SSE 事件类型

| 事件 | 说明 |
|---|---|
| `progress` | 进度更新（含 stage 和 message） |
| `qrcode` | 二维码数据（展示给用户扫码） |
| `done` | 轮转完成 |
| `error` | 错误信息 |

---

## 轮转流程

```
1. 加载配置 → 确定本地/远程模式
2. 创建后端（远程模式：调度器选择最优实例）
3. 查询当前 OpenClaw 状态和队列信息
4. 记录当前 accounts 快照
5. 队列已满？→ 踢出最早加入的 account
6. 执行 openclaw channels login → 推送二维码
7. 用户扫码 → 检测新增 account → 入队
8. 重启 openclaw-gateway
9. 检查 gateway 状态 → 返回结果
```

---

## 多微信号隔离性

多个微信号同时挂载在同一个 OpenClaw 实例上时，会话和记忆的隔离性取决于 OpenClaw 的 `session.dmScope` 配置。

详细分析请参阅 **[OpenClaw 多微信号隔离性指南](./docs/openclaw-isolation-guide.md)**。

---

## Roadmap

ShareClaw 正处于早期阶段，以下是计划中的方向：

- [ ] **多云平台支持**：扩展远程后端，支持阿里云、火山引擎等平台上的 OpenClaw 实例
- [ ] **定时自动轮转**：支持 Cron 定时任务，到期自动踢出并通知下一位用户
- [ ] **用户排队系统**：完整的排队 → 通知 → 扫码流程
- [ ] **Dashboard**：多实例状态总览、队列可视化
- [ ] **Webhook 通知**：轮转完成后推送通知（企业微信、飞书、钉钉等）
- [ ] **队列持久化增强**：支持 Redis/SQLite 后端，替代 JSON 文件
- [ ] **OpenClaw Skill 集成**：作为 OpenClaw 技能直接从聊天中触发轮转
- [ ] **权限控制**：API 鉴权，限制谁可以触发轮转

---

## 开发

```bash
git clone https://github.com/GardenChan/ShareClaw.git
cd ShareClaw
pip install -e ".[dev]"
python -m pytest tests/ -v
```

---

## 参与贡献

ShareClaw 是一个开源项目，欢迎任何形式的贡献：

- 🐛 **Bug 报告**：提交 [Issue](https://github.com/GardenChan/ShareClaw/issues)
- 💡 **功能建议**：在 Issue 中描述你的想法
- 🔧 **代码贡献**：Fork → Branch → PR
- 📖 **文档改进**：修正错别字、补充说明
- ☁️ **云平台适配**：帮助适配阿里云、AWS、火山引擎等云平台的远程后端

特别欢迎以下方向的贡献者：

- 熟悉**阿里云 / 火山引擎 / AWS** 远程命令执行 API 的开发者
- 有 **OpenClaw 插件开发**经验的开发者
- 对 **前端 UI/UX** 有想法的设计师

---

## License

[MIT](./LICENSE)
