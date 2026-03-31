"""调度器模块测试"""

import pytest

from shareclaw.claw.scheduler import InstanceScheduler


@pytest.fixture
def scheduler_config():
    """远程模式配置"""
    return {
        "mode": "remote",
        "max_queue_size": 6,
        "secret_id": "test_id",
        "secret_key": "test_key",
        "instance_ids": ["lhins-aaa", "lhins-bbb", "lhins-ccc"],
        "region": "ap-guangzhou",
    }


class TestSchedulerBlacklist:
    """黑名单测试"""

    def test_initial_all_available(self, scheduler_config):
        """初始状态所有实例可用"""
        scheduler = InstanceScheduler(scheduler_config)
        assert len(scheduler.available_instances) == 3

    def test_blacklist_instance(self, scheduler_config):
        """测试加入黑名单"""
        scheduler = InstanceScheduler(scheduler_config)
        scheduler.blacklist_instance("lhins-aaa")

        assert "lhins-aaa" not in scheduler.available_instances
        assert len(scheduler.available_instances) == 2
        assert scheduler.is_blacklisted("lhins-aaa")

    def test_blacklist_all_instances(self, scheduler_config):
        """测试全部加入黑名单"""
        scheduler = InstanceScheduler(scheduler_config)
        scheduler.blacklist_instance("lhins-aaa")
        scheduler.blacklist_instance("lhins-bbb")
        scheduler.blacklist_instance("lhins-ccc")

        assert len(scheduler.available_instances) == 0

    def test_blacklist_is_permanent(self, scheduler_config):
        """测试黑名单是永久的"""
        scheduler = InstanceScheduler(scheduler_config)
        scheduler.blacklist_instance("lhins-aaa")

        # 多次检查仍在黑名单中
        assert scheduler.is_blacklisted("lhins-aaa")
        assert "lhins-aaa" not in scheduler.available_instances

    def test_get_status(self, scheduler_config):
        """测试获取调度器状态"""
        scheduler = InstanceScheduler(scheduler_config)
        scheduler.blacklist_instance("lhins-bbb")

        status = scheduler.get_status()
        assert status["total_instances"] == 3
        assert "lhins-bbb" in status["blacklisted_instances"]
        assert "lhins-bbb" not in status["available_instances"]
        assert len(status["available_instances"]) == 2
