#!/usr/bin/env python3
"""WP-A スマホ操縦モード 安全テスト（実GPIO・実機・実API不要）。

pilot_server.py はハードウェアを遅延importする設計なので、モジュール import 自体は
gpiozero を触らない。よってフェイクGPIOはWP3同様 sys.modules スタブ方式に倣いつつ、
本テストでは軽量な FakeMotor / FakePanTilt を注入して PilotSafety・WSループを直接叩く。

検証項目（受け入れ条件1）:
  (a) driveコマンド途絶 300ms でモーター自動停止（デッドマン）
  (b) WebSocket切断で即停止（_ws_loop の finally が stop を呼ぶ）
  (c) SIGTERM / SIGINT で stop + STBY off（cleanup）が必ず走る
  (d) 速度指令が pilot.max_speed（既定70）でクランプされる
  (e) 不正JSON・範囲外値でサーバが落ちない（無視 or エラー応答で継続）
  (f) 巨大フレーム長申告（>64KiB）→ 当該接続切断・サーバ継続・モーター停止（追補1）。
      巨大長をそのまま readexactly しないことも、要求バイト数の記録で検証する。
  (g) fakeモードで /stream が multipart/x-mixed-replace の JPEG フレームを配信し、
      クライアント切断でカメラ資源（cap）が解放される（WP-C）。
  (h) 映像系が失敗（カメラ無し・cv2 import例外）しても操縦（drive/head/デッドマン）は
      無傷で動き続ける（WP-C）。

一時ファイルは生成しない（bytecodeキャッシュも無効化）。
実行: python3 gakukoma/tests/test_pilot_safety.py
"""
import os
import sys
import json
import signal
import struct
import asyncio
import importlib.util

sys.dont_write_bytecode = True  # __pycache__ を残さない

CODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PILOT_PATH = os.path.join(CODE_ROOT, "pilot", "pilot_server.py")


