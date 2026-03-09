"""
基于浏览器的 Grok 注册模块（参考 jiang068/grok_reg 项目）。

使用 camoufox 浏览器自动化完成注册流程，无需提取 Next.js Action ID。
适用于 accounts.x.ai 页面结构变化导致 Action ID 无法提取的场景。
"""
import asyncio
import random
import re
import secrets
from typing import Dict, Optional, Tuple

from .email_service import EmailService

SIGNUP_URL = "https://accounts.x.ai/sign-up"

_FIRST_NAMES = [
    "Liam", "Noah", "Oliver", "Elijah", "James", "William", "Benjamin",
    "Lucas", "Henry", "Alexander", "Olivia", "Emma", "Ava", "Charlotte",
    "Sophia", "Amelia", "Isabella", "Mia", "Evelyn", "Harper",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson",
    "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
]


def _generate_name() -> Tuple[str, str]:
    return random.choice(_FIRST_NAMES), random.choice(_LAST_NAMES)


def _is_cf_page(content: str, url: str) -> bool:
    cl = content.lower()
    has_cf = "cloudflare" in cl or "cf-chl" in url or "challenge" in url
    has_challenge = (
        "just a moment" in cl
        or "checking your browser" in cl
        or "please wait" in cl
        or "cf-challenge" in cl
        or "cf_chl" in cl
        or "/cdn-cgi/challenge-platform" in cl
    )
    if "cf-chl" in url or ("/cdn-cgi/" in url and "challenge" in url):
        return True
    return has_cf and has_challenge


async def _wait_for_cf(
    page, timeout: float = 30.0, poll: float = 1.5, debug: bool = False
) -> bool:
    """等待 Cloudflare 挑战自动通过"""
    try:
        content = await page.content()
        url = page.url
        if not _is_cf_page(content, url):
            return True
        if debug:
            print(f"[Browser] 检测到 Cloudflare，等待自动通过（最多 {timeout:.0f}s）...")
        elapsed = 0.0
        while elapsed < timeout:
            await asyncio.sleep(poll)
            elapsed += poll
            try:
                content = await page.content()
                url = page.url
                if not _is_cf_page(content, url):
                    if debug:
                        print(f"[Browser] Cloudflare 已通过（{elapsed:.1f}s）")
                    return True
            except Exception:
                pass
        if debug:
            print(f"[Browser] Cloudflare 等待超时（{timeout:.0f}s）")
        return False
    except Exception:
        return True


async def _extract_token(context, page, debug: bool = False) -> Dict[str, str]:
    """从 cookies、localStorage 和页面内容提取 SSO token"""
    result: Dict[str, str] = {"sso": "", "sso-rw": ""}
    try:
        cookies = await context.cookies()
        for c in cookies:
            name = c.get("name", "").lower()
            val = c.get("value", "")
            if name == "sso" and val and not result["sso"]:
                result["sso"] = val
            if (name == "sso-rw" or name == "sso_rw") and val and not result["sso-rw"]:
                result["sso-rw"] = val
    except Exception:
        pass
    try:
        local = await page.evaluate(
            "() => Object.fromEntries(Object.entries(window.localStorage))"
        )
        for k, v in local.items():
            kl = k.lower()
            if "sso" in kl and not result["sso"] and isinstance(v, str):
                result["sso"] = v
            if ("sso-rw" in kl or "sso_rw" in kl) and not result["sso-rw"] and isinstance(v, str):
                result["sso-rw"] = v
    except Exception:
        pass
    try:
        content = await page.content()
        m = re.search(r'"sso"\s*:\s*"([^"]{8,})"', content)
        if m and not result["sso"]:
            result["sso"] = m.group(1)
    except Exception:
        pass
    if debug:
        has_sso = bool(result["sso"])
        has_rw = bool(result["sso-rw"])
        print(f"[Browser] token 提取: sso={'已获取' if has_sso else '未找到'}, sso-rw={'已获取' if has_rw else '未找到'}")
    return result


