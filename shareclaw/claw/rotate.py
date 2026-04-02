"""坐席轮转核心流程"""

import logging
import os
import threading

from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

from shareclaw.config import get_config
from shareclaw.claw.backend import create_backend
from shareclaw.claw.backend.remote import RemoteBackend
from shareclaw.claw.queue import evict_oldest_if_needed, enqueue_account, detect_new_account, get_queue_info
from shareclaw.claw.isolation import setup_isolated_agent, teardown_isolated_agent
from shareclaw.claw.scheduler import InstanceScheduler
from shareclaw.server.sse import sse_event

logger = logging.getLogger(__name__)

# 全局调度器实例（远程模式下复用，保持黑名单状态）
_scheduler: InstanceScheduler = None

# 按实例粒度的互斥锁：同一实例同一时刻只允许一个轮转，不同实例可并行
_instance_locks: dict = {}  # instance_id -> threading.Lock
_locks_guard = threading.Lock()  # 保护 _instance_locks 字典本身的并发访问


def _get_instance_lock(instance_id: str) -> threading.Lock:
    """获取指定实例的互斥锁（懒创建）"""
    with _locks_guard:
        if instance_id not in _instance_locks:
            _instance_locks[instance_id] = threading.Lock()
        return _instance_locks[instance_id]