def _load_pilot():
    spec = importlib.util.spec_from_file_location("pilot_server", PILOT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pilot_server"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# フェイクハードウェア
# ---------------------------------------------------------------------------
class FakeMotor:
    def __init__(self):
        self.a = 0
        self.b = 0
        self.history = []          # (a, b) の履歴
        self.stby = True
        self.cleaned = False

    def set_motor_a(self, s):
        self.a = s
        self.history.append((self.a, self.b))

    def set_motor_b(self, s):
        self.b = s
        self.history.append((self.a, self.b))

    def cleanup(self):
        self.a = 0
        self.b = 0
        self.stby = False          # STBY off
        self.cleaned = True


class FakePanTilt:
    def __init__(self):
        self.current_pan = 90
        self.current_tilt = 90

    def set_pan_tilt(self, pan, tilt):
        self.current_pan = max(10, min(170, int(pan)))
        self.current_tilt = max(40, min(120, int(tilt)))
        return "ok"


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


# ---------------------------------------------------------------------------
# フェイク WebSocket トランスポート（(b) 用）
# ---------------------------------------------------------------------------
def _client_frame(text):
    """クライアント→サーバのマスク付きテキストフレーム（マスクキー=0）。"""
    payload = text.encode("utf-8")
    n = len(payload)
    assert n < 126
    return bytes([0x81, 0x80 | n]) + b"\x00\x00\x00\x00" + payload


class FakeReader:
    """指定バイト列を返し、尽きたら IncompleteReadError（=切断相当）。"""
    def __init__(self, data):
        self.buf = bytearray(data)

    async def readexactly(self, n):
        if len(self.buf) < n:
            raise asyncio.IncompleteReadError(bytes(self.buf), n)
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    async def read(self, n=-1):
        out = bytes(self.buf)
        self.buf.clear()
        return out


class TrackingReader(FakeReader):
    """readexactly の要求バイト数を記録する FakeReader（(f) 用）。

    フレーム長上限が無い実装だと、巨大申告長をそのまま readexactly(巨大値) して
    しまう（実機ならメモリ枯渇）。その要求自体が発生しないことを検証する。
    """
    def __init__(self, data):
        super().__init__(data)
        self.max_requested = 0

    async def readexactly(self, n):
        self.max_requested = max(self.max_requested, n)
        return await super().readexactly(n)


class FakeWriter:
    def __init__(self):
        self.sent = bytearray()
        self.closed = False

    def write(self, b):
        self.sent += b

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    def get_extra_info(self, _k):
        return "fake"


class StreamFakeWriter(FakeWriter):
    """指定回 drain した後にクライアント切断（ConnectionResetError）を模す（(g) 用）。"""
    def __init__(self, disconnect_after=3):
        super().__init__()
        self.disconnect_after = disconnect_after
        self.drains = 0

    async def drain(self):
        self.drains += 1
        if self.drains > self.disconnect_after:
            raise ConnectionResetError("client gone")


class FakeCap:
    """cv2 の VideoCapture 代役。release されたことを記録する（(g) 資源解放検証）。"""
    def __init__(self):
        self.released = False

    def release(self):
        self.released = True


# ---------------------------------------------------------------------------
# テストランナー
# ---------------------------------------------------------------------------
_results = []


def _check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    _results.append((name, cond, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))


def test_a_deadman(ps):
    """(a) 300ms 途絶で自動停止。"""
    clk = FakeClock()
    motor = FakeMotor()
    s = ps.PilotSafety(motor, FakePanTilt(), max_speed=70,
                       deadman_ms=300, clock=clk)
    s.drive(70, 70)                       # t=0 に指令
    moving = (motor.a == 70 and motor.b == 70)
    clk.t = 0.200                          # 200ms 経過 → まだ停止しない
    triggered_early = s.check_deadman()
    still = (motor.a == 70 and motor.b == 70)
    clk.t = 0.301                          # 301ms 経過 → 停止
    triggered = s.check_deadman()
    stopped = (motor.a == 0 and motor.b == 0)
    _check("(a) drive途絶300msでデッドマン停止",
           moving and not triggered_early and still and triggered and stopped,
           f"moving={moving} early={triggered_early} still={still} "
           f"trig={triggered} stopped={stopped}")


def test_b_disconnect_stops(ps):
    """(b) WebSocket切断（frame途絶）で stop が走る。"""
    motor = FakeMotor()
    s = ps.PilotSafety(motor, FakePanTilt(), max_speed=70, deadman_ms=300)
    server = ps.PilotServer(s, {"port": 0, "max_speed": 70, "deadman_ms": 300})
    reader = FakeReader(_client_frame(json.dumps(
        {"type": "drive", "left": 70, "right": 70})))
    writer = FakeWriter()
    asyncio.run(server._ws_loop(reader, writer))
    drove = any(h == (70, 70) for h in motor.history)   # 途中で走っていた
    stopped = (motor.a == 0 and motor.b == 0)            # 切断後は停止
    _check("(b) WebSocket切断で即停止",
           drove and stopped and writer.closed,
           f"drove={drove} final=({motor.a},{motor.b}) closed={writer.closed}")


def test_c_signal_cleanup(ps):
    """(c) SIGTERM / SIGINT で cleanup（stop + STBY off）が走る。"""
    old_term = signal.getsignal(signal.SIGTERM)
    old_int = signal.getsignal(signal.SIGINT)
    ok_both = True
    detail = []
    try:
        for signame, signum in (("SIGTERM", signal.SIGTERM),
                                 ("SIGINT", signal.SIGINT)):
            motor = FakeMotor()
            s = ps.PilotSafety(motor, FakePanTilt(), max_speed=70, deadman_ms=300)
            s.drive(70, 70)
            ps.install_signal_handlers(s)
            raised = False
            try:
                os.kill(os.getpid(), signum)
            except SystemExit:
                raised = True
            good = (raised and s._cleaned and motor.cleaned
                    and motor.stby is False and motor.a == 0 and motor.b == 0)
            ok_both = ok_both and good
            detail.append(f"{signame}: exit={raised} cleaned={motor.cleaned} "
                          f"stby={motor.stby}")
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)
    _check("(c) SIGTERM/SIGINTでstop+STBY off(cleanup)", ok_both, "; ".join(detail))


def test_d_max_speed_clamp(ps):
    """(d) 速度指令が max_speed(70) にクランプされる。"""
    motor = FakeMotor()
    s = ps.PilotSafety(motor, FakePanTilt(), max_speed=70, deadman_ms=300)
    l, r = s.drive(100, -100)              # 直接
    direct_ok = (l == 70 and r == -70 and motor.a == 70 and motor.b == -70)
    resp = s.handle_command({"type": "drive", "left": 9999, "right": -9999})  # コマンド経由
    cmd_ok = (resp["ok"] and motor.a == 70 and motor.b == -70)
    # config 既定も検証
    cfg = ps.load_pilot_config()
    # WP-D で操縦サーバは 8801 へ移管（8800 は常設ゲートウェイが使用）。
    cfg_ok = (cfg["max_speed"] == 70 and cfg["deadman_ms"] == 300 and cfg["port"] == 8801)
    _check("(d) 速度がmax_speed(70)でクランプ",
           direct_ok and cmd_ok and cfg_ok,
           f"direct=({l},{r}) cmd=({motor.a},{motor.b}) cfg={cfg}")