async def _fill_email_password(page, email: str, password: str) -> bool:
    """填写邮箱和密码字段，返回是否成功填入邮箱"""
    filled = False
    for sel in ['input[type="email"]', 'input[name="email"]', 'input[id*="email"]']:
        try:
            el = page.locator(sel)
            if await el.count() > 0:
                await el.first.fill(email)
                filled = True
                break
        except Exception:
            pass
    if not filled:
        try:
            idx = await page.evaluate("""
                () => {
                    const inputs = Array.from(document.querySelectorAll('input'));
                    for (let i = 0; i < inputs.length; i++) {
                        const t = inputs[i];
                        const attrs = (t.name||'') + ' ' + (t.id||'') + ' ' + (t.placeholder||'') + ' ' + (t.type||'');
                        if (/mail|email/i.test(attrs) || t.type === 'email') return i;
                    }
                    return -1;
                }
            """)
            if isinstance(idx, int) and idx >= 0:
                inp = page.locator("input").nth(idx)
                if await inp.count() > 0:
                    await inp.fill(email)
                    filled = True
        except Exception:
            pass
    for ps in ['input[type="password"]', 'input[name="password"]', 'input[id*="password"]']:
        try:
            el = page.locator(ps)
            if await el.count() > 0:
                await el.first.fill(password)
                break
        except Exception:
            pass
    return filled


async def _fill_verification(
    page,
    email_service: EmailService,
    email_id: str,
    max_attempts: int = 60,
    debug: bool = False,
) -> bool:
    """每秒轮询邮箱一次，获取到验证码后填入页面，最多等待 max_attempts 秒"""
    loop = asyncio.get_event_loop()

    def _fetch_once() -> Optional[str]:
        return email_service.fetch_verification_code(email_id, max_attempts=1, poll_interval=0)

    for _ in range(max_attempts):
        try:
            code = await loop.run_in_executor(None, _fetch_once)
        except asyncio.CancelledError:
            return False
        if code:
            if debug:
                print(f"[Browser] 获取验证码: {code}")
            for sel in [
                'input[name="code"]',
                'input[id*="code"]',
                'input[placeholder*="code"]',
            ]:
                try:
                    inp = page.locator(sel)
                    if await inp.count() > 0:
                        await inp.first.fill(code)
                        await page.keyboard.press("Enter")
                        return True
                except Exception:
                    pass
            # OTP 风格：一格一字符
            digits = page.locator("input")
            cnt = await digits.count()
            if cnt > 0:
                for j in range(min(len(code), cnt)):
                    try:
                        await digits.nth(j).fill(code[j])
                    except Exception:
                        pass
                return True
        await asyncio.sleep(1)
    if debug:
        print(f"[Browser] 验证码获取超时（{max_attempts}s）")
    return False