def _get_scheduler(config: dict) -> InstanceScheduler:
    """获取或创建全局调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = InstanceScheduler(config)
    return _scheduler


def rotate_stream():
    """
    坐席轮转的完整流程，以生成器形式逐步 yield SSE 事件。

    支持两种部署模式：
    - local: 本地模式，直接操作文件系统
    - remote: 远程模式，通过 TAT 操作 Lighthouse 实例（支持多实例调度）

    互斥策略：按实例粒度加锁。
    - 本地模式：同一时刻只允许一个轮转
    - 远程模式：同一实例同一时刻只允许一个轮转，不同实例可并行执行

    Yields:
        str: SSE 格式的事件字符串
    """
    # 预初始化变量，避免异常处理中引用未定义变量
    mode = None
    selected_id = None
    scheduler = None
    instance_lock = None

    try:
        # 1. 读取配置
        config = get_config()
        mode = config["mode"]

        # 读取隔离开关
        isolation_enabled = False
        try:
            from shareclaw.sharing.store import SharingStore
            data_dir = config.get("shareclaw_home") or os.path.expanduser("~/.shareclaw")
            _store = SharingStore(data_dir)
            _settings = _store.read_settings()
            isolation_enabled = _settings.get("account_isolation_enabled", False)
        except Exception:
            pass

        yield sse_event("progress", {
            "stage": "init",
            "message": f"配置加载完成，部署模式: {mode}"
                       + (f"，微信账号强隔离: 已开启" if isolation_enabled else "")
                       + "，开始执行轮转...",
        })

        # 2. 创建后端并确定实例 ID
        if mode == "local":
            selected_id = "local"
            backend = create_backend(config)
            yield sse_event("progress", {
                "stage": "backend_ready",
                "message": "本地模式后端就绪",
            })
        else:
            # 远程模式：通过调度器选择最优实例
            scheduler = _get_scheduler(config)

            yield sse_event("progress", {
                "stage": "selecting_instance",
                "message": f"正在从 {len(scheduler.available_instances)} 台实例中选择最优目标...",
                "data": scheduler.get_status(),
            })

            selected_id = scheduler.select_instance()
            if not selected_id:
                raise RuntimeError("没有可用的实例（全部不健康或已被剔除）")

            backend = RemoteBackend(config, instance_id=selected_id)

            yield sse_event("progress", {
                "stage": "backend_ready",
                "message": f"已选择实例 {selected_id}",
            })

        # 获取该实例的锁
        instance_lock = _get_instance_lock(selected_id)
        if not instance_lock.acquire(blocking=False):
            yield sse_event("error", {
                "stage": "error",
                "message": f"实例 {selected_id} 已有轮转任务在执行中，请稍后再试",
            })
            return

        # 3. 查询当前状态
        current_status = backend.query_status()
        queue_info = get_queue_info(backend)

        yield sse_event("progress", {
            "stage": "query_status",
            "message": "已查询当前微信接入状态",
            "data": {
                "status": current_status,
                "queue": queue_info,
            },
        })

        # 4. 记录登录前的 accounts（用于后续检测新增）
        old_accounts = backend.read_accounts()

        # 5. 队列满时踢出最早的 account
        evicted = evict_oldest_if_needed(backend)
        if evicted:
            yield sse_event("progress", {
                "stage": "evict",
                "message": f"已踢出最早的 account: {evicted}",
                "data": {"evicted_account": evicted},
            })

            # 如果开启了强隔离，清理被踢出账号的 binding
            if isolation_enabled:
                try:
                    teardown_result = teardown_isolated_agent(backend, evicted)
                    yield sse_event("progress", {
                        "stage": "isolation_cleanup",
                        "message": f"已清理被踢出账号的隔离配置",
                        "data": teardown_result,
                    })
                except Exception as e:
                    logger.warning(f"清理隔离配置失败（不影响轮转）: {e}")
        else:
            yield sse_event("progress", {
                "stage": "evict",
                "message": f"队列未满 ({queue_info['queue_length']}/{queue_info['max_queue_size']})，无需踢出",
            })

        # 6. 登录新微信
        for event in backend.login():
            yield event

        # 7. 检测新增的 account 并入队
        new_accounts = backend.read_accounts()
        new_account = detect_new_account(old_accounts, new_accounts)

        if new_account:
            enqueue_account(backend, new_account)
            yield sse_event("progress", {
                "stage": "enqueue",
                "message": f"新 account 已入队: {new_account}",
                "data": {"new_account": new_account},
            })

            # 如果开启了强隔离，为新账号创建独立 Agent 并配置 binding
            if isolation_enabled:
                try:
                    isolation_result = setup_isolated_agent(backend, new_account)
                    yield sse_event("progress", {
                        "stage": "isolation_setup",
                        "message": f"已为新账号创建独立 Agent: {isolation_result['agent_id']}",
                        "data": isolation_result,
                    })
                except Exception as e:
                    logger.error(f"强隔离设置失败: {e}")
                    yield sse_event("progress", {
                        "stage": "isolation_setup",
                        "message": f"⚠️ 强隔离设置失败（账号已接入但未隔离）: {str(e)}",
                    })
        else:
            logger.warning("登录后未检测到新增 account")
            yield sse_event("progress", {
                "stage": "enqueue",
                "message": "⚠️ 登录后未检测到新增 account，请检查登录是否成功",
            })

        # 8. 重启 gateway
        backend.restart_gateway()
        yield sse_event("progress", {
            "stage": "restart_gateway",
            "message": "openclaw-gateway 已重启",
        })

        # 9. 检查服务状态
        status = backend.check_gateway()
        if status != "active":
            raise RuntimeError(f"gateway 重启后状态异常: {status}")

        # 10. 最终状态
        final_queue = get_queue_info(backend)
        yield sse_event("done", {
            "stage": "done",
            "message": "坐席轮转完成！新微信已接入并服务正常运行",
            "gateway_status": status,
            "queue": final_queue,
            "instance_id": backend.get_instance_id(),
        })

    except ValueError as e:
        yield sse_event("error", {"stage": "error", "message": f"配置错误: {str(e)}"})

    except TimeoutError as e:
        yield sse_event("error", {"stage": "error", "message": f"操作超时: {str(e)}"})

    except TencentCloudSDKException as e:
        logger.error(
            "坐席轮转遇到腾讯云 API 异常: code=%s, message=%s, request_id=%s, instance_id=%s",
            getattr(e, "code", ""),
            getattr(e, "message", str(e)),
            getattr(e, "requestId", ""),
            selected_id,
        )
        # 远程模式下，如果是实例问题，加入黑名单
        if mode == "remote" and selected_id and scheduler:
            scheduler.blacklist_instance(selected_id)
            logger.warning(f"实例 {selected_id} 发生腾讯云 API 错误，已加入黑名单")
        yield sse_event("error", {"stage": "error", "message": f"腾讯云 API 错误: {str(e)}"})

    except Exception as e:
        logger.error("坐席轮转异常: %s", e, exc_info=True)
        yield sse_event("error", {"stage": "error", "message": f"执行失败: {str(e)}"})

    finally:
        if instance_lock is not None and instance_lock.locked():
            instance_lock.release()
