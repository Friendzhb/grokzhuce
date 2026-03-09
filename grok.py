import asyncio
import os, json, random, string, time, re, struct
import threading
import concurrent.futures
from datetime import datetime
from urllib.parse import urljoin
from curl_cffi import requests
from bs4 import BeautifulSoup

from g import EmailService, TurnstileService, UserAgreementService, NsfwSettingsService, FlareSolverrService
from g.browser_register import register_one as browser_register_one

# 基础配置
site_url = "https://accounts.x.ai"
DEFAULT_IMPERSONATE = "chrome120"
RSC_ACTION_ID_PATTERN = r'"id":"([a-fA-F0-9]{20,})","bound"'
CHROME_PROFILES = [
    {"impersonate": "chrome110", "version": "110.0.0.0", "brand": "chrome"},
    {"impersonate": "chrome119", "version": "119.0.0.0", "brand": "chrome"},
    {"impersonate": "chrome120", "version": "120.0.0.0", "brand": "chrome"},
    {"impersonate": "edge99",    "version": "99.0.1150.36", "brand": "edge"},
    {"impersonate": "edge101",   "version": "101.0.1210.47", "brand": "edge"},
]

def get_random_chrome_profile():
    profile = random.choice(CHROME_PROFILES)
    if profile.get("brand") == "edge":
        chrome_major = profile["version"].split(".")[0]
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_major}.0.0.0 Safari/537.36 Edg/{profile['version']}"
        )
    else:
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{profile['version']} Safari/537.36"
        )
    return profile["impersonate"], ua

# 运行时配置（由 main() 中交互式输入填充）
runtime_config = {
    "moemail_api_key": "",
    "moemail_base_url": "https://mail.zhouhongbin.top",
    "moemail_domain": "zhouhongbin.top",
    "yescaptcha_key": "",
    "flaresolverr_url": "http://localhost:8191",
    "flaresolverr_refresh_interval": 600,
    "flaresolverr_timeout": 60,
    "proxies": {},
}

# 动态获取的全局变量
config = {
    "site_key": "0x4AAAAAAAhr9JGVDZbrZOo0",
    "action_id": None,
    "state_tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22(app)%22%2C%7B%22children%22%3A%5B%22(auth)%22%2C%7B%22children%22%3A%5B%22sign-up%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fsign-up%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
}

post_lock = threading.Lock()
file_lock = threading.Lock()
success_count = 0
start_time = time.time()
target_count = 100
stop_event = threading.Event()
output_file = None
flaresolverr_service = None  # 全局 FlareSolverr 实例
turnstile_available = False  # Turnstile Solver / YesCaptcha 是否可用

def generate_random_name() -> str:
    length = random.randint(4, 6)
    return random.choice(string.ascii_uppercase) + ''.join(random.choice(string.ascii_lowercase) for _ in range(length - 1))

def generate_random_string(length: int = 15) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))

def encode_grpc_message(field_id, string_value):
    key = (field_id << 3) | 2
    value_bytes = string_value.encode('utf-8')
    length = len(value_bytes)
    payload = struct.pack('B', key) + struct.pack('B', length) + value_bytes
    return b'\x00' + struct.pack('>I', len(payload)) + payload

def encode_grpc_message_verify(email, code):
    p1 = struct.pack('B', (1 << 3) | 2) + struct.pack('B', len(email)) + email.encode('utf-8')
    p2 = struct.pack('B', (2 << 3) | 2) + struct.pack('B', len(code)) + code.encode('utf-8')
    payload = p1 + p2
    return b'\x00' + struct.pack('>I', len(payload)) + payload

def send_email_code_grpc(session, email):
    url = f"{site_url}/auth_mgmt.AuthManagement/CreateEmailValidationCode"
    data = encode_grpc_message(1, email)
    headers = {
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "x-user-agent": "connect-es/2.1.1",
        "origin": site_url,
        "referer": f"{site_url}/sign-up?redirect=grok-com",
    }
    try:
        res = session.post(url, data=data, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"[-] {email} 发送验证码失败: HTTP {res.status_code}")
            return False
        return True
    except Exception as e:
        print(f"[-] {email} 发送验证码异常: {e}")
        return False