async def register_one(
    email_service: EmailService,
    proxy: Optional[str] = None,
    debug: bool = False,
) -> Optional[Dict[str, str]]:
    """
    使用 camoufox 浏览器自动完成 Grok 账号注册。

    参考 jiang068/grok_reg 项目的浏览器自动化方案，不依赖 Next.js Action ID。

    Args:
        email_service: 临时邮箱服务实例（moemail）
        proxy: 代理地址（如 http://127.0.0.1:10808），可选
        debug: 是否输出调试信息

    Returns:
        成功时返回 {"sso": "...", "sso-rw": "..."}，失败返回 None
    """
    # camoufox is an optional dependency — import is deferred so that the rest
    # of the module loads normally even when the package is not installed.
    try:
        from camoufox.async_api import AsyncCamoufox  # type: ignore
    except ImportError:
        print("[-] 缺少 camoufox 依赖，请运行: pip install camoufox && python -m camoufox fetch")
        return None

    email_id: Optional[str] = None
    email_address: Optional[str] = None
    try:
        email_id, email_address = email_service.create_email()
    except Exception as e:
        print(f"[-] 创建邮箱失败: {e}")
        return None

    if not email_address or not email_id:
        print("[-] 邮箱服务返回空值，跳过")
        return None

    # Use a cryptographically random suffix for the password to avoid predictable patterns.
    password = f"Xai{secrets.token_urlsafe(8)}A1!"
    first_name, last_name = _generate_name()

    if debug:
        print(f"[Browser] 使用邮箱: {email_address}")

    launch_opts: dict = {"headless": True}
    if proxy:
        launch_opts["proxy"] = {"server": proxy}

    cam = AsyncCamoufox(**launch_opts)
    try:
        browser = await cam.__aenter__()
        context = await browser.new_context()
        page = await context.new_page()

        if debug:
            print(f"[Browser] 导航到: {SIGNUP_URL}")
        await page.goto(SIGNUP_URL, wait_until="domcontentloaded", timeout=60000)
        await _wait_for_cf(page, debug=debug)

        # 点击 Sign up with email 按钮（如果有）
        for sel in [
            'button:has-text("Sign up with email")',
            'button:has-text("Sign up with Email")',
            'a[href*="/sign-up"]',
            'button:has-text("Sign up")',
        ]:
            try:
                el = page.locator(sel)
                if await el.count() > 0:
                    await el.first.click()
                    await asyncio.sleep(0.5)
                    break
            except Exception:
                pass

        # 填入邮箱和密码
        filled = await _fill_email_password(page, email_address, password)
        if not filled and debug:
            print("[Browser] 未能填入邮箱字段，尝试继续")

        # 触发发送验证码
        for btn_sel in [
            'button:has-text("Send code")',
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button[type="submit"]',
        ]:
            try:
                btn = page.locator(btn_sel)
                if await btn.count() > 0:
                    await btn.first.click()
                    await asyncio.sleep(0.5)
                    break
            except Exception:
                pass

        # 等待验证码输入框出现
        try:
            await page.wait_for_selector(
                'input[name="code"], input[id*="code"], input[placeholder*="code"]',
                timeout=30000,
            )
        except Exception:
            pass

        # 填入验证码
        await _fill_verification(page, email_service, email_id, debug=debug)

        # 填写姓名
        for name_sel, val in [
            ('input[name="givenName"]', first_name),
            ('input[placeholder*="First"]', first_name),
            ('input[aria-label*="First"]', first_name),
            ('input[name="familyName"]', last_name),
            ('input[placeholder*="Last"]', last_name),
            ('input[aria-label*="Last"]', last_name),
        ]:
            try:
                el = page.locator(name_sel)
                if await el.count() > 0:
                    await el.first.fill(val)
            except Exception:
                pass

        # 填写密码（如有单独步骤）
        for ps in ['input[name="password"]', 'input[type="password"]']:
            try:
                el = page.locator(ps)
                if await el.count() > 0:
                    await el.first.fill(password)
                    break
            except Exception:
                pass

        # 提交注册
        for btn_sel in [
            'button:has-text("Complete sign up")',
            'button:has-text("Complete signup")',
            'button:has-text("Complete")',
            'button[type="submit"]',
            'button:has-text("Next")',
        ]:
            try:
                btn = page.locator(btn_sel)
                if await btn.count() > 0:
                    txt = ""
                    try:
                        txt = (await btn.first.inner_text()).strip().lower()
                    except Exception:
                        pass
                    if "back" in txt:
                        continue
                    await btn.first.click()
                    break
            except Exception:
                pass

        await _wait_for_cf(page, debug=debug)
        # Wait for post-CF redirect and page settling before extracting tokens.
        await asyncio.sleep(3)

        # 处理 TOS 页面
        try:
            await page.wait_for_url("*accept-tos*", timeout=20000)
            if debug:
                print(f"[Browser] 进入 TOS 页面: {page.url}")
            checkboxes = page.locator('button[role="checkbox"]')
            count = await checkboxes.count()
            for i in range(count):
                try:
                    cb = checkboxes.nth(i)
                    state = await cb.get_attribute("data-state")
                    if state != "checked":
                        await cb.click()
                        await asyncio.sleep(0.3)
                except Exception:
                    pass
            for btn_sel in [
                'button:has-text("Continue")',
                'button:has-text("Accept")',
                'button[type="submit"]',
            ]:
                try:
                    btn = page.locator(btn_sel)
                    if await btn.count() > 0:
                        await btn.first.click()
                        break
                except Exception:
                    pass
        except Exception:
            pass

        # Allow the final redirect and cookie-setting to complete before extraction.
        await asyncio.sleep(5)
        tokens = await _extract_token(context, page, debug=debug)
        return tokens if tokens.get("sso") else None

    except Exception as e:
        print(f"[-] 浏览器注册异常: {e}")
        return None
    finally:
        try:
            await cam.__aexit__(None, None, None)
        except Exception:
            pass
        if email_id:
            try:
                email_service.delete_email(email_id)
            except Exception:
                pass
