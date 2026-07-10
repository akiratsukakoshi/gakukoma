#!/usr/bin/env python3
"""スマホ操縦モード 常駐サーバ（WP-A）。

スマホブラウザから HTTP でUIを配信し、WebSocket でラジコン感覚の操縦コマンドを
受け取ってキャタピラ（TB6612FNG）と首（PanTiltController）を動かす。

依存を最小化するため WebSocket は Python 標準ライブラリ（asyncio）だけで実装している
（追加pip依存なし）。会場にインターネットが無い前提のため UI も外部参照ゼロの単一HTML。

安全設計:
  - デッドマン: 直近の drive コマンドから deadman_ms（既定300ms）途絶でモーター自動停止。
  - WebSocket切断で即停止。
  - SIGTERM/SIGINT で stop + STBY off（cleanup）が必ず走る。
  - 速度指令は pilot.max_speed（config、既定70）でクランプ。
  - 不正JSON・範囲外値でサーバは落ちない（エラー応答して継続）。
  - WSフレーム長は上限64KiB（MAX_WS_FRAME）。超過申告はプロトコル違反として
    当該接続のみ切断（サーバ本体は継続・切断時は即停止フロー）。

ハードウェアは _build_hardware() で遅延importするため、本モジュールの import 自体は
gpiozero/lgpio を触らない（フェイクGPIOテスト・開発環境実行が容易）。

開発環境での起動（フェイクGPIO）:
    GAKUKOMA_FAKE_GPIO=1 python3 gakukoma/pilot/pilot_server.py
  または
    python3 gakukoma/pilot/pilot_server.py --fake

実機での起動:
    python3 gakukoma/pilot/pilot_server.py
"""

import os
import sys
import json
import time
import signal
import base64
import struct
import hashlib
import asyncio
import threading
import subprocess

# コードルート（motor/・servo/・voice_loop/ がある階層）を import パスに載せる。
CODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CODE_ROOT not in sys.path:
    sys.path.insert(0, CODE_ROOT)

PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML_PATH = os.path.join(PILOT_DIR, "index.html")
# 既存慣例に合わせつつ、開発/実機どちらのレイアウトでも解決できるよう file 相対で組む。
DEFAULT_CONFIG_PATH = os.path.join(CODE_ROOT, "voice_loop", "config.yaml")
SPEAK_SCRIPT = os.path.join(CODE_ROOT, "tools", "speak_text.sh")

DEFAULT_PORT = 8801
DEFAULT_MAX_SPEED = 70.0
DEFAULT_DEADMAN_MS = 300

# 映像ストリーム（任意機能・操縦に必須ではない周縁機能）の既定値。
DEFAULT_STREAM_WIDTH = 640
DEFAULT_STREAM_HEIGHT = 360
DEFAULT_STREAM_FPS = 10.0
DEFAULT_STREAM_QUALITY = 60

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def log(msg):
    print("[pilot] %s" % msg, flush=True)


# ---------------------------------------------------------------------------
# 設定読み込み（pilot セクション）
# ---------------------------------------------------------------------------
def load_pilot_config(config_path=DEFAULT_CONFIG_PATH):
    """config.yaml の pilot セクションを読む。無ければ既定値。"""
    import yaml
    cfg = {}
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        log("config not found (%s) — 既定値を使用" % config_path)
    pilot = cfg.get("pilot") or {}
    return {
        "port": int(pilot.get("port", DEFAULT_PORT)),
        "max_speed": float(pilot.get("max_speed", DEFAULT_MAX_SPEED)),
        "deadman_ms": int(pilot.get("deadman_ms", DEFAULT_DEADMAN_MS)),
        "stream_width": int(pilot.get("stream_width", DEFAULT_STREAM_WIDTH)),
        "stream_height": int(pilot.get("stream_height", DEFAULT_STREAM_HEIGHT)),
        "stream_fps": float(pilot.get("stream_fps", DEFAULT_STREAM_FPS)),
        "stream_quality": int(pilot.get("stream_quality", DEFAULT_STREAM_QUALITY)),
    }


