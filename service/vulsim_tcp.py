from __future__ import annotations

import json
import socket
import struct
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

MAGIC = 0x37549260


class VulSimProtocolError(RuntimeError):
    pass


class VulSimBackendError(RuntimeError):
    """后端返回 code != 0"""
    def __init__(self, code: int, msg: str, payload: dict | None = None):
        super().__init__(f"BackendError code={code}, msg={msg}")
        self.code = code
        self.msg = msg
        self.payload = payload or {}


def _json_dumps(obj: Any) -> str:
    # 确保没有多余的空格，保证长度精确
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed while receiving")
        buf.extend(chunk)
    return bytes(buf)


@dataclass
class Arg:
    """构造 args 中的单个参数项"""
    value: Any
    index: Optional[int] = None
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"value": self.value}
        # 按文档：index/name 至少要有一种；若不用则 index=-1 或 name=""
        if self.index is not None:
            d["index"] = int(self.index)
        if self.name is not None:
            d["name"] = str(self.name)
        return d


class VulSimControlClient:
    """
    主控 Socket：半双工（一次 request 对应一次 response），必须串行。
    """

    def __init__(
        self,
        host: str = "211.87.236.13",
        port: int = 17995,
        timeout_s: float = 10.0,
        endian: str = "<",  # 默认小端；若你的后端用网络序(大端)，改成 ">"
    ):
        print(f"[TCP] init VulSimControlClient")
        if endian not in ("<", ">"):
            raise ValueError("endian must be '<' (little) or '>' (big)")
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self.endian = endian

        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()  # 半双工：所有 call 必须互斥

    def connect(self) -> bool:
        """尝试连接，成功返回 True，失败返回 False"""
        if self._sock:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout_s)
            s.connect((self.host, self.port))
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock = s
            print(f"[TCP] Connected to {self.host}:{self.port}")
            return True
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            print(f"[TCP] Connection failed: {e}")
            self._sock = None
            return False

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def _pack(self, payload_obj: Dict[str, Any]) -> bytes:
        payload_str = _json_dumps(payload_obj)
        payload_bytes = payload_str.encode("utf-8")

        # 打印出来，手动数一下是不是和 payload_len 一致
        print(f"[TCP] Sending Payload: {payload_str}")

        # 封装 Header: Magic(4字节) + Length(4字节)
        # 使用 self.endian (默认为 '<')
        header = struct.pack(f"{self.endian}II", MAGIC, len(payload_bytes))

        print(f"[TCP] Pack Info: HeaderHex={header.hex()}, PayloadLen={len(payload_bytes)}")
        return header + payload_bytes

    def _recv_packet(self) -> Dict[str, Any]:
        if not self._sock:
            raise ConnectionError("Not connected")

        # 1. 先读 8 字节头
        try:
            hdr = _recv_exact(self._sock, 8)
        except socket.timeout:
            raise socket.timeout("Read Header Timeout")

        magic, length = struct.unpack(f"{self.endian}II", hdr)

        if magic != MAGIC:
            # 如果 Magic 不对，说明端序反了或者协议完全错了
            raise VulSimProtocolError(f"Bad magic: 0x{magic:08X}")

        # 2. 再根据 length 读 payload
        if length > 10 * 1024 * 1024:  # 保护：如果长度超过10MB，认为是错包
            raise VulSimProtocolError(f"Payload too large: {length}")

        try:
            payload = _recv_exact(self._sock, length)
            # 有些 C++ 后端会在 JSON 后面塞一个 \x00，我们统一处理掉
            payload_str = payload.decode("utf-8").strip('\x00')
            return json.loads(payload_str)
        except socket.timeout:
            raise socket.timeout(f"Read Payload Timeout (expected {length} bytes)")

    def call(self, name: str, args: List[Arg | Dict[str, Any]] | None = None) -> Dict[str, Any]:
        print(f"[TCP] call name is :{name}, args: {args}")

        req_args: List[Dict[str, Any]] = []
        for a in (args or []):
            if isinstance(a, Arg):
                v = a.value
                if isinstance(v, (dict, list)):
                    v = _json_dumps(v)  # 子 JSON 需要字符串化
                req_args.append(Arg(value=v, index=a.index, name=a.name).to_dict())
            elif isinstance(a, dict):
                req_args.append(a)
            else:
                raise TypeError(f"Unsupported arg type: {type(a)}")

        req_obj = {"name": name, "args": req_args}

        for attempt in range(2):
            try:
                if not self._sock:
                    if not self.connect():
                        # 如果连不上，直接报自定义错误，不要让程序崩溃
                        return {"code": -1, "msg": "Cannot connect to server"}

                data = self._pack(req_obj)
                with self._lock:
                    if not self._sock: raise ConnectionError("Lost connection")
                    self._sock.sendall(data)
                    resp = self._recv_packet()

                # 校验返回码
                if int(resp.get("code", -1)) != 0:
                    print(f"[TCP] Backend returned error: {resp.get('msg')}")
                return resp

            except (ConnectionError, socket.timeout, VulSimProtocolError) as e:
                print(f"[TCP] Error during call: {e}")
                self.close()
                if attempt == 0:
                    # 切换端序逻辑保留
                    self.endian = ">" if self.endian == "<" else "<"
                    continue
                return {"code": -1, "msg": f"Communication error: {str(e)}"}
            except Exception as e:
                print(f"[TCP] Unexpected error: {e}")
                return {"code": -1, "msg": "Unexpected internal error"}


class VulSimLogClient:
    """
    日志 Socket：后端异步推送，前端只读。
    典型用法：start() 后持续回调 on_log(dict)
    """

    def __init__(
        self,
        host: str = "211.87.236.13",
        port: int = 17996,
        timeout_s: float = 10.0,
        endian: str = "<",
        on_log: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self.endian = endian
        self.on_log = on_log
        self.on_error = on_error

        self._sock: Optional[socket.socket] = None
        self._stop_evt = threading.Event()
        self._th: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._th and self._th.is_alive():
            return
        self._stop_evt.clear()
        self._th = threading.Thread(target=self._run, name="VulSimLogClient", daemon=True)
        self._th.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _connect(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout_s)
        s.connect((self.host, self.port))
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = s

    def _recv_packet(self) -> Dict[str, Any]:
        assert self._sock is not None
        hdr = _recv_exact(self._sock, 8)
        magic, length = struct.unpack(f"{self.endian}II", hdr)
        if magic != MAGIC:
            raise VulSimProtocolError(f"Bad magic: 0x{magic:08X}")
        payload = _recv_exact(self._sock, length)
        payload = payload.rstrip(b"\x00")  # 去掉尾部 0
        return json.loads(payload.decode("utf-8"))

    def _run(self) -> None:
        try:
            self._connect()
            while not self._stop_evt.is_set():
                msg = self._recv_packet()
                if self.on_log:
                    self.on_log(msg)
        except Exception as e:
            if not self._stop_evt.is_set() and self.on_error:
                self.on_error(e)
