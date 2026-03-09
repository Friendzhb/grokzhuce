# Grok 批量注册工具

批量注册 Grok 账号并自动开启 NSFW/Unhinged 功能。**完整支持无图形界面的 Linux 服务器终端运行，核心功能零浏览器依赖。**

## 功能

- 自动创建临时邮箱（基于 [moemail](https://github.com/beilunyang/moemail) 服务）
- 自动获取邮箱验证码
- 自动完成 Grok 注册流程
  - **HTTP 模式**（默认）：直接调用注册 API，速度快，仅需核心依赖，无浏览器/图形界面
  - **浏览器模式**（自动回退）：页面结构变化导致 HTTP 模式失效时自动切换为 camoufox 无头浏览器，需额外安装浏览器依赖
- 自动同意用户协议（TOS）
- 自动开启 NSFW/Unhinged 模式
- 注册完成后自动清理临时邮箱
- 支持多线程/多并发注册
- 支持 HTTP 代理

## 依赖说明

| 模式 | 需要安装 | 需要图形界面 | 推荐场景 |
|------|---------|------------|---------|
| **HTTP 模式 + YesCaptcha** | `requirements.txt` | ❌ 不需要 | **服务器首选** ★ |
| **HTTP 模式 + FlareSolverr** | `requirements.txt` | ❌ 不需要 | 有 Docker 的服务器 |
| **本地 Turnstile Solver** | `requirements.txt` + `requirements-browser.txt` | ❌ 不需要（headless）| 本地或服务器 |
| **浏览器兜底模式** | `requirements.txt` + `requirements-browser.txt` | ❌ 不需要（headless）| 自动触发 |

> **结论**：纯 HTTP 模式 + YesCaptcha 是服务器最简方案，只装 `requirements.txt` 即可，完全无浏览器依赖。

## 整体架构

```
┌─────────────────┐     ┌──────────────────────┐     ┌───────────────────┐
│  grok.py 主程序  │────▶│  moemail 临时邮箱服务  │────▶│  你的邮箱服务器    │
│  (批量注册入口)   │     │  (自行部署)            │     │                   │
└────────┬────────┘     └──────────────────────┘     └───────────────────┘
         │
         │  验证服务（三选一，★服务器推荐 YesCaptcha）
         ├──▶ YesCaptcha API（云端 API，零浏览器依赖）★
         ├──▶ 本地 Turnstile Solver（camoufox headless，需浏览器依赖）
         └──▶ FlareSolverr（Docker，Cloudflare 绕过）
                      │
         ┌────────────┴────────────┐
         │                         │
    找到 Action ID            未找到 Action ID
         │                         │
    HTTP 注册模式（快）        浏览器注册模式（兜底）
    仅需核心依赖               需浏览器依赖
         │                         │
         └────────────┬────────────┘
                      │
              grok.com（NSFW/Unhinged API）
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `grok.py` | 主程序，批量注册入口 |
| `requirements.txt` | **核心依赖**（无浏览器/图形界面，服务器可用） |
| `requirements-browser.txt` | **可选浏览器依赖**（本地 Solver 和浏览器兜底模式所需） |
| `TurnstileSolver.sh` | 本地 Turnstile Solver 启动脚本（Linux / macOS） |
| `TurnstileSolver.bat` | 本地 Turnstile Solver 启动脚本（Windows） |
| `api_solver.py` | 本地 Turnstile 验证码解决器（headless，需浏览器依赖） |
| `browser_configs.py` | 浏览器指纹配置 |
| `db_results.py` | 验证结果存储（内存模式） |
| `g/email_service.py` | 临时邮箱服务（moemail API） |
| `g/turnstile_service.py` | Turnstile 验证服务（本地 Solver / YesCaptcha） |
| `g/browser_register.py` | 浏览器兜底注册（camoufox，自动回退，需浏览器依赖） |
| `g/user_agreement_service.py` | 用户协议同意服务 |
| `g/nsfw_service.py` | NSFW/Unhinged 设置服务 |
| `g/flaresolverr_service.py` | FlareSolverr Cloudflare 绕过服务 |
| `.env.example` | 环境变量模板 |

---

## 服务器部署指南（无图形界面）

### 前置条件

- Python 3.11（推荐，见下方第二步安装说明）
- Linux 服务器（CentOS / RHEL / Ubuntu / Debian）
- 已部署 [moemail](https://github.com/beilunyang/moemail) 临时邮箱服务

---

### 第一步：部署 moemail 临时邮箱服务

moemail 是本项目依赖的临时邮箱服务，需自行部署。请参考 [moemail 项目文档](https://github.com/beilunyang/moemail) 完成部署。

部署完成后，记录以下信息：
- **moemail 服务地址**：例如 `https://mail.example.com`
- **API Key**：moemail 后台生成的 API 密钥
- **邮箱域名**：配置在 moemail 中的收信域名，例如 `example.com`

---

### 第二步：安装 Python 3.11

#### CentOS / RHEL（yum）

```bash
# 更新软件源
yum update -y

# 安装 Python 3.11（阿里云 / 官方 YUM 源已内置）
yum install python3.11 -y

# 验证
python3.11 --version
# 应显示 Python 3.11.x
```

#### Ubuntu / Debian（apt）

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip
python3.11 --version
```

---

### 第三步：获取项目并创建虚拟环境

```bash
# 克隆项目
git clone https://github.com/Friendzhb/grokzhuce.git
cd grokzhuce

# 创建 Python 3.11 虚拟环境
python3.11 -m venv venv311

# 激活虚拟环境
source venv311/bin/activate
```

---

### 第四步：安装依赖

#### 仅安装核心依赖（推荐，无浏览器依赖）

适用于：HTTP 模式 + YesCaptcha 或 FlareSolverr

```bash
pip install -r requirements.txt -i https://pypi.org/simple/
```

#### 同时安装浏览器依赖（可选）

仅在需要本地 Turnstile Solver 或浏览器兜底注册时安装：

```bash
pip install -r requirements.txt -r requirements-browser.txt -i https://pypi.org/simple/

# 首次安装后还需下载浏览器内核（约 100 MB）
python -m camoufox fetch
```

> 浏览器依赖（`camoufox`、`patchright`）需要系统浏览器运行库，安装时间较长。若只用 YesCaptcha，无需此步。

---

### 第五步：配置环境变量

```bash
cp .env.example .env
vim .env   # 或 nano .env
```

编辑 `.env` 文件，填入你的配置：

```ini
# ===== 必填：moemail 邮箱服务 =====
MOEMAIL_API_KEY=your-moemail-api-key       # moemail 后台生成的 API Key
MOEMAIL_BASE_URL=https://mail.example.com  # moemail 服务地址
MOEMAIL_DOMAIN=example.com                 # 邮箱域名

# ===== 验证服务（三选一）=====

# 【推荐·服务器首选】YesCaptcha 云端 API，无需浏览器，直接填 Key 即可
YESCAPTCHA_KEY=your-yescaptcha-api-key

# 【可选】FlareSolverr（需单独运行 Docker）
FLARESOLVERR_URL=http://localhost:8191
FLARESOLVERR_REFRESH_INTERVAL=600
FLARESOLVERR_TIMEOUT=60

# 【可选】本地 Turnstile Solver（需安装浏览器依赖并运行 api_solver.py）
# YESCAPTCHA_KEY= 留空时自动尝试本地 Solver（http://127.0.0.1:5072）
```

配置项说明：

| 配置项 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `MOEMAIL_API_KEY` | ✅ | - | moemail API 密钥 |
| `MOEMAIL_BASE_URL` | ✅ | - | moemail 服务地址 |
| `MOEMAIL_DOMAIN` | ❌ | 从 API 自动获取 | 邮箱域名 |
| `YESCAPTCHA_KEY` | ❌ | 空（尝试本地 Solver）| YesCaptcha API Key，**服务器推荐** |
| `FLARESOLVERR_URL` | ❌ | `http://localhost:8191` | FlareSolverr 地址 |
| `FLARESOLVERR_REFRESH_INTERVAL` | ❌ | `600` | cf_clearance 刷新间隔（秒） |
| `FLARESOLVERR_TIMEOUT` | ❌ | `60` | FlareSolverr 超时（秒） |

---

### 第六步：选择并启动验证服务

> 三种方式选其一即可，也可同时启用。**服务器首选方式一（YesCaptcha）**。

---

**方式一：YesCaptcha（推荐，零浏览器依赖）★**

在 `.env` 中填入 `YESCAPTCHA_KEY=your-key`，无需启动任何额外进程，直接进入第七步。

---

**方式二：FlareSolverr（需要 Docker）**

```bash
docker run -d \
  --name flaresolverr \
  -p 8191:8191 \
  ghcr.io/flaresolverr/flaresolverr:latest

# 验证
curl http://localhost:8191/
```

---

**方式三：本地 Turnstile Solver（需要浏览器依赖）**

> 先确保已执行第四步中的浏览器依赖安装，并已运行 `python -m camoufox fetch`

```bash
# 前台运行（调试用）
bash TurnstileSolver.sh

# 后台常驻运行
nohup bash TurnstileSolver.sh > turnstile.log 2>&1 &
echo "Solver PID: $!"

# 验证
curl http://127.0.0.1:5072/
```

---

### 第七步：运行注册程序

```bash
# 确保虚拟环境已激活
source venv311/bin/activate

python grok.py
```

程序读取 `.env` 中的配置，按提示输入（直接回车使用默认值）：

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

[FlareSolverr Cloudflare 绕过（可选）]
  FlareSolverr URL [http://localhost:8191]:
  cf_clearance 刷新间隔秒 [600]:
  FlareSolverr 超时秒 [60]:

[代理设置（留空不使用代理）]
  HTTP 代理地址 (例: http://127.0.0.1:10808):

[注册参数]
  并发线程数 [8]: 8
  注册账号数量 [100]: 10
```

---

### 第八步：等待注册完成

程序自动执行注册并实时输出进度：

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

> 💡 **浏览器模式自动回退**：若 `accounts.x.ai` 页面结构变更导致 Action ID 无法提取，且已安装浏览器依赖（`requirements-browser.txt`），程序将自动切换至 camoufox 无头浏览器注册模式。

---

### 第九步：获取结果

```bash
cat keys/grok_20260309_120000_10.txt
```

每行一个 SSO Token，可直接用于 Grok 登录。

---

## 服务器后台运行

使用 `screen` 或 `tmux` 让程序在后台持续运行（断开 SSH 后不中断）：

```bash
# ---- 使用 screen ----
# 安装（CentOS）
yum install screen -y
# 安装（Ubuntu/Debian）
# apt install screen -y

screen -S grok                   # 新建会话
source venv311/bin/activate      # 激活虚拟环境
python grok.py                   # 启动程序
# Ctrl+A, D  →  脱离会话（程序继续运行）
# screen -r grok  →  重新连接

# ---- 使用 tmux ----
# 安装（CentOS）
yum install tmux -y

tmux new -s grok                 # 新建会话
source venv311/bin/activate
python grok.py
# Ctrl+B, D  →  脱离
# tmux attach -t grok  →  重新连接
```

---

## 常见问题

### 系统没有 Python 3.11，yum 找不到？

```bash
# CentOS 7 自带的 yum 源不含 Python 3.11，推荐使用 pyenv 安装
curl https://pyenv.run | bash
# 按提示将 pyenv 初始化代码加入 ~/.bashrc，然后重新加载：
source ~/.bashrc
pyenv install 3.11.9
pyenv global 3.11.9
python3.11 --version   # 确认版本
```

### pip 安装很慢或失败？

```bash
# 使用清华镜像源（国内服务器）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 或使用阿里云镜像
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### curl_cffi 安装失败（CentOS 编译报错）？

```bash
# 升级 pip 和 setuptools 后重试
pip install --upgrade pip setuptools wheel
pip install curl_cffi -i https://pypi.org/simple/
```

### camoufox 报错 "browser not found"（仅浏览器模式需要）

```bash
python -m camoufox fetch
```

### camoufox 在服务器上启动失败（缺少系统库）

**CentOS / RHEL：**
```bash
yum install -y \
  gtk3 libX11 libXcomposite libXcursor libXdamage libXext \
  libXfixes libXi libXrandr libXrender libXScrnSaver libXtst \
  nss atk at-spi2-core cups-libs libdrm mesa-libgbm alsa-lib
```

**Ubuntu / Debian：**
```bash
sudo apt-get install -y \
  libgtk-3-0 libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 \
  libxfixes3 libxi6 libxrandr2 libxrender1 libxss1 libxtst6 \
  libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
  libgbm1 libasound2
```

### 服务器上如何选择验证方式？

| 场景 | 推荐方式 | 额外依赖 |
|------|---------|---------|
| 纯服务器，最简方案 | YesCaptcha（`YESCAPTCHA_KEY`）| 无 |
| 有 Docker 的服务器 | FlareSolverr | Docker |
| 需要本地 Solver | `TurnstileSolver.sh` | `requirements-browser.txt` |
| 页面结构变化（兜底）| 程序自动切换浏览器模式 | `requirements-browser.txt` |

---

## 注意事项

- 需要自行部署 moemail 临时邮箱服务
- 纯 HTTP 模式（`requirements.txt` 核心依赖）无任何浏览器/图形界面依赖，服务器可直接运行
- 浏览器依赖（`requirements-browser.txt`）仅在使用本地 Turnstile Solver 或浏览器兜底模式时需要
- 仅供学习研究使用


