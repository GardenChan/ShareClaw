"""队列管理模块测试"""

import json
import os
import tempfile
import pytest

from shareclaw.claw.backend.local import LocalBackend
from shareclaw.claw.queue import (
    evict_oldest_if_needed,
    enqueue_account,
    detect_new_account,
    get_queue_info,
)


@pytest.fixture
def temp_dirs():
    """创建临时目录模拟 openclaw 和 shareclaw 数据目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        openclaw_home = os.path.join(tmpdir, ".openclaw")
        shareclaw_home = os.path.join(tmpdir, ".shareclaw")
        weixin_dir = os.path.join(openclaw_home, "openclaw-weixin")
        os.makedirs(weixin_dir)
        os.makedirs(shareclaw_home)
        yield {
            "openclaw_home": openclaw_home,
            "shareclaw_home": shareclaw_home,
            "weixin_dir": weixin_dir,
        }


@pytest.fixture
def backend(temp_dirs):
    """创建本地后端实例"""
    config = {
        "mode": "local",
        "max_queue_size": 3,  # 小队列方便测试
        "openclaw_home": temp_dirs["openclaw_home"],
        "shareclaw_home": temp_dirs["shareclaw_home"],
    }
    return LocalBackend(config)


class TestQueueReadWrite:
    """队列读写测试"""

    def test_read_empty_queue(self, backend):
        """测试读取空队列"""
        assert backend.read_queue() == []

    def test_write_and_read_queue(self, backend):
        """测试写入和读取队列"""
        queue = [
            {"account": "aaa-im-bot", "added_at": "2026-03-31 20:00:00"},
            {"account": "bbb-im-bot", "added_at": "2026-03-31 20:10:00"},
        ]
        backend.write_queue(queue)
        assert backend.read_queue() == queue


class TestAccountsReadWrite:
    """accounts.json 读写测试"""

    def test_read_empty_accounts(self, backend):
        """测试读取空 accounts"""
        assert backend.read_accounts() == []

    def test_write_and_read_accounts(self, backend):
        """测试写入和读取 accounts"""
        accounts = ["aaa-im-bot", "bbb-im-bot"]
        backend.write_accounts(accounts)
        assert backend.read_accounts() == accounts


class TestEviction:
    """踢出逻辑测试"""

    def test_no_eviction_when_queue_not_full(self, backend):
        """队列未满时不踢出"""
        queue = [
            {"account": "aaa-im-bot", "added_at": "2026-03-31 20:00:00"},
        ]
        backend.write_queue(queue)
        backend.write_accounts(["aaa-im-bot"])

        result = evict_oldest_if_needed(backend)
        assert result is None
        assert len(backend.read_queue()) == 1

    def test_evict_oldest_when_full(self, backend):
        """队列满时踢出最早的"""
        queue = [
            {"account": "aaa-im-bot", "added_at": "2026-03-31 20:00:00"},
            {"account": "bbb-im-bot", "added_at": "2026-03-31 20:10:00"},
            {"account": "ccc-im-bot", "added_at": "2026-03-31 20:20:00"},
        ]
        backend.write_queue(queue)
        backend.write_accounts(["aaa-im-bot", "bbb-im-bot", "ccc-im-bot"])

        result = evict_oldest_if_needed(backend)
        assert result == "aaa-im-bot"

        # 验证队列中已移除
        remaining_queue = backend.read_queue()
        assert len(remaining_queue) == 2
        assert remaining_queue[0]["account"] == "bbb-im-bot"

        # 验证 accounts.json 中已移除
        accounts = backend.read_accounts()
        assert "aaa-im-bot" not in accounts
        assert "bbb-im-bot" in accounts

    def test_evict_skips_if_not_in_accounts(self, backend):
        """踢出时如果 account 不在 accounts.json 中则跳过"""
        queue = [
            {"account": "aaa-im-bot", "added_at": "2026-03-31 20:00:00"},
            {"account": "bbb-im-bot", "added_at": "2026-03-31 20:10:00"},
            {"account": "ccc-im-bot", "added_at": "2026-03-31 20:20:00"},
        ]
        backend.write_queue(queue)
        # aaa-im-bot 不在 accounts.json 中（可能已被手动删除）
        backend.write_accounts(["bbb-im-bot", "ccc-im-bot"])

        result = evict_oldest_if_needed(backend)
        assert result == "aaa-im-bot"

        # accounts.json 不受影响
        accounts = backend.read_accounts()
        assert accounts == ["bbb-im-bot", "ccc-im-bot"]

    def test_evict_preserves_non_managed_accounts(self, backend):
        """踢出时不影响非本项目管理的 account"""
        queue = [
            {"account": "managed-im-bot", "added_at": "2026-03-31 20:00:00"},
            {"account": "managed2-im-bot", "added_at": "2026-03-31 20:10:00"},
            {"account": "managed3-im-bot", "added_at": "2026-03-31 20:20:00"},
        ]
        backend.write_queue(queue)
        # external-im-bot 是非本项目管理的
        backend.write_accounts(["external-im-bot", "managed-im-bot", "managed2-im-bot", "managed3-im-bot"])

        result = evict_oldest_if_needed(backend)
        assert result == "managed-im-bot"

        accounts = backend.read_accounts()
        assert "external-im-bot" in accounts  # 非管理的不受影响
        assert "managed-im-bot" not in accounts


class TestEnqueue:
    """入队测试"""

    def test_enqueue_new_account(self, backend):
        """测试新 account 入队"""
        enqueue_account(backend, "new-im-bot")

        queue = backend.read_queue()
        assert len(queue) == 1
        assert queue[0]["account"] == "new-im-bot"
        assert "added_at" in queue[0]

    def test_enqueue_duplicate_skipped(self, backend):
        """测试重复 account 不入队"""
        enqueue_account(backend, "dup-im-bot")
        enqueue_account(backend, "dup-im-bot")

        queue = backend.read_queue()
        assert len(queue) == 1

    def test_enqueue_preserves_order(self, backend):
        """测试入队保持 FIFO 顺序"""
        enqueue_account(backend, "first-im-bot")
        enqueue_account(backend, "second-im-bot")
        enqueue_account(backend, "third-im-bot")

        queue = backend.read_queue()
        assert [item["account"] for item in queue] == [
            "first-im-bot", "second-im-bot", "third-im-bot"
        ]


class TestDetectNewAccount:
    """新 account 检测测试"""

    def test_detect_new(self):
        """测试检测新增 account"""
        old = ["aaa-im-bot"]
        new = ["aaa-im-bot", "bbb-im-bot"]
        result = detect_new_account(old, new)
        assert result == "bbb-im-bot"

    def test_detect_no_change(self):
        """测试无变化"""
        old = ["aaa-im-bot"]
        new = ["aaa-im-bot"]
        result = detect_new_account(old, new)
        assert result is None

    def test_detect_from_empty(self):
        """测试从空列表新增"""
        old = []
        new = ["aaa-im-bot"]
        result = detect_new_account(old, new)
        assert result == "aaa-im-bot"


class TestQueueInfo:
    """队列信息测试"""

    def test_queue_info(self, backend):
        """测试获取队列信息"""
        queue = [
            {"account": "aaa-im-bot", "added_at": "2026-03-31 20:00:00"},
        ]
        backend.write_queue(queue)

        info = get_queue_info(backend)
        assert info["queue_length"] == 1
        assert info["max_queue_size"] == 3
        assert len(info["accounts"]) == 1
