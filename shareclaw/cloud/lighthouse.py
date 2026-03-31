"""Lighthouse 实例操作"""

import logging

from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.lighthouse.v20200324 import models as lh_models

logger = logging.getLogger(__name__)

def _safe_response_text(resp) -> str:
    """安全获取云 API 返回内容，避免日志打印再次报错"""
    to_json_string = getattr(resp, "to_json_string", None)
    if callable(to_json_string):
        try:
            return to_json_string()
        except Exception:
            pass
    return repr(resp)

def check_instance_status(lh_client, instance_id):
    """
    确认 Lighthouse 实例状态正常

    Args:
        lh_client: Lighthouse 客户端
        instance_id: 实例 ID

    Returns:
        dict: 包含 instance_id, state, public_ip 的实例信息

    Raises:
        RuntimeError: 实例不存在或状态异常
    """
    req = lh_models.DescribeInstancesRequest()
    req.InstanceIds = [instance_id]

    try:
        resp = lh_client.DescribeInstances(req)
    except TencentCloudSDKException as e:
        logger.error(
            "查询实例 %s 状态时云 API 异常: code=%s, message=%s, request_id=%s",
            instance_id,
            getattr(e, "code", ""),
            getattr(e, "message", str(e)),
            getattr(e, "requestId", ""),
        )
        raise

    response_text = _safe_response_text(resp)
    instances = resp.InstanceSet

    if not instances:
        logger.warning(
            "实例 %s 健康检查失败: DescribeInstances 返回空实例列表，云 API 返回: %s",
            instance_id,
            response_text,
        )
        raise RuntimeError(f"未找到实例 {instance_id}")

    instance = instances[0]
    instance_info = {
        "instance_id": instance.InstanceId,
        "state": instance.InstanceState,
        "public_ip": instance.PublicAddresses[0] if instance.PublicAddresses else None,
    }

    if instance.InstanceState != "RUNNING":
        logger.warning(
            "实例 %s 健康检查失败: state=%s, public_ip=%s, 云 API 返回: %s",
            instance_id,
            instance_info["state"],
            instance_info["public_ip"],
            response_text,
        )
        raise RuntimeError(
            f"实例 {instance_id} 状态异常: {instance.InstanceState}，需要 RUNNING"
        )

    return instance_info