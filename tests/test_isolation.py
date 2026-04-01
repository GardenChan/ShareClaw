"""微信账号强隔离模块测试"""

import json
import os
import tempfile
import pytest

from shareclaw.claw.isolation import make_agent_id
from shareclaw.claw.commands import (
    cmd_create_agent,
    cmd_add_binding,
    cmd_remove_binding,
    cmd_remove_agent,
    cmd_list_bindings,
    cmd_list_agents,
)


class TestMakeAgentId:
    """agentId 生成测试"""

    def test_standard_account_id(self):
        """测试标准 accountId 生成 agentId"""
        assert make_agent_id("561b705dc7e0-im-bot") == "wx-561b705dc7e0"

    def test_another_account_id(self):
        """测试另一个 accountId"""
        assert make_agent_id("134567e95d3e0-im-bot") == "wx-134567e95d3e0"

    def test_account_without_suffix(self):
        """测试不带 -im-bot 后缀的 accountId"""
        assert make_agent_id("abcdef123456") == "wx-abcdef123456"

    def test_short_account_id(self):
        """测试较短的 accountId"""
        assert make_agent_id("abc-im-bot") == "wx-abc"


class TestIsolationCommands:
    """隔离相关命令生成测试"""

    def test_cmd_create_agent(self):
        """测试创建 Agent 命令"""
        cmd = cmd_create_agent("wx-561b705dc7e0")
        assert "openclaw agents add wx-561b705dc7e0" in cmd
        assert "--workspace ~/.openclaw/workspace-wx-561b705dc7e0" in cmd
        assert "--agent-dir ~/.openclaw/agents/wx-561b705dc7e0/agent" in cmd
        assert "--non-interactive" in cmd

    def test_cmd_add_binding(self):
        """测试添加 binding 命令"""
        cmd = cmd_add_binding("wx-561b705dc7e0", "561b705dc7e0-im-bot")
        # 应包含 jq 命令和 base64 编码
        assert "base64" in cmd
        assert "jq" in cmd
        assert "bindings" in cmd

    def test_cmd_add_binding_content(self):
        """测试 binding 命令中编码的内容包含正确的数据"""
        import base64
        cmd = cmd_add_binding("wx-test", "test-im-bot")
        # 提取 base64 编码的部分
        parts = cmd.split("'")
        for part in parts:
            try:
                decoded = base64.b64decode(part).decode("utf-8")
                data = json.loads(decoded)
                if "agentId" in data:
                    assert data["agentId"] == "wx-test"
                    assert data["match"]["channel"] == "openclaw-weixin"
                    assert data["match"]["accountId"] == "test-im-bot"
                    break
            except Exception:
                continue

    def test_cmd_remove_binding(self):
        """测试移除 binding 命令"""
        cmd = cmd_remove_binding("561b705dc7e0-im-bot")
        assert "jq" in cmd
        assert "561b705dc7e0-im-bot" in cmd
        assert "bindings" in cmd

    def test_cmd_remove_agent(self):
        """测试移除 Agent 命令"""
        cmd = cmd_remove_agent("wx-561b705dc7e0")
        assert "jq" in cmd
        assert "wx-561b705dc7e0" in cmd
        assert "agents.list" in cmd

    def test_cmd_list_bindings(self):
        """测试列出 bindings 命令"""
        cmd = cmd_list_bindings()
        assert "jq" in cmd
        assert "bindings" in cmd

    def test_cmd_list_agents(self):
        """测试列出 agents 命令"""
        cmd = cmd_list_agents()
        assert "jq" in cmd
        assert "agents.list" in cmd


class TestSettingsIsolation:
    """设置中的隔离开关测试"""

    def test_default_settings_include_isolation(self):
        """测试默认设置包含隔离开关"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from shareclaw.sharing.store import SharingStore
            store = SharingStore(tmpdir)
            settings = store.read_settings()
            assert "account_isolation_enabled" in settings
            assert settings["account_isolation_enabled"] is False

    def test_enable_isolation(self):
        """测试开启隔离"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from shareclaw.sharing.store import SharingStore
            store = SharingStore(tmpdir)
            settings = store.read_settings()
            settings["account_isolation_enabled"] = True
            store.write_settings(settings)

            reloaded = store.read_settings()
            assert reloaded["account_isolation_enabled"] is True

    def test_disable_isolation(self):
        """测试关闭隔离"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from shareclaw.sharing.store import SharingStore
            store = SharingStore(tmpdir)
            settings = store.read_settings()
            settings["account_isolation_enabled"] = True
            store.write_settings(settings)

            settings["account_isolation_enabled"] = False
            store.write_settings(settings)

            reloaded = store.read_settings()
            assert reloaded["account_isolation_enabled"] is False
