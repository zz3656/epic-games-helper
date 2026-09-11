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
from typing import Optional, Dict, List, Tuple, Any

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

# Checkout URL generation (from claabs/epicgames-freegames-node)
EPIC_CLIENT_ID = "875a3b57d3a640a6b7f9b4e883463ab4"
EPIC_ID_LOGIN_ENDPOINT = "https://www.epicgames.com/id/login"

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

# Authorization code flow constants 已从当前版本移除
# 原因：Epic 内部 OAuth client (launcherAppClient2) 未注册 localhost redirect_uri，
# 任何 /id/authorize 调用都会返回 errors.com.epicgames.accountportal.client_redirect_domain_mismatch 错误。
# 如需完整游戏库权限，请前往 https://www.epicgames.com/store/mygames


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


# ============================================
# 注意：Authorization Code Flow 相关代码已从当前版本移除。
# 原因：Epic 内部 OAuth client 未注册 localhost redirect_uri，
# 第三方应用无法使用 authorization_code flow 获取 library:public:items 权限。
# 如需查看完整游戏库，请前往 https://www.epicgames.com/store/mygames
# ============================================

@dataclass
class PromotionGame:
    """促销游戏"""
    title: str
    url: str
    offer_id: str
    image_url: str = ""          # 游戏封面 URL
    description: str = ""        # 游戏描述
    namespace: str = ""          # Epic namespace
    original_price: str = ""     # 原价（当前标价）
    current_price: str = ""      # 当前促销价
    discount_percent: int = 0    # 折扣百分比
    original_price_cents: int = 0
    current_price_cents: int = 0
    lowest_price: str = ""       # 历史最低价
    lowest_price_cents: int = 0


