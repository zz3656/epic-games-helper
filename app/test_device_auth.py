"""
Device Auth 流程测试脚本

独立运行，不依赖 FastAPI。用于验证 Epic API endpoint 和参数是否正确。
运行方式：
    python -m app.test_device_auth

但因为是容器内运行的，需要先在容器内测试：
    docker exec -it epic-games-claimer python -m app.test_device_auth
"""
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def test_request_device_code():
    """测试申请 device code"""
    from app.epic_api import EpicAPIClient

    logger.info("=" * 60)
    logger.info("测试 1: 申请 device code")
    logger.info("=" * 60)

    async with EpicAPIClient() as client:
        try:
            device_code, user_code, verification_uri, expires_in = \
                await client.request_device_code()
            logger.info("✓ 申请成功")
            logger.info("  device_code: %s", device_code[:20] + "...")
            logger.info("  user_code: %s", user_code)
            logger.info("  verification_uri: %s", verification_uri)
            logger.info("  expires_in: %d 秒", expires_in)
            logger.info("")
            logger.info("👉 请在浏览器中打开以下链接完成授权：")
            logger.info("   %s", verification_uri)
            logger.info("")
            return device_code
        except Exception as e:
            logger.error("✗ 申请失败: %s", e)
            logger.error("可能原因：")
            logger.error("1. 容器网络无法访问 Epic API")
            logger.error("2. client_id/client_secret 已失效")
            logger.error("3. API endpoint 已变更")
            return None


async def test_fetch_free_games():
    """测试获取免费游戏（无需登录）"""
    from app.epic_api import EpicAPIClient

    logger.info("=" * 60)
    logger.info("测试 2: 获取本周免费游戏（公开 API）")
    logger.info("=" * 60)

    async with EpicAPIClient() as client:
        try:
            games = await client.fetch_free_games()
            logger.info("✓ 获取到 %d 款免费游戏", len(games))
            for g in games[:5]:
                logger.info("  - %s", g.title)
                logger.info("    offer_id: %s", g.offer_id)
            if not games:
                logger.warning("本周暂无免费游戏（可能是 Epic 还没发布）")
            return games
        except Exception as e:
            logger.error("✗ 获取失败: %s", e)
            return []


async def main():
    """主测试流程"""
    logger.info("Epic Games Device Auth API 测试")
    logger.info("")

    # 测试 1: 免费游戏 API（不需登录，先测这个）
    games = await test_fetch_free_games()

    logger.info("")

    # 测试 2: 申请 device code（需要用户在浏览器完成授权）
    logger.info("是否测试 device code 申请？(y/N)")
    choice = input().strip().lower()
    if choice == "y":
        device_code = await test_request_device_code()
        if device_code:
            logger.info("")
            logger.info("Device code 已保存到内存，user 流程：")
            logger.info("1. 在浏览器打开 verification_uri")
            logger.info("2. 登录 Epic 账号并授权")
            logger.info("3. 等待 device code 完成（10 分钟内）")
            logger.info("")
            logger.info("完成后再运行本脚本可继续测试轮询。")
    else:
        logger.info("跳过 device code 测试")


if __name__ == "__main__":
    asyncio.run(main())
