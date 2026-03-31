"""配置模块测试"""

import os
import pytest

from shareclaw.config import get_config


class TestLocalMode:
    """本地模式配置测试"""

    def test_default_mode_is_local(self, monkeypatch):
        """测试默认模式为 local"""
        monkeypatch.delenv("SHARECLAW_MODE", raising=False)
        monkeypatch.delenv("TENCENT_SECRET_ID", raising=False)
        monkeypatch.delenv("TENCENT_SECRET_KEY", raising=False)
        monkeypatch.delenv("LIGHTHOUSE_INSTANCE_IDS", raising=False)

        config = get_config()
        assert config["mode"] == "local"

    def test_local_config_defaults(self, monkeypatch):
        """测试本地模式默认配置"""
        monkeypatch.setenv("SHARECLAW_MODE", "local")
        monkeypatch.delenv("TENCENT_SECRET_ID", raising=False)
        monkeypatch.delenv("TENCENT_SECRET_KEY", raising=False)
        monkeypatch.delenv("LIGHTHOUSE_INSTANCE_IDS", raising=False)

        config = get_config()
        assert config["mode"] == "local"
        assert config["max_queue_size"] == 6
        assert "openclaw_home" in config
        assert "shareclaw_home" in config

    def test_custom_queue_size(self, monkeypatch):
        """测试自定义队列大小"""
        monkeypatch.setenv("SHARECLAW_MODE", "local")
        monkeypatch.setenv("SHARECLAW_MAX_QUEUE_SIZE", "10")
        monkeypatch.delenv("TENCENT_SECRET_ID", raising=False)
        monkeypatch.delenv("TENCENT_SECRET_KEY", raising=False)
        monkeypatch.delenv("LIGHTHOUSE_INSTANCE_IDS", raising=False)

        config = get_config()
        assert config["max_queue_size"] == 10


class TestRemoteMode:
    """远程模式配置测试"""

    def test_remote_config_success(self, monkeypatch):
        """测试远程模式正常配置"""
        monkeypatch.setenv("SHARECLAW_MODE", "remote")
        monkeypatch.setenv("TENCENT_SECRET_ID", "test_id")
        monkeypatch.setenv("TENCENT_SECRET_KEY", "test_key")
        monkeypatch.setenv("LIGHTHOUSE_INSTANCE_IDS", "lhins-aaa,lhins-bbb")
        monkeypatch.setenv("LIGHTHOUSE_REGION", "ap-shanghai")

        config = get_config()
        assert config["mode"] == "remote"
        assert config["secret_id"] == "test_id"
        assert config["secret_key"] == "test_key"
        assert config["instance_ids"] == ["lhins-aaa", "lhins-bbb"]
        assert config["region"] == "ap-shanghai"

    def test_remote_default_region(self, monkeypatch):
        """测试远程模式默认地域"""
        monkeypatch.setenv("SHARECLAW_MODE", "remote")
        monkeypatch.setenv("TENCENT_SECRET_ID", "test_id")
        monkeypatch.setenv("TENCENT_SECRET_KEY", "test_key")
        monkeypatch.setenv("LIGHTHOUSE_INSTANCE_IDS", "lhins-test")
        monkeypatch.delenv("LIGHTHOUSE_REGION", raising=False)

        config = get_config()
        assert config["region"] == "ap-guangzhou"

    def test_remote_missing_secret(self, monkeypatch):
        """测试远程模式缺少密钥"""
        monkeypatch.setenv("SHARECLAW_MODE", "remote")
        monkeypatch.delenv("TENCENT_SECRET_ID", raising=False)
        monkeypatch.delenv("TENCENT_SECRET_KEY", raising=False)
        monkeypatch.setenv("LIGHTHOUSE_INSTANCE_IDS", "lhins-test")

        with pytest.raises(ValueError, match="TENCENT_SECRET_ID"):
            get_config()

    def test_remote_missing_instances(self, monkeypatch):
        """测试远程模式缺少实例 ID"""
        monkeypatch.setenv("SHARECLAW_MODE", "remote")
        monkeypatch.setenv("TENCENT_SECRET_ID", "test_id")
        monkeypatch.setenv("TENCENT_SECRET_KEY", "test_key")
        monkeypatch.delenv("LIGHTHOUSE_INSTANCE_IDS", raising=False)

        with pytest.raises(ValueError, match="LIGHTHOUSE_INSTANCE_IDS"):
            get_config()

    def test_remote_single_instance(self, monkeypatch):
        """测试远程模式单实例"""
        monkeypatch.setenv("SHARECLAW_MODE", "remote")
        monkeypatch.setenv("TENCENT_SECRET_ID", "test_id")
        monkeypatch.setenv("TENCENT_SECRET_KEY", "test_key")
        monkeypatch.setenv("LIGHTHOUSE_INSTANCE_IDS", "lhins-single")

        config = get_config()
        assert config["instance_ids"] == ["lhins-single"]


class TestInvalidMode:
    """无效模式测试"""

    def test_invalid_mode(self, monkeypatch):
        """测试无效的部署模式"""
        monkeypatch.setenv("SHARECLAW_MODE", "invalid")

        with pytest.raises(ValueError, match="不支持的部署模式"):
            get_config()