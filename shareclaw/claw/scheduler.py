"""
多实例调度器（远程模式专用）

负责：
1. 根据各实例的队列长度选择最优实例
2. 维护不健康实例的黑名单（永久剔除）
3. 为选中的实例创建 RemoteBackend
"""

import logging
import random
from typing import List, Optional

logger = logging.getLogger(__name__)


class InstanceScheduler:
    """
    多实例调度器。

    选择策略：
    - 查询所有健康实例的 accounts_queue.json 队列长度
    - 选队列长度最短的（最空闲）
    - 长度相同的随机选一台

    黑名单：
    - 不健康的实例会被永久加入黑名单
    - 黑名单中的实例不再参与调度
    """

    def __init__(self, config: dict):
        self.config = config
        self.instance_ids: List[str] = list(config.get("instance_ids", []))
        self._blacklist: set = set()  # 不健康实例黑名单

        # 缓存云客户端，避免每次创建 RemoteBackend 时重复实例化
        self._cached_clients = None

    @property
    def available_instances(self) -> List[str]:
        """获取可用实例列表（排除黑名单）"""
        return [iid for iid in self.instance_ids if iid not in self._blacklist]

    def blacklist_instance(self, instance_id: str) -> None:
        """
        将实例加入黑名单（永久剔除）

        Args:
            instance_id: 要剔除的实例 ID
        """
        self._blacklist.add(instance_id)
        logger.warning(f"实例 {instance_id} 已被加入黑名单，不再参与调度")

    def is_blacklisted(self, instance_id: str) -> bool:
        """检查实例是否在黑名单中"""
        return instance_id in self._blacklist

    def select_instance(self) -> Optional[str]:
        """
        选择最优实例。

        策略：
        1. 遍历所有可用实例，检查健康状态
        2. 不健康的加入黑名单
        3. 查询健康实例的队列长度
        4. 选队列最短的，相同长度随机选

        Returns:
            选中的实例 ID，如果没有可用实例则返回 None
        """
        from shareclaw.claw.backend.remote import RemoteBackend

        available = self.available_instances
        if not available:
            logger.error("没有可用的 Lighthouse 实例（全部已被加入黑名单）")
            return None

        # 收集各实例的队列长度
        instance_queue_lengths = []

        for instance_id in available:
            try:
                backend = RemoteBackend(self.config, instance_id=instance_id)

                # 健康检查
                if not backend.check_instance_health():
                    logger.warning(f"实例 {instance_id} 不健康，加入黑名单")
                    self.blacklist_instance(instance_id)
                    continue

                queue_length = backend.get_queue_length()
                instance_queue_lengths.append((instance_id, queue_length))
                logger.info(f"实例 {instance_id} 队列长度: {queue_length}")

            except Exception as e:
                logger.warning(f"实例 {instance_id} 查询失败: {e}，加入黑名单")
                self.blacklist_instance(instance_id)
                continue

        if not instance_queue_lengths:
            logger.error("所有实例均不可用")
            return None

        # 找到最小队列长度
        min_length = min(length for _, length in instance_queue_lengths)

        # 筛选出队列长度最短的实例
        candidates = [
            iid for iid, length in instance_queue_lengths
            if length == min_length
        ]

        # 随机选一台
        selected = random.choice(candidates)
        logger.info(
            f"选中实例 {selected}（队列长度: {min_length}，"
            f"同长度候选: {len(candidates)} 台）"
        )

        return selected

    def get_status(self) -> dict:
        """获取调度器状态摘要"""
        return {
            "total_instances": len(self.instance_ids),
            "available_instances": self.available_instances,
            "blacklisted_instances": list(self._blacklist),
        }