def test_e_bad_input(ps):
    """(e) 不正JSON・範囲外・不正型でも落ちず、応答して継続。"""
    motor = FakeMotor()
    s = ps.PilotSafety(motor, FakePanTilt(), max_speed=70, deadman_ms=300)
    cases = []

    r1 = s.handle_command("{not valid json")
    cases.append(("bad_json", r1.get("ok") is False and r1.get("error") == "bad_json"))

    r2 = s.handle_command("こんにちは")           # JSONでない文字列
    cases.append(("garbage", r2.get("ok") is False))

    r3 = s.handle_command({"type": "drive", "left": "x", "right": 5})
    cases.append(("bad_drive", r3.get("ok") is False and r3.get("error") == "bad_drive"))

    r4 = s.handle_command({"type": "drive", "left": True, "right": 5})  # bool は拒否
    cases.append(("bool_reject", r4.get("ok") is False))

    r5 = s.handle_command({"type": "wobble"})       # 未知タイプ
    cases.append(("unknown", r5.get("ok") is False and r5.get("error") == "unknown_type"))

    r6 = s.handle_command({"type": "head", "pan": 99999, "tilt": -500})  # 範囲外→クランプ
    cases.append(("head_clamp", r6.get("ok") is True
                  and 10 <= r6.get("pan") <= 170 and 40 <= r6.get("tilt") <= 120))

    r7 = s.handle_command('{"type":"drive","left":50,"right":-50}')      # 正常継続
    cases.append(("still_alive", r7.get("ok") is True and motor.a == 50 and motor.b == -50))

    r8 = s.handle_command(12345)                    # 想定外の型
    cases.append(("weird_type", r8.get("ok") is False))

    all_ok = all(c for _, c in cases)
    _check("(e) 不正入力でサーバが落ちない",
           all_ok, ", ".join(f"{n}={c}" for n, c in cases))


def test_f_oversize_frame(ps):
    """(f) 巨大フレーム長申告 → 当該接続切断・サーバ継続・モーター停止（追補1）。"""
    motor = FakeMotor()
    s = ps.PilotSafety(motor, FakePanTilt(), max_speed=70, deadman_ms=300)
    server = ps.PilotServer(s, {"port": 0, "max_speed": 70, "deadman_ms": 300})
    # 正常な drive で走らせた直後、1GiB を申告する巨大フレーム（127+64bit長）を送る
    huge = (bytes([0x81, 0x80 | 127]) + struct.pack("!Q", 1 << 30)
            + b"\x00\x00\x00\x00" + b"x" * 128)
    reader = TrackingReader(
        _client_frame(json.dumps({"type": "drive", "left": 70, "right": 70})) + huge)
    writer = FakeWriter()
    survived = True
    try:
        asyncio.run(server._ws_loop(reader, writer))
    except Exception:
        survived = False                      # 例外が漏れる=サーバタスクごと死ぬ
    drove = any(h == (70, 70) for h in motor.history)   # 途中までは走っていた
    stopped = (motor.a == 0 and motor.b == 0)            # 切断で即停止
    disconnected = writer.closed                          # 当該接続は切断
    no_huge_read = reader.max_requested <= 64 * 1024      # 巨大readexactlyを発行しない
    # サーバ本体継続の確認: 同じ server インスタンスが新規接続をまだ捌ける
    reader2 = TrackingReader(_client_frame(json.dumps({"type": "ping"})))
    writer2 = FakeWriter()
    try:
        asyncio.run(server._ws_loop(reader2, writer2))
        server_alive = b'"type": "state"' in bytes(writer2.sent)
    except Exception:
        server_alive = False
    _check("(f) 巨大フレーム長申告→接続切断・サーバ継続・停止",
           survived and drove and stopped and disconnected
           and no_huge_read and server_alive,
           f"survived={survived} drove={drove} stopped={stopped} "
           f"disconnected={disconnected} max_read={reader.max_requested} "
           f"server_alive={server_alive}")