# ---------------------------------------------------------------------------
# 安全コア（ハードウェア非依存・単体テスト可能）
# ---------------------------------------------------------------------------
class PilotSafety:
    """操縦の安全ロジック。motor/pantilt を注入して使う。ネットワーク層に依存しない。"""

    def __init__(self, motor, pantilt, max_speed=DEFAULT_MAX_SPEED,
                 deadman_ms=DEFAULT_DEADMAN_MS, clock=time.monotonic):
        self.motor = motor
        self.pantilt = pantilt
        self.max_speed = float(max_speed)
        self.deadman_s = deadman_ms / 1000.0
        self._clock = clock
        self._last_drive = None
        self._moving = False
        self._cleaned = False
        self._lock = threading.Lock()
        self.current_pan = int(getattr(pantilt, "current_pan", 90))
        self.current_tilt = int(getattr(pantilt, "current_tilt", 90))

    # --- 値の検証・クランプ ------------------------------------------------
    @staticmethod
    def _to_number(v):
        """数値なら float、それ以外（bool含む）は None。"""
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        return None

    def _clamp_speed(self, v):
        v = max(-100.0, min(100.0, v))          # まず物理レンジ
        return max(-self.max_speed, min(self.max_speed, v))  # 次に max_speed

    # --- 動作 --------------------------------------------------------------
    def drive(self, left, right):
        """左右キャタピラ速度を設定し、デッドマン用に最終指令時刻を更新する。"""
        l = self._clamp_speed(left)
        r = self._clamp_speed(right)
        with self._lock:
            self.motor.set_motor_a(l)   # A = 左
            self.motor.set_motor_b(r)   # B = 右
            self._last_drive = self._clock()
            self._moving = (l != 0 or r != 0)
        return l, r

    def head(self, pan, tilt):
        with self._lock:
            self.pantilt.set_pan_tilt(pan, tilt)
            self.current_pan = int(getattr(self.pantilt, "current_pan", pan))
            self.current_tilt = int(getattr(self.pantilt, "current_tilt", tilt))
        return self.current_pan, self.current_tilt

    def stop(self):
        with self._lock:
            self.motor.set_motor_a(0)
            self.motor.set_motor_b(0)
            self._moving = False
            self._last_drive = None

    def check_deadman(self, now=None):
        """直近 drive から deadman_s を超えて途絶していたら停止。停止したら True。"""
        with self._lock:
            if not self._moving or self._last_drive is None:
                return False
            t = self._clock() if now is None else now
            if t - self._last_drive <= self.deadman_s:
                return False
        self.stop()
        return True

    def cleanup(self):
        """停止 + STBY off。SIGTERM/SIGINT や終了時に必ず一度だけ走る。"""
        if self._cleaned:
            return
        self._cleaned = True
        try:
            self.stop()
        finally:
            try:
                self.motor.cleanup()
            except Exception as e:  # noqa: BLE001 — 終了処理は握りつぶす
                log("motor.cleanup failed (ignored): %s" % e)

    # --- コマンド処理（絶対に例外を投げない）-------------------------------
    def _resp(self, error=None):
        r = {
            "type": "state",
            "ok": error is None,
            "pan": self.current_pan,
            "tilt": self.current_tilt,
        }
        if error:
            r["error"] = error
        return r

    def handle_command(self, message):
        """str(JSON) または dict を受け取り、応答 dict を返す。例外は投げない。"""
        try:
            if isinstance(message, (bytes, bytearray)):
                message = message.decode("utf-8", "replace")
            if isinstance(message, str):
                try:
                    data = json.loads(message)
                except ValueError:
                    return self._resp(error="bad_json")
            elif isinstance(message, dict):
                data = message
            else:
                return self._resp(error="bad_type")
            if not isinstance(data, dict):
                return self._resp(error="not_object")

            mtype = data.get("type")
            if mtype == "drive":
                l = self._to_number(data.get("left"))
                r = self._to_number(data.get("right"))
                if l is None or r is None:
                    return self._resp(error="bad_drive")
                self.drive(l, r)
                return self._resp()
            elif mtype == "head":
                pan = self._to_number(data.get("pan"))
                tilt = self._to_number(data.get("tilt"))
                if pan is None or tilt is None:
                    return self._resp(error="bad_head")
                self.head(pan, tilt)
                return self._resp()
            elif mtype == "stop":
                self.stop()
                return self._resp()
            elif mtype == "ping":
                return self._resp()
            else:
                return self._resp(error="unknown_type")
        except Exception as e:  # noqa: BLE001 — 何が来てもサーバは落とさない
            return self._resp(error="exception:%s" % type(e).__name__)


