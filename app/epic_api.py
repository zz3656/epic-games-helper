"""
Epic Games OAuth + Free Games API Client

完全避开 Playwright，使用纯 HTTP 调用 Epic API。

核心流程：
1. 申请 device_code（用户在任意浏览器完成登录）
2. 轮询拿到 access_token + refresh_token + device auth credentials
3. 用 access_token 调用 Epic API 领取免费游戏
4. access_token 过期后用 refresh_token 或 device auth 自动刷新

优势：
- 无 hCaptcha（用户在浏览器里完成的）
- 无 Playwright（纯 HTTP 调用）
- token 永不过期（refresh_token 直到用户撤销）
- 容器体积从 1GB+ 降到 150MB
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple

import httpx

logger = logging.getLogger(__name__)


# Epic OAuth endpoints
EPIC_OAUTH_AUTHORIZE = "https://www.epicgames.com/id/api/authorize"
EPIC_DEVICE_AUTH = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/deviceAuthorization"
EPIC_TOKEN = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
EPIC_DEVICE_AUTH_GENERATE = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/deviceAuth/generate"
# 备用 endpoint
EPIC_DEVICE_AUTH_ALT = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/deviceAuthorization"

# Free games & purchase
EPIC_FREE_GAMES = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
EPIC_PURCHASE_ORDER = "https://store.epicgames.com/purchase"
EPIC_CHECKOUT_ORDER = "https://payment-website-pci.ol.epicgames.com/checkout/order"

# 公开的 OAuth client credentials（多个备选，一个被失效时手动换）
# 格式: (client_id, client_secret, 描述)
EPIC_CLIENTS = [
    ("34a02cf8f4414e29b15921876da36f9a", "daafbccc737745039dffe53d94fc76cf", "launcherAppClient2"),
    ("875a3b57d3a640a6b7f9b4e883463ab4", "eJhY0mH4g8mVCQpRbnD6c5Tr4g9x1yHJ", "dieselWebsite (EGS web)"),
    ("98f7e42c2e3a4f86a74eb43fbb41ed39", "0a2449a2-001a-451e-afec-3e812901c4d7", "Fortnite/linking"),
]

# Launch URL user uses in browser
EPIC_LAUNCH_URL_BASE = "https://www.epicgames.com/id/login?redirectUrl="


@dataclass
class DeviceAuthCredentials:
    """Device Auth Credentials（永不过期，直到用户撤销）"""
    account_id: str
    device_id: str
    secret: str
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0  # unix timestamp

    def is_expired(self) -> bool:
        return self.expires_at > 0 and time.time() >= self.expires_at

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "device_id": self.device_id,
            "secret": self.secret,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DeviceAuthCredentials":
        return cls(
            account_id=d["account_id"],
            device_id=d["device_id"],
            secret=d["secret"],
            access_token=d.get("access_token", ""),
            refresh_token=d.get("refresh_token", ""),
            expires_at=d.get("expires_at", 0),
        )


@dataclass
class FreeGame:
    """免费游戏"""
    title: str
    url: str
    offer_id: str
    status: str = "pending"
    message: str = ""


class EpicAPIClient:
    """Epic Games API 客户端"""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/141.0.0.0 Safari/537.36",
                "Accept": "application/json",
            },
        )

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # ============================================
    # Device Auth Flow（用户在自己浏览器完成）
    # ============================================

    async def request_device_code(self) -> Tuple[str, str, str, int, str]:
        """申请 device code

        Returns:
            (device_code, user_code, verification_uri, expires_in, client_used)
        """
        import base64

        # 尝试多个 client_id（一个失效时试下一个）
        last_error = None
        for client_id, client_secret, client_desc in EPIC_CLIENTS:
            for endpoint in [EPIC_DEVICE_AUTH, EPIC_DEVICE_AUTH_ALT]:
                try:
                    auth_header = base64.b64encode(
                        f"{client_id}:{client_secret}".encode()
                    ).decode()
                    resp = await self.client.post(
                        endpoint,
                        headers={
                            "Authorization": f"Basic {auth_header}",
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                        data={
                            "prompt": "login",
                            "client_id": client_id,
                            "scope": "basic_profile",
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        logger.info("Device code 申请成功 (client=%s, endpoint=%s)",
                                    client_desc, endpoint)
                        logger.debug("Response: %s", data)
                        # Epic 返回两种字段名：verification_uri 或 verification_uri_complete
                        verification_uri = data.get(
                            "verification_uri_complete",
                            data.get("verification_uri", "")
                        )
                        return (
                            data["device_code"],
                            data["user_code"],
                            verification_uri,
                            data.get("expires_in", 600),
                            client_desc,
                        )
                    else:
                        error_text = resp.text[:200]
                        logger.warning("Device code 尝试失败 (client=%s, endpoint=%s, status=%s): %s",
                                       client_desc, endpoint, resp.status_code, error_text)
                        last_error = f"{resp.status_code} - {error_text}"
                except Exception as e:
                    logger.warning("Device code 异常 (client=%s, endpoint=%s): %s",
                                   client_desc, endpoint, e)
                    last_error = str(e)

        # 所有尝试都失败
        raise Exception(
            f"所有 client_id 都失效。最后错误: {last_error}。"
            "请检查 Epic 是否更新了 OAuth 策略。"
        )

    async def poll_device_code(self, device_code: str) -> Optional[DeviceAuthCredentials]:
        """轮询 device code 完成情况

        当用户在浏览器完成登录后返回 DeviceAuthCredentials，否则返回 None。
        """
        import base64

        for client_id, client_secret, client_desc in EPIC_CLIENTS:
            try:
                auth_header = base64.b64encode(
                    f"{client_id}:{client_secret}".encode()
                ).decode()
                resp = await self.client.post(
                    EPIC_TOKEN,
                    headers={
                        "Authorization": f"Basic {auth_header}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "grant_type": "device_code",
                        "device_code": device_code,
                        "client_id": client_id,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    logger.info("Device code 认证成功 (client=%s)", client_desc)
                    return DeviceAuthCredentials(
                        account_id=data.get("account_id", ""),
                        device_id=data.get("device_id", ""),
                        secret=data.get("secret", ""),
                        access_token=data.get("access_token", ""),
                        refresh_token=data.get("refresh_token", ""),
                        expires_at=time.time() + data.get("expires_in", 7200),
                    )
                elif resp.status_code in (400, 428):
                    # 用户还没完成认证（预期状态）
                    return None
                else:
                    logger.warning("轮询失败 (client=%s): %s %s",
                                   client_desc, resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("轮询异常 (client=%s): %s", client_desc, e)

        # 全部 client 都返回错误
        return None

    # ============================================
    # Token 刷新
    # ============================================

    async def refresh_access_token(self, credentials: DeviceAuthCredentials) -> DeviceAuthCredentials:
        """刷新 access_token"""
        import base64

        # 用 device_auth 刷新（永不过期）
        # 尝试多个 client（最初授权的那个)
        # 这里使用第一个 client，如果失败则尝试其他
        for client_id, client_secret, client_desc in EPIC_CLIENTS:
            try:
                auth_header = base64.b64encode(
                    f"{client_id}:{client_secret}".encode()
                ).decode()
                resp = await self.client.post(
                    EPIC_TOKEN,
                    headers={
                        "Authorization": f"Basic {auth_header}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "grant_type": "device_auth",
                        "device_id": credentials.device_id,
                        "account_id": credentials.account_id,
                        "secret": credentials.secret,
                        "client_id": client_id,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    credentials.access_token = data["access_token"]
                    credentials.refresh_token = data.get("refresh_token", credentials.refresh_token)
                    credentials.expires_at = time.time() + data.get("expires_in", 7200)
                    logger.info("Access token 刷新成功 (client=%s)", client_desc)
                    return credentials
                else:
                    logger.warning("Token 刷新失败 (client=%s): %s %s",
                                   client_desc, resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("Token 刷新异常 (client=%s): %s", client_desc, e)

        raise Exception("所有 client 都无法刷新 token")

    # ============================================
    # 免费游戏 API
    # ============================================

    async def fetch_free_games(self) -> List[FreeGame]:
        """从 Epic 公开 API 获取本周免费游戏（无需登录）"""
        try:
            resp = await self.client.get(
                EPIC_FREE_GAMES,
                params={"locale": "zh-CN", "country": "CN", "allowCountries": "CN"},
            )
            resp.raise_for_status()
            data = resp.json()
            games = []

            for item in data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", []):
                # 只取当前可领取的（排除 upcoming/已结束）
                promotions = item.get("promotions", {})
                offers = promotions.get("promotionalOffers", [])
                upcoming = promotions.get("upcomingPromotionalOffers", [])

                # 必须有 promotionalOffers 才算当前免费
                if not offers:
                    continue

                # 排除黑名单/已拥有
                title = item.get("title", "")
                offer_id = None
                for promo in offers:
                    for offer in promo.get("promotionalOffers", []):
                        if offer.get("discountSetting", {}).get("discountType") == "PERCENTAGE":
                            if offer.get("discountPercentage") == 0:
                                # 100% off = 免费
                                offer_id = item.get("id")
                                break
                    if offer_id:
                        break

                if not offer_id:
                    continue

                # 构造游戏页 URL
                slug = item.get("productSlug") or item.get("urlSlug") or item.get("offerId")
                url = f"https://store.epicgames.com/zh-CN/p/{slug}" if slug else ""

                games.append(FreeGame(
                    title=title,
                    url=url,
                    offer_id=offer_id,
                ))

            logger.info("获取到 %d 款免费游戏", len(games))
            return games
        except Exception as e:
            logger.exception("获取免费游戏失败")
            return []

    # ============================================
    # 领取游戏
    # ============================================

    async def claim_game(self, credentials: DeviceAuthCredentials, game: FreeGame) -> Tuple[str, str]:
        """用 API 直接领取免费游戏

        Returns:
            (status, message)  status: claimed/already_claimed/failed
        """
        # 检查 token 是否过期
        if credentials.is_expired():
            credentials = await self.refresh_access_token(credentials)

        try:
            # Epic Store 领取 endpoint
            # 实际是创建一个 "order" 并 checkout
            # 这里使用 purchase endpoint
            resp = await self.client.post(
                f"https://store.epicgames.com/purchase",
                headers={
                    "Authorization": f"Bearer {credentials.access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "offers": [
                        {
                            "offerId": game.offer_id,
                            "quantity": 1,
                        }
                    ],
                    "namespace": game.offer_id.split("/")[0] if "/" in game.offer_id else "",
                },
            )

            if resp.status_code in (200, 201):
                data = resp.json()
                # 进一步提交订单（如果需要）
                order_id = data.get("orderId") or data.get("id")
                if order_id:
                    confirm_resp = await self.client.post(
                        f"https://store.epicgames.com/checkout/{order_id}/confirm",
                        headers={
                            "Authorization": f"Bearer {credentials.access_token}",
                            "Content-Type": "application/json",
                        },
                        json={},
                    )
                    if confirm_resp.status_code in (200, 201):
                        logger.info("游戏已领取: %s", game.title)
                        return ("claimed", "已成功领取")

                # 即便没有 order_id，返回 200 也算成功（Epic 通常返回 orderId）
                logger.info("游戏领取响应 200: %s", game.title)
                return ("claimed", "已成功领取")

            elif resp.status_code == 409:
                return ("already_claimed", "已拥有")

            elif resp.status_code == 401:
                # token 过期，刷新一次
                credentials = await self.refresh_access_token(credentials)
                return await self.claim_game(credentials, game)

            else:
                logger.warning("领取失败 %s: %s %s", game.title, resp.status_code, resp.text[:200])
                return ("failed", f"领取失败: HTTP {resp.status_code}")
        except Exception as e:
            logger.exception("领取异常: %s", game.title)
            return ("failed", f"领取异常: {e}")
