<p align="center">
  <img src="./shareclaw.png" alt="ShareClaw Logo" width="160">
</p>

<h1 align="center">ShareClaw</h1>

<p align="center">
  <em>One Claw, Shared by Many. 🦞</em>
</p>

<p align="center">
  <strong>Shared WeChat seat management for cloud-hosted <a href="https://github.com/openclaw/openclaw">OpenClaw</a> AI assistants</strong>
</p>

<p align="center">
  <a href="./README.md">中文文档</a> · <a href="#quick-start">Quick Start</a> · <a href="#architecture">Architecture</a> · <a href="./docs/openclaw-isolation-guide.md">Isolation Guide</a> · <a href="./DEPLOYMENT.md">Production Deployment</a>
</p>

---

## What problem does this solve?

[OpenClaw](https://github.com/openclaw/openclaw) is the most popular open-source AI assistant framework. With the [openclaw-weixin](https://github.com/Tencent/openclaw-weixin) plugin, it can connect to WeChat. But each cloud server can only host a limited number of WeChat accounts at the same time.

When multiple people want to share the same OpenClaw service — **who gets in? who gets out? how do we manage the queue?**

**ShareClaw is the answer.**

It is a **WeChat seat rotation manager** for cloud-hosted OpenClaw: automatically evict the oldest WeChat account → show a QR code for the new user to scan → restart the Gateway. The entire process is done through a web interface with real-time SSE progress updates.

### Why ShareClaw?

| Pain Point | ShareClaw's Solution |
|---|---|
| Limited WeChat seats, multiple users competing | FIFO queue with automatic rotation |
| Manual operations (SSH → evict → scan → restart) | One-click web UI, fully automated |
| Hard to manage multiple servers | Remote mode + multi-instance scheduling |
| Opaque rotation process | Real-time SSE streaming of every step |

---

## Features

- 🔄 **Seat Rotation**: Evict oldest → Login new (QR code) → Restart Gateway
- 📡 **Real-time SSE**: Stream progress, QR codes, and results to the frontend
- 🖥️ **Web UI**: Built-in dark-theme management page, ready to use
- 📋 **FIFO Queue**: Only evicts accounts managed by ShareClaw, protects manually added ones
- 🌐 **Multi-instance Scheduling**: Automatically picks the least loaded server
- 🔧 **CLI**: `shareclaw serve` to start

---

## Core Idea: One Claw, Shared by Many

> **One high-spec cloud server running OpenClaw (🦞), serving multiple people's WeChat accounts simultaneously.**

Running OpenClaw requires a 24/7 cloud server. For individual users, dedicating an entire server is costly and underutilized. ShareClaw's core idea is **"One Claw, Shared by Many"** — let one lobster (one OpenClaw instance) work for many people:

```
                    ┌────────────────────────────────┐
  User A WeChat ──▶ │                                │
  User B WeChat ──▶ │   🦞 One high-spec cloud server │
  User C WeChat ──▶ │   OpenClaw + openclaw-weixin    │
  User D WeChat ──▶ │                                │
  ...              │   ShareClaw manages seat rotation│
                    └────────────────────────────────┘
```

Since multiple people share the server, it makes sense to **pick a high-spec machine** (more RAM, better CPU). The computing power that one person can't fully use is shared among many — **the per-person cost is actually lower**.

### Use Cases

| Scenario | Description |
|---|---|
| **Friends sharing** | A group of friends share a high-spec cloud server, each scanning their own WeChat to connect, splitting the server cost |
| **Family sharing** | A family shares one OpenClaw instance — parents and kids each use their own WeChat with AI assistance |
| **Team internal service** | A company deploys one OpenClaw, team members rotate in as needed, sharing AI tooling |
| **Community / Open source org** | An open-source community maintains a public OpenClaw instance, members self-serve via QR scan |
| **Teaching & demos** | An instructor deploys one OpenClaw, students take turns scanning to experience the AI assistant |
| **SaaS operation** | Offer AI WeChat assistant services based on OpenClaw, using ShareClaw to manage multi-tenant seat access |

---

## Design Philosophy

### Built around the OpenClaw ecosystem

ShareClaw is not a standalone WeChat management tool. It is tightly integrated with the **OpenClaw + openclaw-weixin** ecosystem:

- Operates on OpenClaw's `accounts.json` (WeChat account list)
- Calls `openclaw channels login` (WeChat login command)
- Manages `openclaw-gateway` (OpenClaw gateway service)
- Maintains its own `accounts_queue.json` (FIFO rotation queue)

### Backend abstraction — local and remote unified

Through the `ClawBackend` abstract base class, ShareClaw unifies **local file operations** and **remote cloud API calls** under the same interface:

```
ClawBackend (abstract)
├── LocalBackend   → filesystem + subprocess (co-located deployment)
└── RemoteBackend  → Tencent Cloud TAT remote command execution (cross-machine)
```

The remote mode is currently built on Tencent Cloud (Lighthouse / CVM + TAT). The architecture is designed to support other cloud providers in the future.

### Security first

- Remote file writes use **base64-encoded transport** to prevent shell injection
- Only evicts accounts managed by ShareClaw — **never touches** manually added WeChat accounts

---

## Architecture

ShareClaw supports two deployment modes for different scales.

### Architecture 1: Local Mode (Single Server)

ShareClaw and OpenClaw on the **same server**. ShareClaw directly operates local files.

```
                    ┌─────────────────────────────────────┐
                    │        Cloud Server (CVM / LH)       │
                    │                                     │
  User Browser ────▶│  ShareClaw (Web + API)               │
                    │       │                             │
                    │       ├── read/write accounts.json   │
                    │       ├── read/write queue.json      │
                    │       ├── openclaw channels login    │
                    │       └── systemctl restart gateway  │
                    │                                     │
                    │  OpenClaw + openclaw-weixin          │
                    │       └── openclaw-gateway           │
                    └─────────────────────────────────────┘
```

**Use case**: Personal use with a single server.

### Architecture 2: Remote Mode (Single OpenClaw Instance)

ShareClaw deployed separately, managing OpenClaw on another server via **Tencent Cloud TAT**.

```
  ┌──────────────────┐        Tencent Cloud TAT API       ┌──────────────────────┐
  │  Management Server│ ────────────────────────────────▶ │  OpenClaw Server      │
  │                  │                                    │                      │
  │  ShareClaw       │      Remote shell execution        │  OpenClaw             │
  │  (Web + API)     │      ◀────────────────────────── │  openclaw-weixin      │
  │                  │      Returns results               │  openclaw-gateway     │
  └──────────────────┘                                    └──────────────────────┘
```

**Use case**: ShareClaw on a public-facing server, OpenClaw on a separate machine.

### Architecture 3: Remote Mode (Multiple OpenClaw Instances)

ShareClaw manages multiple OpenClaw servers, automatically selecting the least loaded one.

```
  ┌──────────────────┐
  │                  │          ┌──────────────────────┐
  │  ShareClaw       │ ───────▶│  OpenClaw Instance A   │ queue: 3/6
  │  (Web + API)     │ │       │  openclaw-weixin      │
  │                  │ │       └──────────────────────┘
  │  ┌────────────┐  │ │
  │  │ Scheduler   │  │ │       ┌──────────────────────┐
  │  │ least loaded│──┘ ├─────▶│  OpenClaw Instance B   │ queue: 1/6 ← selected
  │  └────────────┘    │       │  openclaw-weixin      │
  │                    │       └──────────────────────┘
  │                    │
  │                    │       ┌──────────────────────┐
  │                    └─────▶│  OpenClaw Instance C   │ queue: 5/6
  └──────────────────┘         │  openclaw-weixin      │
                               └──────────────────────┘
```

**Scheduling strategy**: Query all instances' queue lengths → pick shortest → random tie-break → permanently blacklist unhealthy ones.

**Use case**: Team or community sharing across multiple OpenClaw servers.

---

## Quick Start

### Prerequisites

- A cloud server running [OpenClaw](https://github.com/openclaw/openclaw)
- [openclaw-weixin](https://github.com/Tencent/openclaw-weixin) plugin installed and previously logged in
- Python >= 3.9

### 1. Install

```bash
pip install shareclaw
```

### 2. Configure

Copy `.env.example` to `.env` and fill in your values.

#### Local Mode (ShareClaw on the same machine as OpenClaw)

```bash
SHARECLAW_MODE=local
OPENCLAW_HOME=~/.openclaw          # optional, default ~/.openclaw
SHARECLAW_HOME=~/.shareclaw        # optional, default ~/.shareclaw
SHARECLAW_MAX_QUEUE_SIZE=6         # optional, default 6
```

#### Remote Mode (ShareClaw on a separate machine)

```bash
SHARECLAW_MODE=remote
TENCENT_SECRET_ID=your_secret_id
TENCENT_SECRET_KEY=your_secret_key
LIGHTHOUSE_INSTANCE_IDS=lhins-xxx1,lhins-xxx2   # comma-separated
LIGHTHOUSE_REGION=ap-guangzhou                    # optional, default ap-guangzhou
SHARECLAW_MAX_QUEUE_SIZE=6                        # optional
```

### 3. Run

```bash
shareclaw serve
```

Listens on `0.0.0.0:9000` by default. Customize with:

```bash
shareclaw serve --port 8080 --host 127.0.0.1
```

### 4. Use

Open `http://<your-server>:9000` in your browser and click "Start Sync".

---

## API

| Endpoint | Method | Description |
|---|---|---|
| `/rotate` | GET / POST | Seat rotation (SSE stream) |
| `/health` | GET | Health check, returns `{"status": "ok"}` |
| `/` | GET | Web management page |
| `/logo.png` | GET | Logo static asset |

### SSE Event Types

| Event | Description |
|---|---|
| `progress` | Step-by-step progress updates (with stage and message) |
| `qrcode` | QR code data (display for user to scan) |
| `done` | Rotation completed |
| `error` | Error message |

---

## Rotation Flow

```
1. Load config → determine local/remote mode
2. Create backend (remote: scheduler picks optimal instance)
3. Query current OpenClaw status and queue info
4. Snapshot current accounts
5. Queue full? → Evict the oldest account
6. Run openclaw channels login → push QR code
7. User scans → detect new account → enqueue
8. Restart openclaw-gateway
9. Check gateway status → return result
```

---

## Multi-Account Isolation

When multiple WeChat accounts are mounted on the same OpenClaw instance, session and memory isolation depends on OpenClaw's `session.dmScope` configuration.

See the **[OpenClaw Multi-Account Isolation Guide](./docs/openclaw-isolation-guide.md)** for a detailed analysis.

---

## Roadmap

ShareClaw is in its early stages. Planned directions include:

- [ ] **Multi-cloud support**: Alibaba Cloud, Volcengine, AWS remote backends
- [ ] **Scheduled rotation**: Cron-based auto-eviction with user notifications
- [ ] **User queue system**: Full queue → notify → scan workflow
- [ ] **Dashboard**: Multi-instance overview and queue visualization
- [ ] **Webhook notifications**: Push to WeCom, Feishu, DingTalk, etc.
- [ ] **Persistent queue**: Redis/SQLite backends to replace JSON files
- [ ] **OpenClaw Skill integration**: Trigger rotation directly from chat
- [ ] **Auth & permissions**: API authentication and access control

---

## Development

```bash
git clone https://github.com/gardennchen/ShareClaw.git
cd ShareClaw
pip install -e ".[dev]"
python -m pytest tests/ -v
```

---

## Contributing

ShareClaw is open source and welcomes contributions of all kinds:

- 🐛 **Bug reports**: Open an [Issue](https://github.com/gardennchen/ShareClaw/issues)
- 💡 **Feature ideas**: Describe your idea in an Issue
- 🔧 **Code contributions**: Fork → Branch → PR
- 📖 **Documentation**: Fix typos, add explanations
- ☁️ **Cloud platform adapters**: Help adapt to Alibaba Cloud, AWS, Volcengine, etc.

We especially welcome:

- Developers familiar with **Alibaba Cloud / Volcengine / AWS** remote execution APIs
- Developers with **OpenClaw plugin** experience
- Designers with ideas for **frontend UI/UX** improvements

---

## License

[MIT](./LICENSE)
