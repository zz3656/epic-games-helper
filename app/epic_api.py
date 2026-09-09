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
EPIC_PURCHASE_ORDER = "https://www.epicgames.com/store/purchase"
EPIC_CHECKOUT_ORDER = "https://payment-website-pci.ol.epicgames.com/purchase/confirm-order"

# User entitlements (查询用户已拥有的游戏)
EPIC_ENTITLEMENTS_HOST = "entitlement-public-service-prod08.ol.epicgames.com"
EPIC_CATALOG_HOST = "catalog-public-service-prod06.ol.epicgames.com"
EPIC_ENTITLEMENTS_URL = f"https://{EPIC_ENTITLEMENTS_HOST}/entitlement/api/account/{{account_id}}/entitlements"
EPIC_CATALOG_BULK_URL = f"https://{EPIC_CATALOG_HOST}/catalog/api/shared/namespace/{{namespace}}/bulk/items"

# 游戏封面图片
EPIC_IMAGE_BASE = "https://cdn1.epicgames.com/offer"

# OAuth client credentials
# 参考 MixV2/EpicResearch 官方文档推荐的 fortnitePCGameClient
# 以及 claabs/epicgames-freegames-node 使用的 fortniteNewSwitchGameClient
EPIC_CLIENTS = [
    # (client_id, client_secret, name)
    ("ec684b8c687f479fadea3cb2ad83f5c6", "e1f31c211f28413186262d37a13fc84d", "fortnitePCGameClient"),
    ("98f7e42c2e3a4f86a74eb43fbb41ed39", "0a2449a2-001a-451e-afec-3e812901c4d7", "fortniteNewSwitchGameClient"),
    ("34a02cf8f4414e29b15921876da36f9a", "daafbccc737745039dffe53d94fc76cf", "launcherAppClient2"),
    ("875a3b57d3a640a6b7f9b4e883463ab4", "eJhY0mH4g8mVCQpRbnD6c5Tr4g9x1yHJ", "dieselWebsite"),
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
    image_url: str = ""          # 游戏封面 URL
    description: str = ""        # 游戏描述
    namespace: str = ""          # Epic namespace
    already_owned: bool = False  # 用户是否已拥有该游戏
    checkout_url: str = ""       # 领取链接 (如未领取)
    start_date: str = ""         # 免费开始日期
    end_date: str = ""           # 免费结束日期
    original_price: str = ""     # 原价


class EpicAPIClient:
    """Epic Games API 客户端"""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,  # 允许跟随 302 重定向（Epic 购买接口会返回 302）
            headers={
                # 关键：使用 Epic 官方 launcher 的 User-Agent
                # 否则 OAuth endpoint 会返回 401
                "User-Agent": "UELauncher/11.0.1-14907503+++Portal+Release-Live Windows/10.0.19041.1.256.64bit",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
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
    #
    # 严格遵循 MixV2/EpicResearch + claabs 的两步走流程：
    # 1. 用 client_credentials grant type 拿一个 access_token
    # 2. 用该 token 作为 Bearer 去申请 device_code
    # ============================================

    async def _get_client_credentials_token(self, client_id: str, client_secret: str) -> str:
        """第一步：用 client_credentials 获取临时 access_token"""
        import base64

        auth_header = base64.b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()

        for endpoint in [EPIC_TOKEN, "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/token"]:
            try:
                resp = await self.client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Basic {auth_header}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "grant_type": "client_credentials",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    logger.info("client_credentials token 获取成功 (expires_in=%s)", data.get("expires_in"))
                    return data["access_token"]
                else:
                    logger.warning("client_credentials endpoint=%s 失败: %s - %s",
                                   endpoint, resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("client_credentials endpoint=%s 异常: %s", endpoint, e)
        raise Exception("client_credentials 失败（所有 endpoint 都未成功）")

    async def request_device_code(self) -> Tuple[str, str, str, int, str]:
        """申请 device code

        Returns:
            (device_code, user_code, verification_uri, expires_in, client_used)
        """
        import base64

        # 尝试多个 client
        last_error = None
        for client_id, client_secret, client_name in EPIC_CLIENTS:
            try:
                # 第一步：获取 client_credentials token
                bearer_token = await self._get_client_credentials_token(client_id, client_secret)

                # 第二步：用 bearer token 申请 device_code
                for endpoint in [EPIC_DEVICE_AUTH, EPIC_DEVICE_AUTH_ALT]:
                    try:
                        resp = await self.client.post(
                            endpoint,
                            params={"prompt": "login"},
                            headers={
                                "Authorization": f"Bearer {bearer_token}",
                            },
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            logger.info("Device code 申请成功 (client=%s, endpoint=%s)",
                                        client_name, endpoint)
                            verification_uri = data.get(
                                "verification_uri_complete",
                                data.get("verification_uri", "")
                            )
                            return (
                                data["device_code"],
                                data["user_code"],
                                verification_uri,
                                data.get("expires_in", 600),
                                client_name,
                            )
                        else:
                            logger.warning("Device code client=%s endpoint=%s 失败: %s - %s",
                                           client_name, endpoint, resp.status_code, resp.text[:200])
                            last_error = f"{resp.status_code} - {resp.text[:200]}"
                    except Exception as e:
                        logger.warning("Device code endpoint=%s 异常: %s", endpoint, e)
                        last_error = str(e)
            except Exception as e:
                logger.warning("client=%s 全流程失败: %s", client_name, e)
                last_error = str(e)

        raise Exception(f"所有 client 都失败。最后错误: {last_error}")

    async def poll_device_code(self, device_code: str) -> Optional[DeviceAuthCredentials]:
        """轮询 device code 完成情况

        当用户在浏览器完成登录后返回 DeviceAuthCredentials，否则返回 None。
        """
        import base64

        # 尝试多个 client
        for client_id, client_secret, client_name in EPIC_CLIENTS:
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
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    logger.info("Device code 认证成功 (client=%s)", client_name)
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
                    continue
                else:
                    logger.warning("轮询失败 client=%s: %s - %s",
                                   client_name, resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("轮询异常 client=%s: %s", client_name, e)

        # 全部失败
        return None

    # ============================================
    # Token 刷新
    # ============================================

    async def refresh_access_token(self, credentials: DeviceAuthCredentials) -> DeviceAuthCredentials:
        """刷新 access_token（用 refresh_token 刷新，不需要重新授权）"""
        import base64

        # 尝试多个 client
        for client_id, client_secret, client_name in EPIC_CLIENTS:
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
                        "grant_type": "refresh_token",
                        "refresh_token": credentials.refresh_token,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    credentials.access_token = data["access_token"]
                    credentials.refresh_token = data.get("refresh_token", credentials.refresh_token)
                    credentials.expires_at = time.time() + data.get("expires_in", 7200)
                    logger.info("Access token 刷新成功 (client=%s)", client_name)
                    return credentials
                else:
                    logger.warning("Token 刷新 client=%s 失败: %s - %s",
                                   client_name, resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("Token 刷新 client=%s 异常: %s", client_name, e)

        raise Exception("所有 client 都无法刷新 token")

    # ============================================
    # 免费游戏 API
    # ============================================

    async def fetch_free_games(self) -> List[FreeGame]:
        """从 Epic 公开 API 获取本周免费游戏（无需登录）

        筛选策略：
        - 检查 promotionalOffers 中是否所有包含的游戏都打折到 0%（100% 免费）
        - 跳过只有 upcomingPromotionalOffers 的游戏（这些是下周才免费）
        - 跳过有 totalPrice > 0 的游戏（不是完全免费）
        """
        try:
            resp = await self.client.get(
                EPIC_FREE_GAMES,
                params={"locale": "zh-CN", "country": "CN", "allowCountries": "CN"},
            )
            resp.raise_for_status()
            data = resp.json()
            games = []

            for item in data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", []):
                # 快速过滤: 必须有 promotionalOffers
                promotions = item.get("promotions") or {}
                offers = promotions.get("promotionalOffers") or []
                if not offers:
                    continue

                # 检查 promotionalOffers 内的所有 offer 都打折到 0%
                has_full_free = False
                start_date = ""
                end_date = ""
                for promo_group in offers:
                    for offer in promo_group.get("promotionalOffers", []):
                        ds = offer.get("discountSetting") or {}
                        if ds.get("discountType") == "PERCENTAGE" and ds.get("discountPercentage") == 0:
                            has_full_free = True
                            start_date = offer.get("startDate", "")
                            end_date = offer.get("endDate", "")
                            break
                    if has_full_free:
                        break

                if not has_full_free:
                    continue

                # 双检: 实际价格必须为 0
                price = item.get("price", {}).get("totalPrice", {})
                if price.get("discountPrice", 0) != 0:
                    # 如果 有 promo 但不是 0，跳过
                    continue

                # 双检: namespace.id 格式的 offer_id
                offer_id = item.get("id", "")
                if not offer_id or "/" not in offer_id:
                    # 有时 offerId 不在 id 字段
                    offer_id = item.get("offerId") or offer_id

                namespace = offer_id.split("/")[0] if "/" in offer_id else ""

                title = item.get("title", "Unknown")
                slug = item.get("productSlug") or item.get("urlSlug") or offer_id.split("/")[-1]
                url = f"https://store.epicgames.com/zh-CN/p/{slug}" if slug else ""

                # 获取封面图
                image_url = ""
                key_images = item.get("keyImages") or []
                for img in key_images:
                    if img.get("type") in ("Thumbnail", "DieselStoreFrontWide", "OfferImageWide", "VaultClosed"):
                        image_url = img.get("url", "")
                        if img.get("type") == "Thumbnail":
                            break
                if not image_url and key_images:
                    image_url = key_images[0].get("url", "")

                # 获取描述
                description = item.get("description", "") or item.get("shortDescription", "")

                # 获取原价
                original_price = ""
                fmt_price = price.get("fmtPrice", {})
                original_price = fmt_price.get("originalPrice", "")

                games.append(FreeGame(
                    title=title,
                    url=url,
                    offer_id=offer_id,
                    image_url=image_url,
                    description=description,
                    namespace=namespace,
                    start_date=start_date,
                    end_date=end_date,
                    original_price=original_price,
                ))

            logger.info("获取到 %d 款免费游戏", len(games))
            return games
        except Exception as e:
            logger.exception("获取免费游戏失败")
            return []

    # ============================================
    # XSRF Token
    # ============================================

    async def _get_xsrf_token(self, credentials: DeviceAuthCredentials) -> Optional[str]:
        """获取 XSRF token（Epic 购买接口需要）

        通过 GET /store 页面获取 cookie 中的 XSRF-TOKEN。
        如果失败则返回 None（部分请求可能不需要）。
        """
        try:
            resp = await self.client.get(
                "https://www.epicgames.com/store",
                headers={
                    "Authorization": f"Bearer {credentials.access_token}",
                },
            )
            # 从 cookies 中提取 XSRF-TOKEN
            xsrf = self.client.cookies.get("XSRF-TOKEN")
            if xsrf:
                return xsrf
        except Exception as e:
            logger.warning("获取 XSRF token 失败: %s", e)

        return None

    # ============================================
    # Entitlements 查询（用户已拥有的游戏）
    # ============================================

    async def fetch_user_entitlements(
        self, credentials: DeviceAuthCredentials,
    ) -> set:
        """查询用户已拥有的 entitlement names

        参考 legendary 的 get_user_entitlements 接口：
        GET https://entitlement-public-service-prod08.ol.epicgames.com/entitlement/api/account/{accountId}/entitlements?start=0&count=1000

        Returns:
            set of entitlement names (e.g. {"FNBR_Athena_MTX", ...})
            这些是 catalogItemId，需要与游戏信息匹配判断是否已拥有。
        """
        # 刷新 token（如果过期）
        if credentials.is_expired():
            try:
                credentials = await self.refresh_access_token(credentials)
            except Exception:
                pass

        account_id = credentials.account_id
        all_entitlement_names = set()
        start = 0
        page_size = 1000

        try:
            while True:
                url = EPIC_ENTITLEMENTS_URL.format(account_id=account_id)
                resp = await self.client.get(
                    url,
                    params={"start": start, "count": page_size},
                    headers={
                        "Authorization": f"Bearer {credentials.access_token}",
                    },
                )
                if resp.status_code != 200:
                    logger.warning("entitlements 查询失败: %s - %s", resp.status_code, resp.text[:200])
                    break

                data = resp.json()
                if not data:
                    break

                # data 是 entitlements 列表
                for ent in data:
                    name = ent.get("entitlementName") or ent.get("catalogItemId")
                    if name:
                        all_entitlement_names.add(name)

                if len(data) < page_size:
                    break
                start += page_size

            logger.info("查询到 %d 个用户 entitlement", len(all_entitlement_names))
            return all_entitlement_names
        except Exception as e:
            logger.exception("查询 entitlements 异常")
            return set()

    def _build_checkout_url(self, game: FreeGame) -> str:
        """构造领取链接（与 claabs/epicgames-freegames-node 一致）"""
        namespace = game.namespace or (game.offer_id.split("/")[0] if "/" in game.offer_id else "")
        offers_param = f"&offers=1-{namespace}-{game.offer_id}"
        checkout_url = f"https://www.epicgames.com/store/purchase?highlightColor=0078f2{offers_param}&orderId&purchaseToken&showNavigation=true"
        login_redirect_url = (
            f"https://www.epicgames.com/id/login?"
            f"noHostRedirect=true&redirectUrl={checkout_url}&client_id=875a3b57d3a640a6b7f9b4e883463ab4"
        )
        return login_redirect_url

    async def fetch_free_games_with_status(
        self, credentials: Optional[DeviceAuthCredentials] = None,
    ) -> List[FreeGame]:
        """获取本周免费游戏 + 检查用户是否已拥有 + 生成领取链接

        Args:
            credentials: device auth credentials（如未提供则不检查是否已拥有）

        Returns:
            List[FreeGame] with already_owned, checkout_url filled
        """
        # 1. 获取本周免费游戏
        games = await self.fetch_free_games()
        if not games:
            return []

        # 2. 查询用户已拥有的 entitlements
        user_entitlements = set()
        if credentials:
            try:
                user_entitlements = await self.fetch_user_entitlements(credentials)
            except Exception as e:
                logger.warning("查询 entitlements 失败，继续返回未标记状态: %s", e)

        # 3. 标记每款游戏
        for game in games:
            # 检查是否已拥有（通过 offer_id 的 catalogItemId 部分匹配）
            offer_id_short = game.offer_id.split("/")[-1] if "/" in game.offer_id else game.offer_id
            if offer_id_short in user_entitlements or game.offer_id in user_entitlements:
                game.already_owned = True
                game.status = "already_claimed"
                game.message = "已拥有"

            # 生成领取链接
            game.checkout_url = self._build_checkout_url(game)

        return games

    # ============================================
    # 领取游戏
    # ============================================

    async def claim_game(self, credentials: DeviceAuthCredentials, game: FreeGame) -> Tuple[str, str]:
        """生成 Epic Games 领取链接（checkout URL）

        注意：Epic Games 的购买/领取流程无法通过纯 API 完成。
        购买接口需要浏览器 session cookie、XSRF-TOKEN、hCaptcha 等。
        因此我们生成一个 checkout URL，引导用户去浏览器手动领取。

        参考：claabs/epicgames-freegames-node 的 generateCheckoutUrl

        Returns:
            (status, message)  status: claimed/already_claimed/failed/needs_manual
        """
        # 检查 token 是否过期（用于生成 redirect URL）
        if credentials.is_expired():
            try:
                credentials = await self.refresh_access_token(credentials)
            except Exception:
                pass

        # 生成 checkout URL（参考 claabs/epicgames-freegames-node）
        namespace = game.offer_id.split("/")[0] if "/" in game.offer_id else ""
        offers_param = f"&offers=1-{namespace}-{game.offer_id}"
        checkout_url = f"https://www.epicgames.com/store/purchase?highlightColor=0078f2{offers_param}&orderId&purchaseToken&showNavigation=true"
        login_redirect_url = (
            f"https://www.epicgames.com/id/login?"
            f"noHostRedirect=true&redirectUrl={checkout_url}&client_id=875a3b57d3a640a6b7f9b4e883463ab4"
        )

        return (
            "needs_manual",
            f"请前往浏览器领取：<a href='{login_redirect_url}' target='_blank'>{game.title}</a>",
        )
