"""FlareSolverr 服务 - 用于绕过 Cloudflare 检测，获取 cf_clearance cookie"""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()


class FlareSolverrService:
    """通过本地 FlareSolverr 实例获取 Cloudflare cf_clearance cookie。

    FlareSolverr 需独立运行（Docker 或直接安装），默认监听 http://localhost:8191。
    配置项（.env 或启动时传入）：
      FLARESOLVERR_URL              - FlareSolverr 地址，默认 http://localhost:8191
      FLARESOLVERR_REFRESH_INTERVAL - cf_clearance 刷新间隔（秒），默认 600
      FLARESOLVERR_TIMEOUT          - 单次请求超时（秒），默认 60
    """

    def __init__(self, url=None, refresh_interval=None, timeout=None):
        self.url = (url or os.getenv("FLARESOLVERR_URL", "http://localhost:8191")).rstrip("/")
        self.refresh_interval = int(
            refresh_interval or os.getenv("FLARESOLVERR_REFRESH_INTERVAL", 600)
        )
        self.timeout = int(timeout or os.getenv("FLARESOLVERR_TIMEOUT", 60))

        # 缓存结构: { target_url: {"cf_clearance": str, "user_agent": str, "expires_at": float} }
        self._cache: dict = {}

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def get_clearance(self, target_url: str) -> dict:
        """返回 {"cf_clearance": str, "user_agent": str}，优先使用缓存。

        若 FlareSolverr 不可用或请求失败，返回空字典（不抛异常，调用方决定是否继续）。
        """
        cached = self._cache.get(target_url)
        if cached and time.time() < cached["expires_at"]:
            return {"cf_clearance": cached["cf_clearance"], "user_agent": cached["user_agent"]}

        return self._refresh(target_url)

    def is_available(self) -> bool:
        """检查 FlareSolverr 是否在线"""
        try:
            res = requests.get(f"{self.url}/", timeout=5)
            return res.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _refresh(self, target_url: str) -> dict:
        """向 FlareSolverr 发起请求，刷新 cf_clearance"""
        try:
            payload = {
                "cmd": "request.get",
                "url": target_url,
                "maxTimeout": self.timeout * 1000,  # FlareSolverr expects milliseconds
            }
            res = requests.post(
                f"{self.url}/v1",
                json=payload,
                timeout=self.timeout + 10,
            )
            if res.status_code != 200:
                print(f"[-] FlareSolverr 请求失败: {res.status_code} - {res.text[:120]}")
                return {}

            data = res.json()
            if data.get("status") != "ok":
                print(f"[-] FlareSolverr 返回错误: {data.get('message', data)}")
                return {}

            solution = data.get("solution", {})
            cookies = {c["name"]: c["value"] for c in solution.get("cookies", [])}
            cf_clearance = cookies.get("cf_clearance", "")
            user_agent = solution.get("userAgent", "")

            if cf_clearance:
                self._cache[target_url] = {
                    "cf_clearance": cf_clearance,
                    "user_agent": user_agent,
                    "expires_at": time.time() + self.refresh_interval,
                }
                print(f"[+] FlareSolverr 获取 cf_clearance 成功 ({target_url})")
                return {"cf_clearance": cf_clearance, "user_agent": user_agent}

            print(f"[-] FlareSolverr 响应中未找到 cf_clearance cookie")
            return {}

        except requests.exceptions.ConnectionError:
            print(f"[-] FlareSolverr 连接失败，请确认服务已启动: {self.url}")
            return {}
        except Exception as e:
            print(f"[-] FlareSolverr 异常: {e}")
            return {}
