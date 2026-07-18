# 益志领导师匹配系统 · Zeabur 部署指南

本项目是 **Flask 全栈应用**(后端有匹配算法 / 飞书集成 / 审核 / 证书 / 数据持久化),
部署到 [Zeabur](https://zeabur.com) 可完整运行(不像静态托管只能放前端)。

---

## 一、你需要准备的(3 样)

| # | 项目 | 说明 |
|---|------|------|
| 1 | **Zeabur 账号** | https://zeabur.com 用 GitHub 或邮箱免费注册 |
| 2 | **GitHub 仓库** | 把本项目代码推到一个 GitHub 仓库(Zeabur 靠 Git 自动部署) |
| 3 | **环境变量值** | 已生成 `.env`(本地,含飞书/密码),复制到 Zeabur |

> 不需要你提供新的密钥 —— 飞书凭证、密码都已在本项目 `config/` 里,我整理进了 `.env`。

---

## 二、部署步骤

### 1. 推代码到 GitHub
1. 在 GitHub 新建一个仓库(建议 **Private**,避免泄露代码)
2. 把 `AI_CAMP/` 目录下的所有文件推上去:
   ```bash
   cd AI_CAMP
   git init && git add . && git commit -m "益志领导师匹配系统"
   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```
   > `.gitignore` 已排除 `config/feishu.json`、`config/admin.json`、`.env`(密钥不进仓库,用环境变量注入)。

### 2. Zeabur 创建项目
1. 登录 https://zeabur.com → **New Project**
2. **Add Service** → **Git Repository** → 选刚才的 GitHub 仓库
3. Zeabur 检测到 `Dockerfile` 会自动用容器构建(无需改配置)

### 3. 配置环境变量(关键)
项目 → **Variables** → 把 `.env` 里每行 `KEY=VALUE` 逐条添加:
- `SECRET_KEY`、`ADMIN_PASSWORD`、`AUDIT_PASSWORD`
- `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_BASE_URL`
- `FEISHU_GROUP_WEBHOOK`、`FEISHU_TABLES_JSON`
> `FEISHU_TABLES_JSON` 的值是整段 JSON,作为**一个**变量的值整体粘贴。

### 4. 配置持久卷(让配对/课程/活动数据不丢)
项目 → 你的 Service → **Volumes** → 新增:
- 挂载路径:`/app/data`
> 这样容器重启后 `data/` 里的 `pairs.json`/`schedules.json`/`activities.json`/`applicants.json` 不会丢。

### 5. 绑定域名 + 访问
- **Networking** → Zeabur 会自动给一个 `*.zeabur.app` 免费域名
- 打开域名 → 看到益志领官网落地页 → 点「管理员入口」登录(密码 = `ADMIN_PASSWORD`)

---

## 三、环境变量清单(对照 `.env`)

| 变量 | 说明 | 来源 |
|------|------|------|
| `SECRET_KEY` | Flask session 密钥 | 随便一串(可改) |
| `ADMIN_PASSWORD` | 管理端登录密码 | `config/admin.json` → password |
| `AUDIT_PASSWORD` | 录用/证书审核二级密码 | `config/admin.json` → audit_password |
| `FEISHU_APP_ID` | 飞书应用 App ID | `config/feishu.json` → app_id |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret | `config/feishu.json` → app_secret |
| `FEISHU_BASE_URL` | 飞书多维表格地址 | `config/feishu.json` → base_url |
| `FEISHU_GROUP_WEBHOOK` | 大群机器人 webhook | `config/feishu.json` → group_webhook |
| `FEISHU_TABLES_JSON` | 三张表 token(导师/学生/匹配) | `config/feishu.json` → tables 整段 |

---

## 四、部署后检查清单

- [ ] 落地页能打开
- [ ] 管理端能登录(`ADMIN_PASSWORD`)
- [ ] 选学生 → 匹配导师 能出结果(匹配算法在跑)
- [ ] 切数据源到「飞书实时」→ 能读飞书导师表(`FEISHU_*` 生效)
- [ ] 发布活动 → 大群收到消息(需飞书后台已开**机器人能力**,否则报 230006)
- [ ] L2/L3 导师证书审核 → 二级密码(`AUDIT_PASSWORD`)

---

## 五、注意事项

> **🔒 密钥安全(重要)**:生产用平台环境变量注入(Zeabur Variables / systemd EnvironmentFile),**勿把含密钥的 .env 留在工作目录或提交 Git**。`.gitignore` 已排除 `.env`;新部署照 `.env.example` 模板填值。代码已强制:未配 `ADMIN_PASSWORD` 会拒绝启动(不再静默用弱口令 `admin`)。

1. **飞书机器人能力**:飞书应用必须在开放平台启用「机器人」能力,否则发个人消息报 `230006 Bot ability is not activated`。这是飞书侧配置,与部署无关。
2. **免费层**:Zeabur 免费层有资源/休眠限制。长期高频使用建议升级付费(几美元/月)。公益小规模够用。
3. **数据持久化**:配对/课程/活动存持久卷 `/app/data`;飞书多维表格数据在飞书侧(不受部署影响)。
4. **本地开发不变**:代码仍优先读环境变量、其次读 `config/*.json`。本地不设环境变量就用 config 文件,行为不变。
