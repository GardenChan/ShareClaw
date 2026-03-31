"""
Account 队列管理模块

管理 accounts_queue.json，实现 FIFO 队列，
只允许踢出本项目录入的 account，保护非本项目管理的 account。
"""

import logging
from datetime import datetime
from typing import Optional

from shareclaw.claw.backend.base import ClawBackend

logger = logging.getLogger(__name__)


def evict_oldest_if_needed(backend: ClawBackend) -> Optional[str]:
    """
    如果队列已满，踢出最早加入的 account。

    流程：
    1. 读取 accounts_queue.json
    2. 如果队列长度 >= max_queue_size，取出最早的 account
    3. 检查该 account 是否在 accounts.json 中
    4. 如果在，从 accounts.json 中移除
    5. 从 accounts_queue.json 中移除该记录

    Args:
        backend: 后端实例

    Returns:
        被踢出的 account 名称，如果无需踢出则返回 None
    """
    queue = backend.read_queue()

    if len(queue) < backend.max_queue_size:
        logger.info(f"队列未满 ({len(queue)}/{backend.max_queue_size})，无需踢出")
        return None

    # 取出最早的（队首）
    oldest = queue.pop(0)
    oldest_account = oldest["account"]
    logger.info(f"队列已满，准备踢出最早的 account: {oldest_account} (加入时间: {oldest['added_at']})")

    # 检查是否在 accounts.json 中
    accounts = backend.read_accounts()
    if oldest_account in accounts:
        accounts.remove(oldest_account)
        backend.write_accounts(accounts)
        logger.info(f"已从 accounts.json 中移除: {oldest_account}")
    else:
        logger.info(f"{oldest_account} 不在 accounts.json 中，跳过移除")

    # 更新队列
    backend.write_queue(queue)
    logger.info(f"已从队列中移除: {oldest_account}，当前队列长度: {len(queue)}")

    return oldest_account


def enqueue_account(backend: ClawBackend, account: str) -> None:
    """
    将新 account 加入队列尾部。

    Args:
        backend: 后端实例
        account: 新的 account 名称
    """
    queue = backend.read_queue()

    # 检查是否已在队列中（避免重复）
    existing = [item for item in queue if item["account"] == account]
    if existing:
        logger.warning(f"account {account} 已在队列中，跳过入队")
        return

    queue.append({
        "account": account,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    backend.write_queue(queue)
    logger.info(f"已将 {account} 加入队列，当前队列长度: {len(queue)}")


def detect_new_account(old_accounts: list, new_accounts: list) -> Optional[str]:
    """
    对比登录前后的 accounts.json，检测新增的 account。

    Args:
        old_accounts: 登录前的 account 列表
        new_accounts: 登录后的 account 列表

    Returns:
        新增的 account 名称，如果没有新增则返回 None
    """
    old_set = set(old_accounts)
    added = [a for a in new_accounts if a not in old_set]

    if added:
        return added[0]
    return None


def get_queue_info(backend: ClawBackend) -> dict:
    """
    获取队列信息摘要

    Args:
        backend: 后端实例

    Returns:
        dict: 队列信息
    """
    queue = backend.read_queue()
    return {
        "queue_length": len(queue),
        "max_queue_size": backend.max_queue_size,
        "accounts": [
            {"account": item["account"], "added_at": item["added_at"]}
            for item in queue
        ],
    }
