"""邮箱服务类 - 适配 moemail API"""
import os
import re
import time
import random
import string
import requests
from dotenv import load_dotenv


class EmailService:
    def __init__(self, api_key=None, base_url=None, domain=None):
        load_dotenv()
        self.api_key = api_key or os.getenv("MOEMAIL_API_KEY", "").strip()
        self.base_url = (base_url or os.getenv("MOEMAIL_BASE_URL", "https://mail.zhouhongbin.top")).rstrip("/")
        self._default_domain = domain or os.getenv("MOEMAIL_DOMAIN", "").strip()
        if not self.api_key:
            raise ValueError("Missing: MOEMAIL_API_KEY (请在 .env 或启动时输入)")
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        self._domain = None  # 缓存域名

    def _get_domain(self):
        """从 /api/config 获取首个可用邮箱域名，结果缓存。
        优先级：API 返回 > 用户配置（MOEMAIL_DOMAIN）> 默认 moemail.app
        """
        if self._domain:
            return self._domain
        try:
            res = requests.get(
                f"{self.base_url}/api/config",
                headers={"X-API-Key": self.api_key},
                timeout=10,
            )
            if res.status_code == 200:
                data = res.json()
                domains = data.get("domains", [])
                if domains:
                    self._domain = domains[0]
                    return self._domain
            else:
                print(f"[-] 获取域名配置失败: {res.status_code} - {res.text[:80]}")
        except Exception as e:
            print(f"[-] 获取域名配置异常: {e}")
        self._domain = self._default_domain or "moemail.app"  # 优先使用用户配置的域名
        return self._domain

    def create_email(self):
        """创建临时邮箱 POST /api/emails/generate
        返回: (email_id, email_address)
        """
        domain = self._get_domain()
        name = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(10))
        try:
            res = requests.post(
                f"{self.base_url}/api/emails/generate",
                headers=self.headers,
                json={"name": name, "expiryTime": 3600000, "domain": domain},
                timeout=10,
            )
            if res.status_code == 200:
                data = res.json()
                email_id = data.get("id")
                # 地址可能在 email / address / name@domain
                email_address = (
                    data.get("email")
                    or data.get("address")
                    or f"{name}@{domain}"
                )
                if not email_id:
                    print(f"[-] 创建邮箱返回缺少 id: {data}")
                    return None, None
                return email_id, email_address
            print(f"[-] 创建邮箱失败: {res.status_code} - {res.text[:120]}")
            return None, None
        except Exception as e:
            print(f"[-] 创建邮箱异常: {e}")
            return None, None

    def fetch_verification_code(self, email_id, max_attempts=30, poll_interval=2):
        """轮询获取验证码
        GET /api/emails/{emailId}  → 邮件列表
        GET /api/emails/{emailId}/{messageId}  → 单封邮件正文
        """
        for attempt in range(max_attempts):
            try:
                res = requests.get(
                    f"{self.base_url}/api/emails/{email_id}",
                    headers={"X-API-Key": self.api_key},
                    timeout=10,
                )
                if res.status_code == 200:
                    data = res.json()
                    # 列表可能在 messages / items / 直接是 list
                    messages = (
                        data.get("messages")
                        or data.get("items")
                        or (data if isinstance(data, list) else [])
                    )
                    if messages:
                        msg_id = messages[0].get("id")
                        if msg_id:
                            code = self._fetch_code_from_message(email_id, msg_id)
                            if code:
                                return code
                elif res.status_code != 404:
                    print(f"[-] 获取邮件列表失败 (attempt {attempt+1}): {res.status_code}")
            except Exception as e:
                print(f"[-] 获取邮件列表异常 (attempt {attempt+1}): {e}")
            time.sleep(poll_interval)
        print(f"[-] 超时未收到验证码 (email_id={email_id})")
        return None

    def _fetch_code_from_message(self, email_id, message_id):
        """GET /api/emails/{emailId}/{messageId} 并提取验证码"""
        try:
            res = requests.get(
                f"{self.base_url}/api/emails/{email_id}/{message_id}",
                headers={"X-API-Key": self.api_key},
                timeout=10,
            )
            if res.status_code == 200:
                data = res.json()
                content = data.get("text") or data.get("html") or data.get("content") or ""
                return self._extract_code(content)
            print(f"[-] 获取单封邮件失败: {res.status_code} - {res.text[:80]}")
        except Exception as e:
            print(f"[-] 获取单封邮件异常: {e}")
        return None

    @staticmethod
    def _extract_code(text):
        """从邮件正文（HTML 或纯文本）中提取 6 位数字验证码"""
        clean = re.sub(r"<[^>]+>", " ", text)
        match = re.search(r"\b(\d{6})\b", clean)
        return match.group(1) if match else None

    def delete_email(self, email_id):
        """删除邮箱 DELETE /api/emails/{emailId}"""
        if not email_id:
            return False
        try:
            res = requests.delete(
                f"{self.base_url}/api/emails/{email_id}",
                headers={"X-API-Key": self.api_key},
                timeout=10,
            )
            if res.status_code in (200, 204):
                return True
            print(f"[-] 删除邮箱失败: {res.status_code} - {res.text[:80]}")
            return False
        except Exception as e:
            print(f"[-] 删除邮箱异常: {e}")
            return False