# ---------------------------------------------------------------------------
# シグナルハンドラ（テスト可能な形で install）
# ---------------------------------------------------------------------------
def install_signal_handlers(safety, extra=None):
    """SIGTERM/SIGINT で safety.cleanup() を必ず通し、SystemExit を送出する。"""
    def _handler(signum, frame):
        try:
            safety.cleanup()
        finally:
            if extra is not None:
                try:
                    extra()
                except Exception:
                    pass
            raise SystemExit(0)
    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
    return _handler


# ---------------------------------------------------------------------------
# WebSocket フレーム（RFC6455 の必要最小限）
# ---------------------------------------------------------------------------
# 受信フレーム長の上限（64KiB）。操縦コマンドは高々数百バイトであり、
# 巨大長の申告はバグったクライアント/悪意ある接続とみなしプロトコル違反で切断する
# （無制限に readexactly するとメモリを食い潰しサーバごと落ち得るため）。
MAX_WS_FRAME = 64 * 1024


class WSProtocolError(Exception):
    """WebSocketプロトコル違反（当該接続のみ切断。サーバ本体は継続）。"""


def encode_frame(payload, opcode=0x1):
    """サーバ→クライアント（マスク無し）フレームを組む。"""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    header = bytearray([0x80 | opcode])
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header += struct.pack("!H", n)
    else:
        header.append(127)
        header += struct.pack("!Q", n)
    return bytes(header) + payload


async def read_frame(reader):
    """クライアント→サーバ フレームを1つ読む。(opcode, payload) を返す。EOFは例外送出。

    申告長が MAX_WS_FRAME(64KiB) を超える場合は payload を読む前に
    WSProtocolError を送出する（呼び出し側で当該接続を切断する）。
    """
    hdr = await reader.readexactly(2)
    b2 = hdr[1]
    opcode = hdr[0] & 0x0F
    masked = b2 & 0x80
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack("!H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", await reader.readexactly(8))[0]
    if length > MAX_WS_FRAME:
        raise WSProtocolError("frame too large: %d bytes (max %d)"
                              % (length, MAX_WS_FRAME))
    mask = await reader.readexactly(4) if masked else None
    payload = await reader.readexactly(length) if length else b""
    if mask:
        payload = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))
    return opcode, payload


async def read_http_request(reader):
    """HTTPリクエスト行とヘッダを読む。"""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = await reader.read(1024)
        if not chunk:
            break
        data += chunk
        if len(data) > 65536:
            break
    head = data.split(b"\r\n\r\n", 1)[0]
    lines = head.decode("latin1").split("\r\n")
    request_line = lines[0] if lines else ""
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return request_line, headers


# ---------------------------------------------------------------------------
# 映像ストリーム（任意機能）
#
# 設計方針:
#   - 操縦（drive/head/デッドマン/切断停止）とは完全に独立。映像が失敗しても操縦は無傷。
#   - 撮影・JPEGエンコードはブロッキングなので必ず executor スレッドで行い、
#     asyncio イベントループ（=操縦の即応性）をブロックしない。
#   - クライアント参照カウント。0 になったらカメラ資源を解放する。
#   - fakeモードでは cv2・実カメラを一切触らず、コード内生成の静的テストJPEGを返す。
#   - 帯域: 640x360・約8〜10fps・JPEG品質60 が目安（config.yaml pilot: で調整可）。
# ---------------------------------------------------------------------------
# 標準ベースライン輝度ハフマン表（JPEG Annex K）。fakeテストJPEG生成に使う。
_JPEG_DC_BITS = bytes([0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0])
_JPEG_DC_VALS = bytes(range(12))
_JPEG_AC_BITS = bytes([0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7d])
_JPEG_AC_VALS = bytes([
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
    0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xa1, 0x08,
    0x23, 0x42, 0xb1, 0xc1, 0x15, 0x52, 0xd1, 0xf0, 0x24, 0x33, 0x62, 0x72,
    0x82, 0x09, 0x0a, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2a, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3a, 0x43, 0x44, 0x45,
    0x46, 0x47, 0x48, 0x49, 0x4a, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
    0x5a, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6a, 0x73, 0x74, 0x75,
    0x76, 0x77, 0x78, 0x79, 0x7a, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
    0x8a, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0xa2, 0xa3,
    0xa4, 0xa5, 0xa6, 0xa7, 0xa8, 0xa9, 0xaa, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6,
    0xb7, 0xb8, 0xb9, 0xba, 0xc2, 0xc3, 0xc4, 0xc5, 0xc6, 0xc7, 0xc8, 0xc9,
    0xca, 0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda, 0xe1, 0xe2,
    0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea, 0xf1, 0xf2, 0xf3, 0xf4,
    0xf5, 0xf6, 0xf7, 0xf8, 0xf9, 0xfa])