@dataclass
class FreeGame:
    """免费游戏"""
    title: str
    url: str
    offer_id: str
    offer_id_short: str = ""     # 仅 catalogItemId（不含 namespace）
    status: str = "pending"
    message: str = ""
    image_url: str = ""          # 游戏封面 URL
    description: str = ""        # 游戏描述
    namespace: str = ""          # Epic namespace
    checkout_url: str = ""       # 领取链接 (如未领取)
    already_owned: bool = False  # 是否已拥有
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
        """刷新 access_token（用 refresh_token 刷新，不需要重新授权）

        快失败机制：
        - 如果遇到 invalid_refresh_token 等不可重试错误，立即终止
        - 避免多 client 尝试导致请求耗时过长
        """
        import base64

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
                    # 如果是 refresh_token 本身无效，立即终止（其他 client 也会同样失败）
                    if resp.status_code in (400, 401):
                        try:
                            err_data = resp.json()
                            err_code = err_data.get("errorCode", "")
                            # 这些错误表示 token 无效，不需重试
                            if "invalid_refresh_token" in err_code or "invalid_grant" in err_code:
                                logger.warning("refresh_token 无效，不再重试其他 client")
                                break
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Token 刷新 client=%s 异常: %s", client_name, e)

        raise Exception("所有 client 都无法刷新 token")

    # ============================================
    # 免费游戏 API
    # ============================================

    def _parse_free_game(self, item: dict) -> FreeGame:
        """从 Epic API 返回的 item 提取 FreeGame（不检查 promo）"""
        # 提取 namespace 和 offer_id
        items_arr = item.get("items") or []
        if items_arr and items_arr[0].get("id") and items_arr[0].get("namespace"):
            offer_id_short = items_arr[0]["id"]
            namespace = items_arr[0]["namespace"]
        else:
            offer_id_short = item.get("id", "")
            namespace = item.get("namespace", "")

        if not offer_id_short or not namespace:
            return None

        offer_id = f"{namespace}/{offer_id_short}"
        title = item.get("title", "Unknown")
        # 优先使用 offerMappings[0].pageSlug（Epic 生成的唯一 URL slug，去 /p/{slug} 能直达正确商品页）
        # 例：Luftrausers 的 pageSlug = "luftrausers-51e5e9"
        # 回退到 urlSlug 或 productSlug
        slug = ""
        offer_mappings = item.get("offerMappings") or []
        if offer_mappings and offer_mappings[0].get("pageSlug"):
            slug = offer_mappings[0]["pageSlug"]
        if not slug:
            slug = item.get("productSlug") or item.get("urlSlug") or offer_id_short
        url = f"https://store.epicgames.com/zh-CN/p/{slug}" if slug else ""

        # 封面图
        image_url = ""
        key_images = item.get("keyImages") or []
        for img in key_images:
            if img.get("type") in ("Thumbnail", "DieselStoreFrontWide", "OfferImageWide", "VaultClosed"):
                image_url = img.get("url", "")
                if img.get("type") == "Thumbnail":
                    break
        if not image_url and key_images:
            image_url = key_images[0].get("url", "")

        description = item.get("description", "") or item.get("shortDescription", "")
        price = item.get("price", {}).get("totalPrice", {}) or {}
        fmt_price = price.get("fmtPrice", {}) or {}
        original_price = fmt_price.get("originalPrice", "")

        return FreeGame(
            title=title,
            url=url,
            offer_id=offer_id,
            offer_id_short=offer_id_short,
            image_url=image_url,
            description=description,
            namespace=namespace,
            original_price=original_price,
        )

    async def fetch_free_games(self) -> Tuple[List[FreeGame], List[FreeGame]]:
        """从 Epic 公开 API 获取本周免费游戏（无需登录）

        Returns:
            (current_games, upcoming_games)
            - current_games: 本周正在免费领取的游戏（discountPrice=0 且 promo 有效）
            - upcoming_games: 下周即将免费的游戏（upcomingPromotionalOffers 中的下一个免费周期）

        字段说明（参考 Epic API 返回结构）：
        - item.id: catalog item ID（不是 offer ID）
        - item.namespace: 该 catalog item 所属的 namespace（顶层字段）
        - item.items[0].id + .namespace: 实际的 offer 信息（用于 checkout URL）
        """
        try:
            resp = await self.client.get(
                EPIC_FREE_GAMES,
                params={"locale": "zh-CN", "country": "CN", "allowCountries": "CN"},
            )
            resp.raise_for_status()
            data = resp.json()
            games = []
            upcoming = []

            for item in data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", []):
                promotions = item.get("promotions") or {}
                offers = promotions.get("promotionalOffers") or []
                upcoming_offers = promotions.get("upcomingPromotionalOffers") or []

                # === 本周免费 ===
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

                if has_full_free:
                    # 双检价格
                    price = item.get("price", {}).get("totalPrice", {}) or {}
                    if price.get("discountPrice", 0) == 0:
                        game = self._parse_free_game(item)
                        if game:
                            game.start_date = start_date
                            game.end_date = end_date
                            games.append(game)
                        continue  # 已识别为本周免费，跳过 upcoming 检查

                # === 下周预告（仅取 100% 免费的 upcoming offer）===
                for promo_group in upcoming_offers:
                    for offer in promo_group.get("promotionalOffers", []):
                        ds = offer.get("discountSetting") or {}
                        if ds.get("discountType") == "PERCENTAGE" and ds.get("discountPercentage") == 0:
                            game = self._parse_free_game(item)
                            if game:
                                game.start_date = offer.get("startDate", "")
                                game.end_date = offer.get("endDate", "")
                                game.message = "下周免费"  # 标记为预告
                                upcoming.append(game)
                            break  # 一個游戏只加一次

            logger.info("获取到 %d 款本周免费游戏，%d 款下周预告", len(games), len(upcoming))
            return games, upcoming
        except Exception as e:
            logger.exception("获取免费游戏失败")
            return [], []

    async def fetch_free_games_legacy(self) -> List[FreeGame]:
        """为了向后兼容，仅返回本周免费游戏列表"""
        games, _ = await self.fetch_free_games()
        return games

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
    # 促销游戏 API
    # ============================================

    @staticmethod
    def _load_low_prices() -> Dict[str, Dict]:
        """从本地 low_prices.json 加载历史最低价数据"""
        import json
        import os
        low_file = "/app/data/low_prices.json"
        if os.path.exists(low_file):
            try:
                with open(low_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _parse_promotion_game(self, item: dict, low_prices: Dict) -> Optional[PromotionGame]:
        """从 Epic API 返回的 item 提取 PromotionGame"""
        items_arr = item.get("items") or []
        if not items_arr or not items_arr[0].get("id"):
            return None

        offer_id_short = items_arr[0]["id"]
        namespace = items_arr[0].get("namespace", "")
        offer_id = f"{namespace}/{offer_id_short}"
        title = item.get("title", "Unknown")

        slug = ""
        offer_mappings = item.get("offerMappings") or []
        if offer_mappings and offer_mappings[0].get("pageSlug"):
            slug = offer_mappings[0]["pageSlug"]
        if not slug:
            slug = item.get("productSlug") or item.get("urlSlug") or offer_id_short
        url = f"https://store.epicgames.com/zh-CN/p/{slug}" if slug else ""

        # 封面图
        image_url = ""
        key_images = item.get("keyImages") or []
        for img in key_images:
            if img.get("type") in ("Thumbnail", "DieselStoreFrontWide", "OfferImageWide", "VaultClosed"):
                image_url = img.get("url", "")
                if img.get("type") == "Thumbnail":
                    break
        if not image_url and key_images:
            image_url = key_images[0].get("url", "")

        description = item.get("description", "") or item.get("shortDescription", "")

        price = item.get("price", {}).get("totalPrice", {}) or {}
        discount_price = price.get("discountPrice", 0)
        original_price_cents = price.get("originalPrice", 0)
        discount = price.get("discount", 0)
        fmt_price = price.get("fmtPrice", {}) or {}
        original_price = fmt_price.get("originalPrice", "")
        current_price = fmt_price.get("discountPrice", "")

        # 计算折扣百分比
        discount_percent = 0
        if original_price_cents > 0:
            discount_percent = round(discount / original_price_cents * 100)

        # 查找历史最低价
        lowest_price_cents = 0
        lowest_price = ""
        # 用 title 作为 key 查找
        for key, data in low_prices.items():
            # 尝试精确匹配或标题中包含
            if key.lower() in title.lower() or title.lower().startswith(key.lower()):
                lowest_price_cents = data.get("lowest_price", 0)
                lowest_price = data.get("lowest_price_formatted", "")
                break

        return PromotionGame(
            title=title,
            url=url,
            offer_id=offer_id,
            image_url=image_url,
            description=description,
            namespace=namespace,
            original_price=original_price,
            current_price=current_price,
            discount_percent=discount_percent,
            original_price_cents=original_price_cents,
            current_price_cents=discount_price,
            lowest_price=lowest_price,
            lowest_price_cents=lowest_price_cents,
        )

    async def fetch_promotions(self) -> List[PromotionGame]:
        """获取当前正在促销（打折）的游戏列表（非免费）

        Returns:
            当前打折的游戏列表（排除免费游戏）
        """
        try:
            resp = await self.client.get(
                EPIC_FREE_GAMES,
                params={"locale": "zh-CN", "country": "CN", "allowCountries": "CN"},
            )
            resp.raise_for_status()
            data = resp.json()
            games = []

            low_prices = self._load_low_prices()

            for item in data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", []):
                # 仅处理 BASE_GAME
                if item.get("offerType") != "BASE_GAME":
                    continue

                price = item.get("price", {}).get("totalPrice", {}) or {}
                discount_price = price.get("discountPrice", 0)
                original_price_cents = price.get("originalPrice", 0)

                # 必须是打折的（有折扣且不是免费）
                if discount_price <= 0 or discount_price >= original_price_cents:
                    continue

                game = self._parse_promotion_game(item, low_prices)
                if game:
                    games.append(game)

            # 按折扣幅度排序
            games.sort(key=lambda g: g.discount_percent, reverse=True)
            logger.info("获取到 %d 款促销游戏", len(games))
            return games
        except Exception as e:
            logger.exception("获取促销游戏失败")
            return []

    # ============================================
    async def fetch_free_games_with_status(
        self, credentials: Optional[DeviceAuthCredentials] = None,
    ) -> Tuple[List[FreeGame], List[FreeGame], Dict[str, Any]]:
        """获取本周免费游戏 + 下周预告 + 生成领取链接

        注意：检查用户是否已拥有（entitlements API）需要有效的 device auth token。
        由于 Epic 内部 OAuth client 未注册 localhost redirect_uri，device auth token
        权限有限，entitlements API 查询结果不可靠，因此不再使用 credentials。

        Returns:
            (games, upcoming, diagnostics)
        """
        diagnostics: Dict[str, Any] = {
            "free_games_fetch_ok": False,
            "games_count": 0,
            "upcoming_count": 0,
        }

        games, upcoming = await self.fetch_free_games()
        diagnostics["free_games_fetch_ok"] = True
        diagnostics["games_count"] = len(games)
        diagnostics["upcoming_count"] = len(upcoming)

        if not games:
            return [], upcoming, diagnostics

        # 生成 checkout_url
        for game in games:
            game.checkout_url = self._build_checkout_url(game)

        # 下周预告使用商店页 URL
        for game in upcoming:
            game.checkout_url = game.url

        return games, upcoming, diagnostics

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
        login_redirect_url = self._build_checkout_url(game)

        return (
            "needs_manual",
            f"请前往浏览器领取：<a href='{login_redirect_url}' target='_blank'>{game.title}</a>",
        )

    def _build_checkout_url(self, game: FreeGame) -> str:
        """生成 Epic Games checkout URL + login redirect

        参考：claabs/epicgames-freegames-node 的 generateCheckoutUrl

        Args:
            game: FreeGame 对象，需要 offer_id 和 namespace

        Returns:
            完整的 login redirect URL
        """
        # 构建 offers 参数: &offers=1-{namespace}-{offer_id}
        offers_params = f"&offers=1-{game.namespace}-{game.offer_id}"
        # 构建 checkout URL
        checkout_url = f"{EPIC_PURCHASE_ORDER}?highlightColor=0078f2{offers_params}&orderId&purchaseToken&showNavigation=true"
        # 包装为 login redirect URL
        # 使用 urllib.parse 构建查询参数
        from urllib.parse import urlencode, urljoin
        params = urlencode({
            "noHostRedirect": "true",
            "redirectUrl": checkout_url,
            "client_id": EPIC_CLIENT_ID,
        })
        return f"{EPIC_ID_LOGIN_ENDPOINT}?{params}"