def verify_email_code_grpc(session, email, code):
    url = f"{site_url}/auth_mgmt.AuthManagement/VerifyEmailValidationCode"
    data = encode_grpc_message_verify(email, code)
    headers = {
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "x-user-agent": "connect-es/2.1.1",
        "origin": site_url,
        "referer": f"{site_url}/sign-up?redirect=grok-com",
    }
    try:
        res = session.post(url, data=data, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"[-] {email} 验证验证码失败: HTTP {res.status_code}")
            return False
        return True
    except Exception as e:
        print(f"[-] {email} 验证验证码异常: {e}")
        return False

def get_cf_clearance(target: str) -> dict:
    """从全局 FlareSolverr 实例获取 cf_clearance，不可用时返回空字典"""
    if flaresolverr_service is None:
        return {}
    return flaresolverr_service.get_clearance(target)

def register_single_thread():
    # 错峰启动，防止瞬时并发过高
    time.sleep(random.uniform(0, 5))

    try:
        email_service = EmailService(
            api_key=runtime_config["moemail_api_key"],
            base_url=runtime_config["moemail_base_url"],
            domain=runtime_config["moemail_domain"],
        )
        turnstile_service = TurnstileService()
        user_agreement_service = UserAgreementService()
        nsfw_service = NsfwSettingsService()
    except Exception as e:
        print(f"[-] 服务初始化失败: {e}")
        return

    final_action_id = config["action_id"]
    if not final_action_id:
        print("[-] 线程退出：缺少 Action ID")
        return

    while True:
        email_id = None
        email_address = None
        try:
            if stop_event.is_set():
                return

            impersonate_fingerprint, account_user_agent = get_random_chrome_profile()
            proxies = runtime_config["proxies"]

            with requests.Session(impersonate=impersonate_fingerprint, proxies=proxies) as session:
                # 预热连接
                try:
                    session.get(site_url, timeout=10)
                except Exception:
                    pass

                password = generate_random_string()

                # 创建邮箱 — 返回 (email_id, email_address)
                try:
                    email_id, email_address = email_service.create_email()
                except Exception as e:
                    print(f"[-] 邮箱服务抛出异常: {e}")
                    email_id, email_address = None, None

                if not email_address or not email_id:
                    print("[-] 创建邮箱失败，5秒后重试")
                    time.sleep(5)
                    continue

                if stop_event.is_set():
                    email_service.delete_email(email_id)
                    return

                print(f"[*] 开始注册: {email_address}")

                # Step 1: 发送验证码
                if not send_email_code_grpc(session, email_address):
                    email_service.delete_email(email_id)
                    time.sleep(5)
                    continue

                # Step 2: 获取验证码（使用 email_id 调用 moemail API）
                verify_code = email_service.fetch_verification_code(email_id)
                if not verify_code:
                    print(f"[-] {email_address} 未获取到验证码")
                    email_service.delete_email(email_id)
                    continue

                # Step 3: 验证验证码
                if not verify_email_code_grpc(session, email_address, verify_code):
                    email_service.delete_email(email_id)
                    continue

                # Step 4: 注册重试循环（最多 3 次）
                abort_retries = False
                for attempt in range(3):
                    if stop_event.is_set():
                        email_service.delete_email(email_id)
                        return

                    token = ""
                    if turnstile_available:
                        try:
                            task_id = turnstile_service.create_task(site_url, config["site_key"])
                            token = turnstile_service.get_response(task_id)
                        except Exception as e:
                            print(f"[-] {email_address} Turnstile 请求异常: {e}")
                            token = None

                        if not token or token == "CAPTCHA_FAIL":
                            print(f"[-] {email_address} 第 {attempt+1} 次获取 Turnstile token 失败")
                            continue

                    # 尝试获取 cf_clearance（可选，失败不影响主流程）
                    cf_info = get_cf_clearance(site_url)

                    headers = {
                        "user-agent": account_user_agent,
                        "accept": "text/x-component",
                        "content-type": "text/plain;charset=UTF-8",
                        "origin": site_url,
                        "referer": f"{site_url}/sign-up",
                        "cookie": f"__cf_bm={session.cookies.get('__cf_bm', '')}",
                        "next-router-state-tree": config["state_tree"],
                        "next-action": final_action_id,
                    }
                    if cf_info.get("cf_clearance"):
                        headers["cookie"] += f"; cf_clearance={cf_info['cf_clearance']}"

                    payload = [{
                        "emailValidationCode": verify_code,
                        "createUserAndSessionRequest": {
                            "email": email_address,
                            "givenName": generate_random_name(),
                            "familyName": generate_random_name(),
                            "clearTextPassword": password,
                            "tosAcceptedVersion": "$undefined",
                        },
                        "turnstileToken": token,
                        "promptOnDuplicateEmail": True,
                    }]

                    try:
                        with post_lock:
                            res = session.post(f"{site_url}/sign-up", json=payload, headers=headers)
                    except Exception as e:
                        print(f"[-] {email_address} 注册请求异常: {e}")
                        time.sleep(3)
                        continue

                    if res.status_code == 200:
                        match = re.search(r'(https://[^" \s]+set-cookie\?q=[^:" \s]+)1:', res.text)
                        if not match:
                            print(f"[-] {email_address} 注册响应未找到验证 URL")
                            email_service.delete_email(email_id)
                            abort_retries = True
                            break

                        verify_url = match.group(1)
                        try:
                            session.get(verify_url, allow_redirects=True)
                        except Exception as e:
                            print(f"[-] {email_address} 访问验证 URL 异常: {e}")
                            email_service.delete_email(email_id)
                            abort_retries = True
                            break

                        sso = session.cookies.get("sso")
                        sso_rw = session.cookies.get("sso-rw")
                        if not sso:
                            print(f"[-] {email_address} 未获取到 sso cookie")
                            email_service.delete_email(email_id)
                            abort_retries = True
                            break

                        # TOS
                        tos_result = user_agreement_service.accept_tos_version(
                            sso=sso,
                            sso_rw=sso_rw or "",
                            impersonate=impersonate_fingerprint,
                            user_agent=account_user_agent,
                            cf_clearance=cf_info.get("cf_clearance"),
                        )
                        if not tos_result.get("ok"):
                            print(f"[-] {email_address} TOS 同意失败: {tos_result.get('error')}")
                            email_service.delete_email(email_id)
                            abort_retries = True
                            break

                        # NSFW
                        nsfw_result = nsfw_service.enable_nsfw(
                            sso=sso,
                            sso_rw=sso_rw or "",
                            impersonate=impersonate_fingerprint,
                            user_agent=account_user_agent,
                            cf_clearance=cf_info.get("cf_clearance"),
                        )
                        if not nsfw_result.get("ok"):
                            print(f"[-] {email_address} NSFW 设置失败: {nsfw_result.get('error')}")
                            email_service.delete_email(email_id)
                            abort_retries = True
                            break

                        # 写入结果
                        with file_lock:
                            global success_count
                            if success_count >= target_count:
                                if not stop_event.is_set():
                                    stop_event.set()
                                email_service.delete_email(email_id)
                                abort_retries = True
                                break
                            with open(output_file, "a") as f:
                                f.write(sso + "\n")
                            success_count += 1
                            elapsed = time.time() - start_time
                            avg = elapsed / success_count
                            print(f"[+] {success_count}/{target_count} {email_address} | {avg:.1f}s/个")
                            email_service.delete_email(email_id)
                            if success_count >= target_count and not stop_event.is_set():
                                stop_event.set()
                        abort_retries = True
                        break  # 注册成功，跳出 for 循环继续 while 注册下一个

                    elif res.status_code == 403:
                        print(f"[-] {email_address} 第 {attempt+1} 次注册 403 Forbidden（可能需要 cf_clearance）")
                        time.sleep(3)
                    else:
                        print(f"[-] {email_address} 第 {attempt+1} 次注册失败: HTTP {res.status_code}")
                        time.sleep(3)

                if not abort_retries:
                    # for 循环 3 次全部失败
                    print(f"[-] {email_address} 3 次注册均失败，删除邮箱")
                    email_service.delete_email(email_id)
                    time.sleep(5)

        except Exception as e:
            print(f"[-] 线程异常: {str(e)[:100]}")
            # 确保邮箱被清理
            if email_id:
                try:
                    email_service = EmailService(
                        api_key=runtime_config["moemail_api_key"],
                        base_url=runtime_config["moemail_base_url"],
                        domain=runtime_config["moemail_domain"],
                    )
                    email_service.delete_email(email_id)
                except Exception:
                    pass
            time.sleep(5)