def test_g_stream_fake(ps):
    """(g) fake /stream が multipart JPEG を配信し、切断でカメラ資源を解放する。"""
    motor = FakeMotor()
    s = ps.PilotSafety(motor, FakePanTilt(), max_speed=70, deadman_ms=300)
    streamer = ps.CameraStreamer(width=64, height=36, fps=50, quality=60, fake=True)
    server = ps.PilotServer(s, {"port": 0, "max_speed": 70, "deadman_ms": 300},
                            streamer=streamer)
    writer = StreamFakeWriter(disconnect_after=3)   # ヘッダ+2フレーム後に切断
    survived = True
    try:
        asyncio.run(server._serve_stream(writer))
    except Exception:
        survived = False                             # 例外が漏れる=タスク死
    sent = bytes(writer.sent)
    multipart = b"multipart/x-mixed-replace" in sent
    has_boundary = b"--gakukomaframe" in sent
    jpeg_ct = b"Content-Type: image/jpeg" in sent
    has_frame = (b"\xff\xd8" in sent and b"\xff\xd9" in sent)  # SOI/EOI
    released = (streamer.clients == 0)               # 切断でrefcount=0（解放済み）
    closed = writer.closed

    # 実カメラ(cap)相当の資源が release() で確実に閉じることも直接検証する。
    st2 = ps.CameraStreamer(width=64, height=36, fps=10, quality=60, fake=True)
    cap = FakeCap()
    st2._cap = cap
    st2.acquire()
    st2.release()                                    # 0クライアント → cap.release()
    cap_freed = (cap.released and st2._cap is None and st2.clients == 0)

    _check("(g) fake /stream がmultipart JPEG配信・切断で資源解放",
           survived and multipart and has_boundary and jpeg_ct and has_frame
           and released and closed and cap_freed,
           f"survived={survived} multipart={multipart} boundary={has_boundary} "
           f"jpeg_ct={jpeg_ct} frame={has_frame} released={released} "
           f"closed={closed} cap_freed={cap_freed}")


def test_h_stream_failure_isolated(ps):
    """(h) 映像失敗（cv2 import例外・カメラ無し）でも操縦は無傷で継続する。"""
    motor = FakeMotor()
    s = ps.PilotSafety(motor, FakePanTilt(), max_speed=70, deadman_ms=300)
    # 映像系の失敗を決定的に注入する。以前は「dev環境に cv2 無し→失敗」に依存していたが、
    # cv2 と実カメラのある実機では本物のカメラを開いて配信し続け、テストがハングして
    # カメラを占有する事故が起きた（2026-07-11 実機で実害）。環境に依存させない。
    streamer = ps.CameraStreamer(width=640, height=360, fps=10, quality=60, fake=False)
    def _boom():
        raise RuntimeError("injected camera failure")
    streamer.read_jpeg = _boom   # カメラを開くのは read_jpeg（acquireは参照カウントのみ）
    server = ps.PilotServer(s, {"port": 0, "max_speed": 70, "deadman_ms": 300},
                            streamer=streamer)
    writer = FakeWriter()
    stream_survived = True
    try:
        asyncio.run(server._serve_stream(writer))    # 例外を外へ漏らさず終うこと
    except Exception:
        stream_survived = False
    graceful = (stream_survived and writer.closed and streamer.clients == 0)

    # 映像が転けた後でも操縦（drive→切断で停止）が普通に動く。
    reader = FakeReader(_client_frame(json.dumps(
        {"type": "drive", "left": 60, "right": 60})))
    w2 = FakeWriter()
    asyncio.run(server._ws_loop(reader, w2))
    drove = any(h == (60, 60) for h in motor.history)
    stopped_on_disc = (motor.a == 0 and motor.b == 0)

    # デッドマンも無傷（映像と独立）。
    clk = FakeClock()
    m2 = FakeMotor()
    s2 = ps.PilotSafety(m2, FakePanTilt(), max_speed=70, deadman_ms=300, clock=clk)
    s2.drive(70, 70)
    clk.t = 0.301
    deadman_ok = s2.check_deadman() and m2.a == 0 and m2.b == 0

    _check("(h) 映像失敗でも操縦(drive/切断停止/デッドマン)が無傷",
           graceful and drove and stopped_on_disc and deadman_ok,
           f"graceful={graceful} drove={drove} stopped={stopped_on_disc} "
           f"deadman={deadman_ok}")


def main():
    ps = _load_pilot()
    test_a_deadman(ps)
    test_b_disconnect_stops(ps)
    test_c_signal_cleanup(ps)
    test_d_max_speed_clamp(ps)
    test_e_bad_input(ps)
    test_f_oversize_frame(ps)
    test_g_stream_fake(ps)
    test_h_stream_failure_isolated(ps)

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n=== {passed}/{total} checks passed ===")
    if passed != total:
        print("FAILED checks:")
        for name, ok, detail in _results:
            if not ok:
                print(f"  - {name} :: {detail}")
        sys.exit(1)
    print("ALL PASS")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("TEST ERROR:", e)
        sys.exit(2)
