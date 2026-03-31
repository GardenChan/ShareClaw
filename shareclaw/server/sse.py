"""SSE（Server-Sent Events）工具"""

import json


def sse_event(event_type, data):
    """
    构建一条 SSE 事件字符串

    Args:
        event_type: 事件类型（如 progress, qrcode, done, error）
        data: 事件数据（会被 JSON 序列化）

    Returns:
        str: SSE 格式的事件字符串
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"