def _prompt(prompt_text: str, default, cast=str):
    """带默认值的交互式输入，支持类型转换"""
    try:
        raw = input(prompt_text).strip()
        if raw == "":
            return default
        return cast(raw)
    except (EOFError, KeyboardInterrupt):
        return default
    except (ValueError, TypeError):
        print(f"  输入无效，使用默认值: {default}")
        return default


def interactive_config():
    """交互式配置向导，将结果写入 runtime_config"""
    print("\n" + "=" * 60)
    print("  Grok 注册机 - 启动配置")
    print("  直接回车使用括号中的默认值 / .env 配置")
    print("=" * 60)

    # 尝试从 .env 读取默认值
    from dotenv import load_dotenv
    load_dotenv()

    # --- moemail ---
    print("\n[邮箱服务 moemail]")
    runtime_config["moemail_api_key"] = _prompt(
        f"  moemail API Key [{os.getenv('MOEMAIL_API_KEY', '') or '未设置'}]: ",
        os.getenv("MOEMAIL_API_KEY", ""),
    )
    runtime_config["moemail_base_url"] = _prompt(
        f"  moemail Base URL [{os.getenv('MOEMAIL_BASE_URL', 'https://mail.zhouhongbin.top')}]: ",
        os.getenv("MOEMAIL_BASE_URL", "https://mail.zhouhongbin.top"),
    )
    runtime_config["moemail_domain"] = _prompt(
        f"  邮箱域名 [{os.getenv('MOEMAIL_DOMAIN', 'zhouhongbin.top')}]: ",
        os.getenv("MOEMAIL_DOMAIN", "zhouhongbin.top"),
    )

    # --- Turnstile / YesCaptcha ---
    print("\n[验证码服务（可选，和 FlareSolverr 二选一即可）]")
    runtime_config["yescaptcha_key"] = _prompt(
        f"  YesCaptcha Key (留空使用本地 Turnstile Solver) [{os.getenv('YESCAPTCHA_KEY', '') or '未设置'}]: ",
        os.getenv("YESCAPTCHA_KEY", ""),
    )
    # 写入环境变量，TurnstileService 从 env 读取
    if runtime_config["yescaptcha_key"]:
        os.environ["YESCAPTCHA_KEY"] = runtime_config["yescaptcha_key"]

    # --- FlareSolverr ---
    print("\n[FlareSolverr Cloudflare 绕过（可选，和 Turnstile Solver 二选一即可）]")
    runtime_config["flaresolverr_url"] = _prompt(
        f"  FlareSolverr URL [{os.getenv('FLARESOLVERR_URL', 'http://localhost:8191')}]: ",
        os.getenv("FLARESOLVERR_URL", "http://localhost:8191"),
    )
    runtime_config["flaresolverr_refresh_interval"] = _prompt(
        f"  cf_clearance 刷新间隔秒 [{os.getenv('FLARESOLVERR_REFRESH_INTERVAL', '600')}]: ",
        int(os.getenv("FLARESOLVERR_REFRESH_INTERVAL", 600)),
        cast=int,
    )
    runtime_config["flaresolverr_timeout"] = _prompt(
        f"  FlareSolverr 超时秒 [{os.getenv('FLARESOLVERR_TIMEOUT', '60')}]: ",
        int(os.getenv("FLARESOLVERR_TIMEOUT", 60)),
        cast=int,
    )

    # --- 代理 ---
    print("\n[代理设置（留空不使用代理）]")
    proxy = _prompt("  HTTP 代理地址 (例: http://127.0.0.1:10808): ", "")
    if proxy:
        runtime_config["proxies"] = {"http": proxy, "https": proxy}

    # --- 注册参数 ---
    print("\n[注册参数]")
    threads = _prompt("  并发线程数 [8]: ", 8, cast=int)
    total = _prompt("  注册账号数量 [100]: ", 100, cast=int)
    threads = max(1, threads)
    total = max(1, total)

    print("\n[配置确认]")
    print(f"  moemail API Key : {'*' * 8 + '...' if runtime_config['moemail_api_key'] else '未设置'}")
    print(f"  moemail Base URL: {runtime_config['moemail_base_url']}")
    print(f"  邮箱域名        : {runtime_config['moemail_domain']}")
    print(f"  YesCaptcha Key  : {'已设置' if runtime_config['yescaptcha_key'] else '未设置（本地 Solver）'}")
    print(f"  FlareSolverr    : {runtime_config['flaresolverr_url']}")
    print(f"  代理            : {runtime_config['proxies'] or '不使用'}")
    print(f"  并发 / 数量     : {threads} 线程 / {total} 个账号")

    return threads, total


