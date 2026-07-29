"""WebSocket 公共工具：基类、logger 初始化"""
import logging
import sys


def setup_ws_logger(name=None):
    """为 WebSocket 模块创建带 stdout 输出的 logger，防止重复添加 handler。"""
    logger = logging.getLogger(name or __name__)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        _h = logging.StreamHandler(sys.stdout)
        _h.setLevel(logging.INFO)
        _h.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s %(name)s: %(message)s'))
        logger.addHandler(_h)
    return logger


class SafeSendMixin:
    """WebSocket 安全发送并关闭的公共方法，供 OgsWebSocket / OgsSftpWebSocket 复用。"""

    def _safe_send_and_close(self, message, code=1000, reason=''):
        """安全地发送错误消息并关闭 WebSocket：
        1. 先发送文本消息（让前端 onmessage 能收到）
        2. 短暂等待确保消息发出
        3. 发送标准关闭帧（避免 1005）
        """
        try:
            if self.client_socket and not self.client_socket.closed:
                self.client_socket.send(message)
                from gevent import sleep
                sleep(0.05)
                self.client_socket.close(code, reason or message[:30])
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning('_safe_send_and_close error: %s', e)
