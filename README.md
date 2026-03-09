# Grok 批量注册工具

批量注册 Grok 账号并自动开启 NSFW/Unhinged 功能。**完整支持无图形界面的 Linux 服务器终端运行。**

## 功能

- 自动创建临时邮箱（基于 [moemail](https://github.com/beilunyang/moemail) 服务）
- 自动获取邮箱验证码
- 自动完成 Grok 注册流程
  - **HTTP 模式**：直接调用注册 API，速度快，需要 Turnstile 验证服务（YesCaptcha / 本地 Solver / FlareSolverr）
  - **浏览器模式**（自动回退）：当页面结构变化导致 HTTP 模式失效时，自动切换为 camoufox 无头浏览器注册，无需 Action ID
- 自动同意用户协议（TOS）
- 自动开启 NSFW/Unhinged 模式
- 注册完成后自动清理临时邮箱
- 支持多线程/多并发注册
- 支持 HTTP 代理
- **无需图形界面，全程可在服务器终端运行**

## 整体架构

```
┌─────────────────┐     ┌──────────────────────┐     ┌───────────────────┐
│  grok.py 主程序  │────▶│  moemail 临时邮箱服务  │────▶│  你的邮箱服务器    │
│  (批量注册入口)   │     │  (自行部署)            │     │                   │
└────────┬────────┘     └──────────────────────┘     └───────────────────┘
         │
         │  验证服务（三选一，推荐 YesCaptcha）
         ├──▶ YesCaptcha API（云端，服务器最友好，无需本地浏览器）★推荐
         ├──▶ 本地 Turnstile Solver（camoufox 无头浏览器，默认 headless）
         ├──▶ FlareSolverr（Docker，Cloudflare 绕过）
         │
         ├──▶ HTTP 注册模式 → accounts.x.ai（快速）
         │       ↓ 若页面结构变更自动回退
         └──▶ 浏览器注册模式 → camoufox 无头浏览器（兜底，无需验证服务）
                      ↓
              grok.com（NSFW/Unhinged 设置 API）
```

## 注册流程

```
启动 → 读取 .env 配置（或交互式输入）→ 扫描注册页参数
                                               │
                          ┌────────────────────┤
                          │                    │
                   找到 Action ID        未找到 Action ID
                          │                    │
               HTTP 注册模式（快）      浏览器模式（兜底）
               N 个并发线程             N 个并发 camoufox
                          │
       ┌──────────────────┼──────────────────┐
       ▼                  ▼                  ▼
 ┌────────────────────────────────────────────┐
 │  单次注册流程:                               │
 │  1. 创建临时邮箱 (moemail API)              │
 │  2. 发送验证码 (accounts.x.ai gRPC)         │
 │  3. 轮询获取验证码 (moemail API)             │
 │  4. 验证邮箱验证码 (accounts.x.ai gRPC)     │
 │  5. 获取 Turnstile Token（若可用）           │
 │  6. 获取 cf_clearance（若可用）              │
 │  7. 提交注册请求                             │
 │  8. 同意用户协议 (TOS)                      │
 │  9. 开启 NSFW 模式                          │
 │  10. 保存 SSO Token                        │
 │  11. 删除临时邮箱                            │
 └────────────────────────────────────────────┘
                          │
                          ▼
              二次验证 (enable_unhinged)
                          │
                          ▼
              输出结果至 keys/ 目录
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `grok.py` | 主程序，批量注册入口 |
| `TurnstileSolver.sh` | Turnstile Solver 启动脚本（**Linux / macOS 服务器**，无头模式） |
| `TurnstileSolver.bat` | Turnstile Solver 启动脚本（Windows 桌面） |
| `api_solver.py` | 本地 Turnstile 验证码解决器（默认 headless，服务器可用） |
| `browser_configs.py` | 浏览器指纹配置 |
| `db_results.py` | 验证结果存储（内存模式） |
| `g/email_service.py` | 临时邮箱服务（moemail API） |
| `g/turnstile_service.py` | Turnstile 验证服务（本地 Solver / YesCaptcha） |
| `g/browser_register.py` | 浏览器自动化注册（camoufox 无头，兜底模式） |
| `g/user_agreement_service.py` | 用户协议同意服务 |
| `g/nsfw_service.py` | NSFW/Unhinged 设置服务 |
| `g/flaresolverr_service.py` | FlareSolverr Cloudflare 绕过服务 |
| `.env.example` | 环境变量模板 |
| `requirements.txt` | Python 依赖列表 |

---

## 服务器部署指南（无图形界面）

### 前置条件

- Python 3.9+（推荐 3.11）
- Linux 服务器（Ubuntu 20.04+ / Debian 11+ / CentOS 8+）
- 已部署 [moemail](https://github.com/beilunyang/moemail) 临时邮箱服务

### 第一步：部署 moemail 临时邮箱服务

moemail 是本项目依赖的临时邮箱服务，需自行部署。请参考 [moemail 项目文档](https://github.com/beilunyang/moemail) 完成部署。

部署完成后，你应该拥有：
- **moemail 服务地址**：例如 `https://mail.example.com`
- **API Key**：moemail 后台生成的 API 密钥
- **邮箱域名**：配置在 moemail 中的收信域名，例如 `example.com`

验证 moemail 服务是否正常：

```bash
curl -X GET https://mail.example.com/api/config \
  -H "X-API-Key: YOUR_API_KEY"
```

### 第二步：安装项目

```bash
git clone https://github.com/Friendzhb/grokzhuce.git
cd grokzhuce
pip install -r requirements.txt
```

### 第三步：安装 camoufox 浏览器内核

camoufox 需要单独下载浏览器内核（仅需执行一次）：

```bash
python -m camoufox fetch
```

> 💡 这一步会下载约 100MB 的浏览器文件，请确保服务器有网络访问权限。
> 如使用代理，可先设置 `export https_proxy=http://...`

### 第四步：配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
nano .env   # 或使用 vim .env
```

编辑 `.env` 文件：

```ini
# moemail 邮箱服务配置（必填）
MOEMAIL_API_KEY=your-moemail-api-key
MOEMAIL_BASE_URL=https://mail.example.com
MOEMAIL_DOMAIN=example.com

# 验证码服务（三选一，推荐 YesCaptcha，服务器最省心）
# 方式一：YesCaptcha（云端 API，无需本地浏览器，服务器首选）★
YESCAPTCHA_KEY=your-yescaptcha-api-key

# 方式二：本地 Turnstile Solver（留空则尝试本地 Solver，需先启动 api_solver.py）
# YESCAPTCHA_KEY=

# 方式三：FlareSolverr（留空，单独配置下方 URL）
FLARESOLVERR_URL=http://localhost:8191
FLARESOLVERR_REFRESH_INTERVAL=600
FLARESOLVERR_TIMEOUT=60
```

配置项说明：

| 配置项 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `MOEMAIL_API_KEY` | ✅ | - | moemail API 密钥 |
| `MOEMAIL_BASE_URL` | ✅ | - | moemail 服务地址 |
| `MOEMAIL_DOMAIN` | ❌ | 从 API 自动获取 | 邮箱域名 |
| `YESCAPTCHA_KEY` | ❌ | 空（用本地 Solver）| YesCaptcha API Key，**服务器推荐** |
| `FLARESOLVERR_URL` | ❌ | `http://localhost:8191` | FlareSolverr 地址 |
| `FLARESOLVERR_REFRESH_INTERVAL` | ❌ | `600` | cf_clearance 刷新间隔（秒） |
| `FLARESOLVERR_TIMEOUT` | ❌ | `60` | FlareSolverr 超时（秒） |

### 第五步：选择并启动验证服务

> 三种方式选其一即可（也可组合使用）。**服务器上推荐方式一（YesCaptcha）**，无需额外进程。

---

**方式一：YesCaptcha（推荐，无需本地浏览器）**

在 `.env` 中填入 `YESCAPTCHA_KEY=your-key`，直接跳到第六步运行主程序。

无需启动任何额外服务。

---

**方式二：本地 Turnstile Solver（需要 camoufox，无头模式）**

在后台启动 Solver（默认已是无头模式，无需图形界面）：

```bash
# 前台运行（调试用）
bash TurnstileSolver.sh

# 后台运行（服务器常驻）
nohup bash TurnstileSolver.sh > turnstile.log 2>&1 &
echo "Turnstile Solver PID: $!"
```

等待看到类似 `Running on http://0.0.0.0:5072` 的日志后，Solver 已就绪。

验证是否正常：
```bash
curl http://127.0.0.1:5072/
```

---

**方式三：FlareSolverr（Docker，服务器可用）**

```bash
docker run -d \
  --name flaresolverr \
  -p 8191:8191 \
  ghcr.io/flaresolverr/flaresolverr:latest
```

验证：
```bash
curl http://localhost:8191/
```

### 第六步：运行注册程序

```bash
python grok.py
```

程序会读取 `.env` 中的配置，并提示输入（直接回车使用默认值/已配置值）：

```
============================================================
  Grok 注册机 - 启动配置
  直接回车使用括号中的默认值 / .env 配置
============================================================

[邮箱服务 moemail]
  moemail API Key [your-moemail-api-key]:
  moemail Base URL [https://mail.example.com]:
  邮箱域名 [example.com]:

[验证码服务（可选，和 FlareSolverr 二选一即可）]
  YesCaptcha Key (留空使用本地 Turnstile Solver) [已设置]:

[FlareSolverr Cloudflare 绕过（可选，和 Turnstile Solver 二选一即可）]
  FlareSolverr URL [http://localhost:8191]:
  cf_clearance 刷新间隔秒 [600]:
  FlareSolverr 超时秒 [60]:

[代理设置（留空不使用代理）]
  HTTP 代理地址 (例: http://127.0.0.1:10808):

[注册参数]
  并发线程数 [8]:
  注册账号数量 [100]: 10
```

### 第七步：等待注册完成

程序将自动执行注册流程，并实时输出进度：

```
============================================================
Grok 注册机
============================================================
[*] 正在初始化，扫描注册页面参数...
[+] Action ID: 7f67aa61adfb0655899002808e1d443935b057c25b
[*] 启动 8 个线程，目标 10 个账号
[*] 输出文件: keys/grok_20260309_120000_10.txt
============================================================
[*] 开始注册: abc123@example.com
[+] 1/10 abc123@example.com | 5.2s/个
[+] 2/10 def456@example.com | 4.8s/个
...
[*] 开始二次验证 NSFW...
[*] 二次验证完成: 10/10
[*] 完成！共注册 10 个账号，耗时 52.3s
[*] 结果保存至: keys/grok_20260309_120000_10.txt
```

> 💡 **浏览器模式自动回退**：若 `accounts.x.ai` 页面结构变更导致 Action ID 无法提取，程序会自动切换至 camoufox 无头浏览器注册模式，无需手动干预。

### 第八步：获取结果

注册成功的 SSO Token 保存在 `keys/` 目录下：

```bash
cat keys/grok_20260309_120000_10.txt
```

每行一个 SSO Token，可直接用于 Grok 登录。

---

## 服务器后台运行

使用 `screen` 或 `tmux` 在服务器后台持久运行：

```bash
# 使用 screen
screen -S grok
python grok.py
# Ctrl+A, D 脱离会话（程序继续后台运行）
# screen -r grok  重新连接

# 使用 tmux
tmux new -s grok
python grok.py
# Ctrl+B, D 脱离
# tmux attach -t grok  重新连接
```

---

## 常见问题

### camoufox 报错 "browser not found"

```bash
python -m camoufox fetch
```

### 无头模式下 camoufox 启动失败

确认系统已安装必要的共享库（Ubuntu/Debian）：

```bash
sudo apt-get install -y \
  libgtk-3-0 libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 \
  libxfixes3 libxi6 libxrandr2 libxrender1 libxss1 libxtst6 \
  libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
  libgbm1 libasound2 fonts-liberation libappindicator3-1
```

### 服务器上如何选择验证方式？

| 场景 | 推荐方式 |
|------|---------|
| 纯服务器，无 Docker | YesCaptcha（`YESCAPTCHA_KEY`） |
| 服务器，有 Docker | FlareSolverr 或 YesCaptcha |
| 任意环境（页面结构变化） | 程序自动切换浏览器模式，无需配置 |

### api_solver.py 是否支持无头服务器？

支持。`api_solver.py` 默认即为无头（headless）模式，服务器上直接运行即可：

```bash
# 服务器上（默认 headless，无需图形界面）
python api_solver.py --browser_type camoufox --thread 5 --debug

# 本地调试时启用 GUI（仅有图形界面时使用）
python api_solver.py --browser_type camoufox --thread 5 --debug --no-headless
```

---

## 注意事项

- 需要自行部署 moemail 临时邮箱服务
- 验证服务三选一：YesCaptcha（云端）、本地 Turnstile Solver（camoufox headless）、FlareSolverr（Docker）
- 程序在页面结构变更时自动切换浏览器注册模式
- 仅供学习研究使用