def _build_fake_jpeg():
    """依存ゼロで有効なベースラインJPEG（8x8・中間グレー単色）をバイト列で組む。

    fakeモードで実カメラ/cv2 を触らずに `/stream` を検証・動作させるためのもの。
    単一8x8ブロック: DC差分=0(カテゴリ0="00") + AC EOB("1010") = "001010"、
    バイト境界へ "11" で詰めて "00101011"=0x2b。
    """
    qt = bytes([1] * 64)                     # 量子化テーブル（全1 = 高品質）
    soi = b"\xff\xd8"
    dqt = b"\xff\xdb" + struct.pack("!H", 2 + 1 + 64) + b"\x00" + qt
    sof = (b"\xff\xc0" + struct.pack("!H", 2 + 1 + 2 + 2 + 1 + 3)
           + b"\x08" + struct.pack("!H", 8) + struct.pack("!H", 8)
           + b"\x01" + b"\x01\x11\x00")
    dht_dc = (b"\xff\xc4" + struct.pack("!H", 2 + 1 + 16 + len(_JPEG_DC_VALS))
              + b"\x00" + _JPEG_DC_BITS + _JPEG_DC_VALS)
    dht_ac = (b"\xff\xc4" + struct.pack("!H", 2 + 1 + 16 + len(_JPEG_AC_VALS))
              + b"\x10" + _JPEG_AC_BITS + _JPEG_AC_VALS)
    sos = (b"\xff\xda" + struct.pack("!H", 2 + 1 + 2 + 3)
           + b"\x01" + b"\x01\x00" + b"\x00\x3f\x00")
    entropy = bytes([0x2b])
    eoi = b"\xff\xd9"
    return soi + dqt + sof + dht_dc + dht_ac + sos + entropy + eoi


class CameraStreamer:
    """MJPEG用のカメラ資源管理。参照カウントで開閉し、撮影は executor で行う前提。

    read_jpeg() は撮影スレッド（executor）から呼ばれ、ブロッキング可。
    例外は投げてよい（呼び出し側の /stream ハンドラが握って接続だけ閉じる）。
    """

    def __init__(self, width, height, fps, quality, fake=False, device=0):
        self.width = int(width)
        self.height = int(height)
        self.fps = max(1.0, float(fps))
        self.quality = max(1, min(100, int(quality)))
        self.fake = bool(fake)
        self.device = int(device)
        self.frame_interval = 1.0 / self.fps
        self._lock = threading.Lock()
        self._clients = 0
        self._cap = None
        self._fake_jpeg = _build_fake_jpeg() if fake else None

    # --- 参照カウント ------------------------------------------------------
    def acquire(self):
        with self._lock:
            self._clients += 1

    def release(self):
        """クライアント離脱。0 になったらカメラを解放する。"""
        with self._lock:
            self._clients -= 1
            if self._clients <= 0:
                self._clients = 0
                self._close_locked()

    @property
    def clients(self):
        with self._lock:
            return self._clients

    def is_open(self):
        with self._lock:
            return self._cap is not None

    # --- カメラ本体（実機のみ・cv2遅延import）-----------------------------
    def _close_locked(self):
        cap = self._cap
        self._cap = None
        if cap is not None:
            try:
                cap.release()
            except Exception as e:  # noqa: BLE001
                log("camera release failed (ignored): %s" % e)

    def _open_locked(self):
        import cv2  # 実機のみ。fakeでは決してここへ来ない。
        cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            raise RuntimeError("camera open failed (device %d)" % self.device)
        # 既存 camera/capture.py の慣例: MJPEG FOURCC→解像度の順で設定。
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap = cap
        return cap

    def read_jpeg(self):
        """1フレーム撮影しJPEGバイト列を返す。取得不能なら None。executorで実行。"""
        if self.fake:
            return self._fake_jpeg
        import cv2
        with self._lock:
            if self._clients <= 0:
                return None
            cap = self._cap or self._open_locked()
            ok, frame = cap.read()
            if not ok or frame is None:
                return None
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height))
            ok, buf = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
            if not ok:
                return None
            return buf.tobytes()


