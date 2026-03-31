"""SSE 工具模块测试"""

from shareclaw.server.sse import sse_event


def test_sse_event_basic():
    """测试基本 SSE 事件构建"""
    result = sse_event("progress", {"stage": "init", "message": "测试"})
    assert result.startswith("event: progress\n")
    assert "data: " in result
    assert result.endswith("\n\n")


def test_sse_event_chinese():
    """测试中文内容不被转义"""
    result = sse_event("error", {"message": "配置错误"})
    assert "配置错误" in result


def test_sse_event_types():
    """测试不同事件类型"""
    for event_type in ("progress", "qrcode", "done", "error"):
        result = sse_event(event_type, {"test": True})
        assert f"event: {event_type}\n" in result