async def _run_browser_registration(threads: int, total: int) -> None:
    """
    使用浏览器自动化完成注册（参考 jiang068/grok_reg 项目）。

    当 Action ID 无法从注册页面提取时，自动切换至此模式。
    启动 threads 个并发浏览器任务，每个任务注册成功后继续循环，
    直到达到目标数量 total 为止。
    """
    global success_count

    email_service = EmailService(
        api_key=runtime_config["moemail_api_key"],
        base_url=runtime_config["moemail_base_url"],
        domain=runtime_config["moemail_domain"],
    )

    proxies = runtime_config.get("proxies", {})
    proxy_url = proxies.get("http") or proxies.get("https") if proxies else None

    async def worker() -> None:
        global success_count
        while not stop_event.is_set():
            result = await browser_register_one(email_service, proxy=proxy_url)
            if stop_event.is_set():
                return
            if result and result.get("sso"):
                with file_lock:
                    if success_count >= target_count:
                        if not stop_event.is_set():
                            stop_event.set()
                        return
                    with open(output_file, "a") as f:
                        f.write(result["sso"] + "\n")
                    success_count += 1
                    elapsed = time.time() - start_time
                    avg = elapsed / success_count
                    print(f"[+] {success_count}/{target_count} | {avg:.1f}s/个")
                    if success_count >= target_count and not stop_event.is_set():
                        stop_event.set()
            else:
                # 短暂等待再重试，防止失败时紧密循环
                await asyncio.sleep(2)

    tasks = [asyncio.create_task(worker()) for _ in range(threads)]
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def main():
    global flaresolverr_service, turnstile_available, target_count, output_file, start_time

    print("=" * 60 + "\nGrok 注册机\n" + "=" * 60)

    # 1. 交互式配置
    threads, total = interactive_config()

    # 校验必要配置
    if not runtime_config["moemail_api_key"]:
        print("\n[-] 错误: moemail API Key 未设置，无法继续")
        return

    # 2. 检查 Turnstile Solver / YesCaptcha 可用性
    _ts = TurnstileService()
    turnstile_available = _ts.is_available()
    if turnstile_available:
        print(f"\n[+] Turnstile 验证服务可用"
              + (" (YesCaptcha)" if _ts.yescaptcha_key else " (本地 Solver)"))
    else:
        print(f"\n[!] Turnstile 验证服务不可用（本地 Solver 未启动且未配置 YesCaptcha）")

    # 3. 初始化 FlareSolverr
    flaresolverr_service = FlareSolverrService(
        url=runtime_config["flaresolverr_url"],
        refresh_interval=runtime_config["flaresolverr_refresh_interval"],
        timeout=runtime_config["flaresolverr_timeout"],
    )
    flaresolverr_ok = flaresolverr_service.is_available()
    if flaresolverr_ok:
        print(f"[+] FlareSolverr 已连接: {runtime_config['flaresolverr_url']}")
    else:
        print(f"[!] FlareSolverr 不可用 ({runtime_config['flaresolverr_url']})，将跳过 cf_clearance 注入")

    # 校验：HTTP 模式需要至少一个验证服务；浏览器模式无需此检查
    if not turnstile_available and not flaresolverr_ok:
        print("\n[!] Turnstile Solver/YesCaptcha 和 FlareSolverr 均不可用")
        print("    HTTP 注册模式需要其中一个；如果页面结构已变更，将自动切换至浏览器注册模式")

    # 4. 扫描 Grok 注册页面参数
    print("\n[*] 正在初始化，扫描注册页面参数...")
    start_url = f"{site_url}/sign-up"
    with requests.Session(impersonate=DEFAULT_IMPERSONATE) as s:
        try:
            html = s.get(start_url, timeout=15).text
            # Site Key
            key_match = re.search(r'sitekey":"(0x4[a-zA-Z0-9_-]+)"', html)
            if key_match:
                config["site_key"] = key_match.group(1)
            # State Tree
            tree_match = re.search(r'next-router-state-tree":"([^"]+)"', html)
            if tree_match:
                config["state_tree"] = tree_match.group(1)
            # Action ID — 多策略提取
            action_id = None

            # 策略 1: 从 HTML 内联 RSC flight data 中查找
            html_unescaped = html.replace('\\"', '"')
            rsc_match = re.search(RSC_ACTION_ID_PATTERN, html_unescaped)
            if rsc_match:
                action_id = rsc_match.group(1)

            # 策略 2: 从 _next/static JS 文件中查找
            if not action_id:
                soup = BeautifulSoup(html, 'html.parser')
                js_urls = [
                    urljoin(start_url, script['src'])
                    for script in soup.find_all('script', src=True)
                    if '_next/static' in script['src']
                ]
                for js_url in js_urls:
                    if action_id:
                        break
                    try:
                        js_content = s.get(js_url, timeout=10).text
                        # 原始 pattern: 7f 前缀 + 40 个十六进制字符
                        m = re.search(r'7f[a-fA-F0-9]{40}', js_content)
                        if m:
                            action_id = m.group(0)
                            break
                        # 从 JS 中查找 RSC server reference 格式
                        js_unescaped = js_content.replace('\\"', '"')
                        m = re.search(RSC_ACTION_ID_PATTERN, js_unescaped)
                        if m:
                            action_id = m.group(1)
                            break
                    except Exception as e:
                        print(f"[-] 获取 JS 文件失败 ({js_url}): {e}")

            if action_id:
                config["action_id"] = action_id
                print(f"[+] Action ID: {config['action_id']}")
        except Exception as e:
            print(f"[-] 初始化扫描失败: {e}，将尝试浏览器注册模式")

    if not config["action_id"]:
        print("[!] 未找到 Action ID（注册页面结构已更新），切换至浏览器注册模式...")
        print("[*] 浏览器模式基于 camoufox，无需 Action ID 即可完成注册")

        # 5b. 浏览器注册模式（无需 Action ID）
        target_count = total
        start_time = time.time()
        stop_event.clear()

        os.makedirs("keys", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"keys/grok_{timestamp}_{target_count}.txt"

        print(f"\n[*] 启动 {threads} 个并发浏览器，目标 {target_count} 个账号")
        print(f"[*] 输出文件: {output_file}")
        print("=" * 60)

        try:
            asyncio.run(_run_browser_registration(threads, total))
        except KeyboardInterrupt:
            print("\n[!] 收到中断信号，正在停止...")
            stop_event.set()

        # 二次验证 NSFW
        if os.path.exists(output_file):
            print(f"\n[*] 开始二次验证 NSFW...")
            nsfw_service = NsfwSettingsService()
            with open(output_file, "r") as f:
                tokens = [line.strip() for line in f if line.strip()]
            ok_count = 0
            for sso in tokens:
                try:
                    result = nsfw_service.enable_unhinged(sso)
                    if result.get("ok"):
                        ok_count += 1
                    else:
                        print(f"[-] enable_unhinged 失败: {result.get('error', result)}")
                except Exception as e:
                    print(f"[-] enable_unhinged 异常: {e}")
            print(f"[*] 二次验证完成: {ok_count}/{len(tokens)}")

        elapsed = time.time() - start_time
        print(f"\n[*] 完成！共注册 {success_count} 个账号，耗时 {elapsed:.1f}s")
        print(f"[*] 结果保存至: {output_file}")
        return

    # 5. 启动注册线程（HTTP 模式，需要 Action ID）
    target_count = total
    start_time = time.time()
    stop_event.clear()

    os.makedirs("keys", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"keys/grok_{timestamp}_{target_count}.txt"

    print(f"\n[*] 启动 {threads} 个线程，目标 {target_count} 个账号")
    print(f"[*] 输出文件: {output_file}")
    print("=" * 60)

    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(register_single_thread) for _ in range(threads)]
        try:
            concurrent.futures.wait(futures)
        except KeyboardInterrupt:
            print("\n[!] 收到中断信号，正在停止...")
            stop_event.set()
            concurrent.futures.wait(futures, timeout=30)

    # 6. 二次验证 NSFW
    if os.path.exists(output_file):
        print(f"\n[*] 开始二次验证 NSFW...")
        nsfw_service = NsfwSettingsService()
        with open(output_file, "r") as f:
            tokens = [line.strip() for line in f if line.strip()]
        ok_count = 0
        for sso in tokens:
            try:
                result = nsfw_service.enable_unhinged(sso)
                if result.get("ok"):
                    ok_count += 1
                else:
                    print(f"[-] enable_unhinged 失败: {result.get('error', result)}")
            except Exception as e:
                print(f"[-] enable_unhinged 异常: {e}")
        print(f"[*] 二次验证完成: {ok_count}/{len(tokens)}")

    elapsed = time.time() - start_time
    print(f"\n[*] 完成！共注册 {success_count} 个账号，耗时 {elapsed:.1f}s")
    print(f"[*] 结果保存至: {output_file}")


if __name__ == "__main__":
    main()