# ---------------------------------------------------------------------------
# サーバ
# ---------------------------------------------------------------------------
class PilotServer:
    def __init__(self, safety, config, streamer=None):
        self.safety = safety
        self.config = config
        self.streamer = streamer
        self._current_writer = None  # 同時接続1クライアント（後勝ち）

    async def _serve_index(self, writer):
        try:
            with open(INDEX_HTML_PATH, "rb") as f:
                body = f.read()
            status = b"200 OK"
        except OSError:
            body = b"index.html not found"
            status = b"500 Internal Server Error"
        head = (b"HTTP/1.1 " + status + b"\r\n"
                b"Content-Type: text/html; charset=utf-8\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                b"Cache-Control: no-store\r\n"
                b"Connection: close\r\n\r\n")
        writer.write(head + body)
        try:
            await writer.drain()
        except Exception:
            pass
        writer.close()

    async def _serve_stream(self, writer):
        """GET /stream — multipart/x-mixed-replace で JPEG を流し続ける。

        映像は任意機能。ここで何が起きても操縦系（別タスク・別接続）は無傷。
        撮影/エンコードは executor で行い、イベントループをブロックしない。
        クライアント切断や取得失敗で必ず streamer.release()（カメラ資源解放）へ抜ける。
        """
        streamer = self.streamer
        if streamer is None:
            # 映像無効環境: 503 を返す（UI側 <img> の onerror が窓を隠す）。
            body = b"stream disabled"
            head = (b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Type: text/plain; charset=utf-8\r\n"
                    b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                    b"Cache-Control: no-store\r\n"
                    b"Connection: close\r\n\r\n")
            writer.write(head + body)
            try:
                await writer.drain()
            except Exception:
                pass
            try:
                writer.close()
            except Exception:
                pass
            return

        boundary = b"gakukomaframe"
        head = (b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: multipart/x-mixed-replace; boundary="
                + boundary + b"\r\n"
                b"Cache-Control: no-store, no-cache, must-revalidate\r\n"
                b"Pragma: no-cache\r\n"
                b"Connection: close\r\n\r\n")
        writer.write(head)
        try:
            await writer.drain()
        except Exception:
            try:
                writer.close()
            except Exception:
                pass
            return

        loop = asyncio.get_event_loop()
        interval = streamer.frame_interval
        streamer.acquire()
        try:
            while True:
                try:
                    jpeg = await loop.run_in_executor(None, streamer.read_jpeg)
                except Exception as e:  # noqa: BLE001 — 映像失敗は操縦に波及させない
                    log("stream capture failed (ignored): %s" % e)
                    break
                if not jpeg:
                    # カメラ無し/取得失敗 → ストリーム終了（操縦は無傷）。
                    break
                part = (b"--" + boundary + b"\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(jpeg)).encode()
                        + b"\r\n\r\n" + jpeg + b"\r\n")
                writer.write(part)
                try:
                    await writer.drain()
                except (ConnectionError, OSError):
                    break                    # クライアント切断
                except Exception:
                    break
                await asyncio.sleep(interval)
        finally:
            streamer.release()               # カメラ資源解放（0クライアントで close）
            try:
                writer.close()
            except Exception:
                pass

    async def handle_conn(self, reader, writer):
        try:
            request_line, headers = await read_http_request(reader)
        except Exception:
            try:
                writer.close()
            except Exception:
                pass
            return
        if headers.get("upgrade", "").lower() != "websocket":
            # 非WebSocketのHTTP: パスで振り分け（/stream は映像、他はUI）。
            path = "/"
            parts = request_line.split(" ")
            if len(parts) >= 2:
                path = parts[1]
            if path.split("?", 1)[0] == "/stream":
                await self._serve_stream(writer)
            else:
                await self._serve_index(writer)
            return
        key = headers.get("sec-websocket-key", "")
        accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        resp = ("HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Accept: " + accept + "\r\n\r\n")
        writer.write(resp.encode())
        await writer.drain()
        await self._ws_loop(reader, writer)

    async def _ws_loop(self, reader, writer):
        # 後勝ち: 既存クライアントに切断通知して閉じる。
        prev = self._current_writer
        if prev is not None and prev is not writer:
            try:
                prev.write(encode_frame(json.dumps({"type": "kicked"})))
                prev.write(encode_frame(b"", 0x8))  # close
                await prev.drain()
                prev.close()
            except Exception:
                pass
        self._current_writer = writer
        log("client connected: %s" % (writer.get_extra_info("peername"),))
        try:
            while True:
                try:
                    opcode, payload = await read_frame(reader)
                except WSProtocolError as e:
                    # プロトコル違反（巨大フレーム等）→ 当該接続のみ切断。
                    # finally で即停止フロー（stop）を通る。サーバ本体は継続。
                    log("protocol violation → disconnect: %s" % e)
                    break
                except (asyncio.IncompleteReadError, ConnectionError, OSError):
                    break
                if opcode == 0x8:            # close
                    break
                elif opcode == 0x9:          # ping → pong
                    writer.write(encode_frame(payload, 0xA))
                    await writer.drain()
                    continue
                elif opcode == 0xA:          # pong
                    continue
                elif opcode in (0x1, 0x2):   # text / binary
                    resp = self.safety.handle_command(
                        payload.decode("utf-8", "replace"))
                    try:
                        writer.write(encode_frame(json.dumps(resp)))
                        await writer.drain()
                    except Exception:
                        break
                # それ以外の opcode は無視して継続
        finally:
            if self._current_writer is writer:
                self._current_writer = None
                self.safety.stop()          # WebSocket切断 → 即停止
                log("client disconnected → stop")
            try:
                writer.close()
            except Exception:
                pass

    async def _deadman_loop(self):
        interval = self.safety.deadman_s / 3.0 if self.safety.deadman_s > 0 else 0.05
        interval = max(0.02, min(0.05, interval))
        while True:
            await asyncio.sleep(interval)
            if self.safety.check_deadman():
                log("deadman → stop（指令途絶）")

    async def run(self):
        server = await asyncio.start_server(
            self.handle_conn, "0.0.0.0", self.config["port"])
        asyncio.create_task(self._deadman_loop())
        log("listening on 0.0.0.0:%d  (UI: http://<pi-host>:%d/)"
            % (self.config["port"], self.config["port"]))
        async with server:
            await server.serve_forever()


