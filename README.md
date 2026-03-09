# Grok 批量注册工具

批量注册 Grok 账号并自动开启 NSFW/Unhinged 功能。

## 功能

- 自动创建临时邮箱（基于 [moemail](https://github.com/beilunyang/moemail) 服务）
- 自动获取邮箱验证码
- 自动完成 Grok 注册流程（含 Turnstile 验证码自动解决）
- 自动同意用户协议（TOS）
- 自动开启 NSFW/Unhinged 模式
- 注册完成后自动清理临时邮箱
- 支持多线程并发注册
- 支持 FlareSolverr 绕过 Cloudflare（可选）
- 支持 HTTP 代理

## 整体架构

```
┌─────────────────┐     ┌──────────────────────┐     ┌───────────────────┐
│  grok.py 主程序  │────▶│  moemail 临时邮箱服务  │────▶│ mail.zhouhongbin  │
│  (批量注册入口)   │     │  (自行部署)            │     │  .top             │
└────────┬────────┘     └──────────────────────┘     └───────────────────┘
         │
         ├──▶ Turnstile Solver (本地验证码服务, 端口 5072)
         │       或 YesCaptcha API (第三方, 可选)
         │
         ├──▶ accounts.x.ai (Grok 注册 API)
         │
         ├──▶ grok.com (NSFW/Unhinged 设置 API)
         │
         └──▶ FlareSolverr (Cloudflare 绕过, 可选, 端口 8191)
```

## 注册流程

```
启动 → 交互式配置 → 扫描注册页参数(Action ID / Site Key)
                            │
                            ▼
                    启动 N 个并发线程
                            │
                ┌───────────┼───────────┐
                ▼           ▼           ▼
          ┌──────────────────────────────────┐
          │  单线程注册循环:                     │
          │  1. 创建临时邮箱 (moemail API)      │
          │  2. 发送验证码 (accounts.x.ai)      │
          │  3. 轮询获取验证码 (moemail API)     │
          │  4. 验证邮箱验证码 (accounts.x.ai)   │
          │  5. 获取 Turnstile Token            │
          │  6. 获取 cf_clearance (可选)         │
          │  7. 提交注册请求                     │
          │  8. 同意用户协议 (TOS)               │
          │  9. 开启 NSFW 模式                   │
          │  10. 保存 SSO Token                 │
          │  11. 删除临时邮箱                    │
          └──────────────────────────────────┘
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
| `TurnstileSolver.bat` | Turnstile Solver 启动脚本（Windows） |
| `api_solver.py` | Turnstile 验证码解决器（本地服务） |
| `browser_configs.py` | 浏览器指纹配置 |
| `db_results.py` | 验证结果存储（内存模式） |
| `g/email_service.py` | 临时邮箱服务（moemail API） |
| `g/turnstile_service.py` | Turnstile 验证服务（本地 Solver / YesCaptcha） |
| `g/user_agreement_service.py` | 用户协议同意服务 |
| `g/nsfw_service.py` | NSFW/Unhinged 设置服务 |
| `g/flaresolverr_service.py` | FlareSolverr Cloudflare 绕过服务 |
| `.env.example` | 环境变量模板 |
| `requirements.txt` | Python 依赖列表 |

## 部署流程

### 前置条件

- Python 3.8+
- 一台可用的服务器或本地机器
- 已部署 [moemail](https://github.com/beilunyang/moemail) 临时邮箱服务

### 第一步：部署 moemail 临时邮箱服务

moemail 是本项目依赖的临时邮箱服务，需自行部署。请参考 [moemail 项目文档](https://github.com/beilunyang/moemail) 完成部署。

部署完成后，你应该拥有：
- **moemail 服务地址**：例如 `https://mail.zhouhongbin.top`
- **API Key**：moemail 后台生成的 API 密钥
- **邮箱域名**：配置在 moemail 中的收信域名，例如 `zhouhongbin.top`

验证 moemail 服务是否正常：

```bash
# 获取域名配置
curl -X GET https://mail.zhouhongbin.top/api/config \
  -H "X-API-Key: YOUR_API_KEY"

# 测试创建临时邮箱（domain 填写你在 moemail 中配置的收信域名）
curl -X POST https://mail.zhouhongbin.top/api/emails/generate \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test",
    "expiryTime": 3600000,
    "domain": "zhouhongbin.top"
  }'
```

### 第二步：安装 Python 依赖

```bash
git clone https://github.com/Friendzhb/grokzhuce.git
cd grokzhuce
pip install -r requirements.txt
```

### 第三步：配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```ini
# moemail 邮箱服务配置
MOEMAIL_API_KEY=your-moemail-api-key          # moemail API 密钥（必填）
MOEMAIL_BASE_URL=https://mail.zhouhongbin.top # moemail 服务地址（必填）
MOEMAIL_DOMAIN=zhouhongbin.top                # 邮箱域名（可选，默认从 API 获取）

# Turnstile 验证配置
# 如果不填则使用本地 Turnstile Solver（http://127.0.0.1:5072）
YESCAPTCHA_KEY=

# FlareSolverr 配置（可选，用于绕过 Cloudflare）
FLARESOLVERR_URL=http://localhost:8191
FLARESOLVERR_REFRESH_INTERVAL=600
FLARESOLVERR_TIMEOUT=60
```

配置项说明：

| 配置项 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `MOEMAIL_API_KEY` | ✅ | - | moemail API 密钥 |
| `MOEMAIL_BASE_URL` | ✅ | `https://mail.zhouhongbin.top` | moemail 服务地址 |
| `MOEMAIL_DOMAIN` | ❌ | 从 API 自动获取 | 邮箱域名，如 `zhouhongbin.top` |
| `YESCAPTCHA_KEY` | ❌ | 空（使用本地 Solver） | YesCaptcha API Key |
| `FLARESOLVERR_URL` | ❌ | `http://localhost:8191` | FlareSolverr 服务地址 |
| `FLARESOLVERR_REFRESH_INTERVAL` | ❌ | `600` | cf_clearance 缓存刷新间隔（秒） |
| `FLARESOLVERR_TIMEOUT` | ❌ | `60` | FlareSolverr 请求超时（秒） |

### 第四步：部署 FlareSolverr（可选）

如果注册过程中遇到 Cloudflare 403 拦截，需要部署 FlareSolverr：

```bash
docker run -d \
  --name flaresolverr \
  -p 8191:8191 \
  ghcr.io/flaresolverr/flaresolverr:latest
```

验证 FlareSolverr 是否正常：

```bash
curl http://localhost:8191/
```

## 使用流程

### 第一步：启动 Turnstile Solver

> 如果在 `.env` 中配置了 `YESCAPTCHA_KEY`，则跳过此步骤。

在终端中运行：

```bash
# Windows
TurnstileSolver.bat

# Linux / macOS
python api_solver.py --browser_type camoufox --thread 5 --debug
```

等待 Solver 启动完成，看到监听端口日志后即可（默认 `http://127.0.0.1:5072`）。

### 第二步：运行注册程序

新开一个终端窗口，运行：

```bash
python grok.py
```

程序会启动交互式配置向导，按提示输入（直接回车使用默认值）：

```
============================================================
  Grok 注册机 - 启动配置
  直接回车使用括号中的默认值 / .env 配置
============================================================

[邮箱服务 moemail]
  moemail API Key [未设置]: your-api-key
  moemail Base URL [https://mail.zhouhongbin.top]:
  邮箱域名 [zhouhongbin.top]:

[验证码服务]
  YesCaptcha Key (留空使用本地 Turnstile Solver) [未设置]:

[FlareSolverr Cloudflare 绕过]
  FlareSolverr URL [http://localhost:8191]:
  cf_clearance 刷新间隔秒 [600]:
  FlareSolverr 超时秒 [60]:

[代理设置（留空不使用代理）]
  HTTP 代理地址 (例: http://127.0.0.1:10808):

[注册参数]
  并发线程数 [8]: 8
  注册账号数量 [100]: 10
```

### 第三步：等待注册完成

程序将自动执行注册流程：

```
============================================================
Grok 注册机
============================================================
[*] 正在初始化，扫描注册页面参数...
[+] Action ID: 7f67aa61adfb0655899002808e1d443935b057c25b
[*] 启动 8 个线程，目标 10 个账号
[*] 输出文件: keys/grok_20260204_190000_10.txt
============================================================
[*] 开始注册: abc123@zhouhongbin.top
[+] 1/10 abc123@zhouhongbin.top | 5.2s/个
[+] 2/10 def456@zhouhongbin.top | 4.8s/个
...
[*] 开始二次验证 NSFW...
[*] 二次验证完成: 10/10
[*] 完成！共注册 10 个账号，耗时 52.3s
[*] 结果保存至: keys/grok_20260204_190000_10.txt
```

### 第四步：获取结果

注册成功的 SSO Token 保存在 `keys/` 目录下：

```bash
cat keys/grok_20260204_190000_10.txt
```

每行一个 SSO Token，可直接用于 Grok 登录。

## 注意事项

- 需要自行部署 moemail 临时邮箱服务，并确保邮箱域名（如 `zhouhongbin.top`）配置正确
- 运行前必须先启动 Turnstile Solver（除非使用 YesCaptcha）
- FlareSolverr 为可选服务，遇到 Cloudflare 拦截时才需要
- 仅供学习研究使用
