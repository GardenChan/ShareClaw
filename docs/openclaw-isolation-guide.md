# OpenClaw 多微信号隔离性指南

> 当多个微信号同时挂载在一个 OpenClaw 实例上时，它们之间的会话、记忆和数据是如何隔离的？  
> 本文档从 OpenClaw 架构出发，结合 openclaw-weixin 插件的实现，系统梳理隔离机制和配置建议。

---

## 目录

- [1. 为什么需要关注隔离性](#1-为什么需要关注隔离性)
- [2. 核心概念](#2-核心概念)
- [3. 隔离级别详解](#3-隔离级别详解)
- [4. 总结对比表](#4-总结对比表)
- [5. ShareClaw 场景下的建议](#5-shareclaw-场景下的建议)
- [6. Bindings 路由优先级](#6-bindings-路由优先级)
- [7. 参考链接](#7-参考链接)

---

## 1. 为什么需要关注隔离性

ShareClaw 的核心场景是在一个 OpenClaw 实例上管理多个微信号的轮转。这意味着同一时刻可能有多个微信号同时在线。需要回答的关键问题是：

- 微信号 A 的用户和微信号 B 的用户聊天时，AI 会不会串上下文？
- 微信号 A 的记忆，微信号 B 能不能看到？
- 如果同一个人同时加了微信号 A 和微信号 B，会怎样？

答案取决于 OpenClaw 的会话隔离配置。

---

## 2. 核心概念

### 2.1 Peer —— 对话的对方

`Peer` 是 OpenClaw 中"跟 AI 聊天的那个人"的抽象。

在微信渠道中，Peer ID 来自 openclaw-weixin 插件的 ilink 协议，对应消息结构中的 `from_user_id` 字段：

```
格式：xxx@im.wechat
示例：wxid_abc123def456@im.wechat
```

这是微信内部用户 ID，每个微信用户唯一且不变。**它不是微信号、昵称或手机号。**

> 信息来源：[openclaw-weixin ilink 协议分析](https://segmentfault.com/a/1190000047673612)

### 2.2 AccountId —— 你的微信号

`AccountId` 是同一渠道下不同登录实例的标识。每次扫码登录一个微信号，就会生成一个 accountId：

```bash
cat ~/.openclaw/openclaw-weixin/accounts.json
# ["6782910569e-im-bot", "134567e95d3e0-im-bot"]
```

每个 accountId 对应一个已登录的微信号。在 `openclaw.json` 中的 `channels.openclaw-weixin.accounts` 下管理。

### 2.3 Agent —— 独立的 AI "大脑"

`Agent` 是 OpenClaw 中一个完全隔离的 AI 运行单元：

| 资源 | 存储路径 |
|---|---|
| 工作区 | `~/.openclaw/workspace-<agentId>/` |
| 会话存储 | `~/.openclaw/agents/<agentId>/sessions/` |
| 认证配置 | `~/.openclaw/agents/<agentId>/agent/auth-profiles.json` |
| 人格文件 | agentDir 内的 `AGENTS.md`、`SOUL.md` |
| 记忆 (QMD) | workspace 内 |

默认只有一个 `main` Agent。可以创建多个 Agent 实现物理级隔离。

### 2.4 Session Key —— 对话的唯一标识

Session Key 决定了"这条消息属于哪个对话"。其结构取决于 `session.dmScope` 配置：

| dmScope | Session Key 结构 | 示例 |
|---|---|---|
| 默认 | `agent:<agentId>:<mainKey>` | `agent:main:default` |
| `per-peer` | `agent:<agentId>:dm:<peerId>` | `agent:main:dm:wxid_abc@im.wechat` |
| `per-channel-peer` | `agent:<agentId>:<channel>:dm:<peerId>` | `agent:main:openclaw-weixin:dm:wxid_abc@im.wechat` |
| `per-account-channel-peer` | `agent:<agentId>:<channel>:<accountId>:dm:<peerId>` | `agent:main:openclaw-weixin:678291-im-bot:dm:wxid_abc@im.wechat` |

群组消息始终隔离，key 为 `agent:<agentId>:<channel>:group:<groupId>`。

> 信息来源：[OpenClaw 会话管理文档](https://docs.openclaw.ai/zh-CN/concepts/session)

---

## 3. 隔离级别详解

从弱到强，共四个级别。

### Level 0：无隔离（默认）

**配置**：不设置 `session.dmScope`

所有渠道、所有微信号、所有用户共享同一个会话。AI 的回忆里，所有人的对话混在一起。

**几乎不会有人这样用，仅作为基线理解。**

### Level 1a：`per-channel-peer`

**配置**：

```json
{ "session": { "dmScope": "per-channel-peer" } }
```

按「渠道 + 对方」隔离。不同人跟 AI 聊天有各自独立的 session。

**关键行为**：

```
微信号 A 收到 张三 的消息 → session: openclaw-weixin:dm:张三@im.wechat
微信号 B 收到 李四 的消息 → session: openclaw-weixin:dm:李四@im.wechat  ✅ 隔离
微信号 B 收到 张三 的消息 → session: openclaw-weixin:dm:张三@im.wechat  ⚠️ 和微信号A的张三共享！
```

**优点**：配置简单（一行），绝大多数场景够用。  
**风险点**：如果同一个人加了你的多个微信号，会共享 session。  
**适用场景**：多个微信号面对的是不同的好友群体（ShareClaw 轮转的典型场景）。

### Level 1b：`per-account-channel-peer`

**配置**：

```json
{ "session": { "dmScope": "per-account-channel-peer" } }
```

或命令行：

```bash
openclaw config set session.dmScope per-account-channel-peer
```

比 Level 1a 多了 **accountId 维度**，即使同一个人在不同微信号上发消息，也是不同 session。

**关键行为**：

```
微信号 A 收到 张三 的消息 → session: openclaw-weixin:678291-im-bot:dm:张三@im.wechat
微信号 B 收到 张三 的消息 → session: openclaw-weixin:134567-im-bot:dm:张三@im.wechat  ✅ 隔离
```

**优点**：多微信号之间 session 完全隔离。  
**局限**：所有微信号仍然共享同一个 Agent 的记忆、工作区和人格。  
**适用场景**：多微信号且好友可能重叠（如客服分流场景）。

### Level 2：Agent 级隔离（最强）

为每个微信号创建独立的 Agent，通过 `bindings` 路由。

**配置步骤**：

```bash
# 1. 创建独立 Agent
openclaw agents add agent-weixin-a \
  --workspace ~/.openclaw/workspace-agent-weixin-a \
  --agent-dir ~/.openclaw/agents/agent-weixin-a/agent \
  --non-interactive

openclaw agents add agent-weixin-b \
  --workspace ~/.openclaw/workspace-agent-weixin-b \
  --agent-dir ~/.openclaw/agents/agent-weixin-b/agent \
  --non-interactive
```

```json
// 2. 在 openclaw.json 中配置 bindings
{
  "bindings": [
    {
      "agentId": "agent-weixin-a",
      "match": { "channel": "openclaw-weixin", "accountId": "6782910569e-im-bot" }
    },
    {
      "agentId": "agent-weixin-b",
      "match": { "channel": "openclaw-weixin", "accountId": "134567e95d3e0-im-bot" }
    }
  ]
}
```

**隔离效果**：每个微信号拥有完全独立的一切——会话、记忆、工作区、人格、模型配置。

**跨 Agent 记忆搜索（可选）**：默认完全隔离，如需共享可配置 `memorySearch.qmd.extraCollections`。

**适用场景**：需要每个微信号有独立 AI 人格或完全的数据隔离。

---

## 4. 总结对比表

| 维度 | Level 0 (默认) | Level 1a (`per-channel-peer`) | Level 1b (`per-account-channel-peer`) | Level 2 (Agent 隔离) |
|---|---|---|---|---|
| **会话上下文** | ❌ 全局共享 | ✅ 按渠道+对方 | ✅ 按账号+渠道+对方 | ✅ 物理隔离 |
| **同人跨号** | 串 | ⚠️ 串 | ✅ 不串 | ✅ 不串 |
| **记忆 (QMD)** | ❌ 共享 | ❌ 共享 | ❌ 共享 | ✅ 隔离 |
| **工作区/文件** | ❌ 共享 | ❌ 共享 | ❌ 共享 | ✅ 隔离 |
| **人格/Prompt** | ❌ 共享 | ❌ 共享 | ❌ 共享 | ✅ 可独立 |
| **模型/认证** | ❌ 共享 | ❌ 共享 | ❌ 共享 | ✅ 可独立 |
| **配置复杂度** | 零 | 一行 | 一行 | 需创建 Agent + bindings |

---

## 5. ShareClaw 场景下的建议

ShareClaw 的核心场景是**多人共享微信坐席轮转**：每位用户扫码登录自己的微信号，各自面对各自的好友。

| 你的情况 | 推荐级别 | 原因 |
|---|---|---|
| 多微信号，好友完全不重叠 | **Level 1a** (`per-channel-peer`) | peer 天然不同，不会串 session |
| 多微信号，可能有共同好友 | **Level 1b** (`per-account-channel-peer`) | accountId 维度额外隔离 |
| 需要每个微信号独立 AI 人格/记忆 | **Level 2** (Agent 隔离) | 物理级完全隔离 |

**对于大多数 ShareClaw 用户，`per-channel-peer` 已经足够。** 因为不同人的微信好友天然不同，peer（`xxx@im.wechat`）不会重叠。

---

## 6. Bindings 路由优先级

当使用 Level 2 多 Agent 模式时，入站消息按以下优先级匹配（由高到低）：

1. `peer` 匹配（精确的私信/群组/频道 ID）
2. `parentPeer` 匹配（线程继承）
3. `guildId + roles`（Discord 角色路由）
4. `guildId`（Discord）
5. `teamId`（Slack）
6. **`accountId` 匹配**（← 微信多账号路由在此层）
7. 渠道级匹配（`accountId: "*"`）
8. 回退到默认 Agent

同层级多条匹配时，配置文件中靠前的优先。

> 信息来源：[OpenClaw 多智能体路由文档](https://docs.openclaw.ai/zh-CN/concepts/multi-agent)

---

## 7. 参考链接

| 资源 | 链接 |
|---|---|
| OpenClaw GitHub | https://github.com/openclaw/openclaw |
| openclaw-weixin GitHub | https://github.com/Tencent/openclaw-weixin |
| OpenClaw 多智能体路由文档 | https://docs.openclaw.ai/zh-CN/concepts/multi-agent |
| OpenClaw 会话管理文档 | https://docs.openclaw.ai/zh-CN/concepts/session |
| openclaw-weixin ilink 协议分析 | https://segmentfault.com/a/1190000047673612 |
| 多微信账号配置教程 | https://www.intoep.com/ai/73132.html |
| ShareClaw GitHub | https://github.com/GardenChan/ShareClaw |