# ---------------------------------------------------------------------------
# ハードウェア構築（実機 / フェイク）
# ---------------------------------------------------------------------------
class _FakeMotor:
    """開発環境用。値が変わった時だけログするので 10Hz drive でもログが埋まらない。"""
    def __init__(self):
        self.a = 0
        self.b = 0
        self.stby = True

    def set_motor_a(self, s):
        if s != self.a:
            log("motor A(左)=%s" % s)
        self.a = s

    def set_motor_b(self, s):
        if s != self.b:
            log("motor B(右)=%s" % s)
        self.b = s

    def stop(self):
        self.set_motor_a(0)
        self.set_motor_b(0)

    def cleanup(self):
        self.stop()
        self.stby = False
        log("motor cleanup（STBY off）")


class _FakePanTilt:
    def __init__(self):
        self.current_pan = 90
        self.current_tilt = 90

    def set_pan_tilt(self, pan, tilt):
        self.current_pan = max(10, min(170, int(pan)))
        self.current_tilt = max(40, min(120, int(tilt)))
        log("pantilt pan=%s tilt=%s" % (self.current_pan, self.current_tilt))
        return "ok"


def _build_hardware(fake):
    if fake:
        log("FAKE GPIO モードで起動")
        return _FakeMotor(), _FakePanTilt()
    from motor.tb6612_ctrl import TB6612FNG
    from servo.pan_tilt import PanTiltController
    return TB6612FNG(), PanTiltController()


def _speak(text):
    """起動時の一言。失敗しても操縦は継続。"""
    try:
        subprocess.Popen(
            ["/bin/bash", SPEAK_SCRIPT, text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:  # noqa: BLE001
        log("TTS failed (ignored): %s" % e)


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    fake = bool(os.environ.get("GAKUKOMA_FAKE_GPIO")) or "--fake" in argv
    config = load_pilot_config()
    motor, pantilt = _build_hardware(fake)
    safety = PilotSafety(
        motor, pantilt,
        max_speed=config["max_speed"], deadman_ms=config["deadman_ms"])
    install_signal_handlers(safety)
    _speak("操縦モードだよ。スマホで動かしてね")
    streamer = CameraStreamer(
        width=config["stream_width"], height=config["stream_height"],
        fps=config["stream_fps"], quality=config["stream_quality"], fake=fake)
    server = PilotServer(safety, config, streamer=streamer)
    try:
        asyncio.run(server.run())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        safety.cleanup()


if __name__ == "__main__":
    main()
