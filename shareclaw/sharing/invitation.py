"""
邀请码管理模块

支持：
- 虾主生成邀请码（每个邀请码只能使用一次）
- 验证邀请码是否有效
- 使用邀请码（标记已用）
- 列出所有邀请码
"""

import logging
import secrets
from datetime import datetime

from shareclaw.sharing.store import SharingStore

logger = logging.getLogger(__name__)


class InvitationManager:
    """邀请码管理器"""

    def __init__(self, store: SharingStore):
        self.store = store

    def create(self, created_by: str = "虾主", **kwargs) -> str:
        """
        生成新的邀请码（每个邀请码只能使用一次）

        Args:
            created_by: 创建者名称

        Returns:
            str: 生成的邀请码
        """
        code = secrets.token_urlsafe(8)  # 11 字符的 URL 安全码

        self.store.save_invitation(code, {
            "created_by": created_by,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "max_uses": 1,
            "used_count": 0,
            "used_by": None,
        })

        logger.info(f"已创建邀请码: {code}")
        return code

    def validate(self, code: str) -> tuple[bool, str]:
        """
        验证邀请码是否有效

        Args:
            code: 邀请码

        Returns:
            (is_valid, message)
        """
        if not code:
            return False, "邀请码不能为空"

        invitation = self.store.get_invitation(code)
        if not invitation:
            return False, "邀请码无效"

        if invitation["used_count"] >= 1:
            return False, "邀请码已被使用"

        return True, "邀请码有效"

    def use(self, code: str, user_id: str) -> bool:
        """
        使用邀请码（标记已用）

        Args:
            code: 邀请码
            user_id: 使用者 ID

        Returns:
            bool: 是否成功
        """
        valid, msg = self.validate(code)
        if not valid:
            logger.warning(f"邀请码 {code} 使用失败: {msg}")
            return False

        invitations = self.store.read_invitations()
        inv = invitations.get(code)
        if inv:
            inv["used_count"] = 1
            inv["used_by"] = user_id
            self.store.write_invitations(invitations)
            logger.info(f"邀请码 {code} 已被 {user_id} 使用")

        return True

    def list_all(self) -> dict:
        """列出所有邀请码"""
        return self.store.read_invitations()

    def delete(self, code: str) -> bool:
        """删除邀请码"""
        invitations = self.store.read_invitations()
        if code in invitations:
            del invitations[code]
            self.store.write_invitations(invitations)
            logger.info(f"已删除邀请码: {code}")
            return True
        return False
