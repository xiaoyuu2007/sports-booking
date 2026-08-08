#!/usr/bin/env python3
"""
🏟️ 地大体育馆可视化购票系统 (全能版)
"""
import json, sys, threading, webbrowser, traceback, time, os, tempfile
from http.server import ThreadingHTTPServer as HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import date, datetime, timedelta

sys.path.insert(0, ".")
from api_client import VenueClient
import config

OPENID = getattr(config, "OPENID", "你的_OPENID_填在这里")
ORG_ID = getattr(config, "ORG_ID", "2")
TOKEN = getattr(config, "TOKEN", "")
PORT = 8765

_client = None
_client_lock = threading.Lock()


def get_client():
    global _client
    with _client_lock:
        if _client is None:
            _client = VenueClient(token=TOKEN)
            try:
                _client.get_user_info()
            except Exception:
                try:
                    _client.login_by_openid(OPENID, ORG_ID)
                except Exception as e:
                    print(f"登录失败: {e}")
        return _client


def fetch_pay_price(client, nodeid, nl, coords, date_str, user_idserial, max_retries=3):
    """获取支付价格，重试最多 max_retries 次，失败抛出异常"""
    last_err = None
    for attempt in range(max_retries):
        try:
            price_info = client.get_pay_price(nodeid, nl, coords, date_str, user_idserial)
            return int(price_info.get("txamt", 0))
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(0.2)
    raise last_err or Exception("获取价格失败")


class AutoGrabber:
    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self.logs = []
        self.thread = None
        self.success = False

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{ts}] {msg}"
        with self._lock:
            self.logs.append(line)
            if len(self.logs) > 200:
                self.logs = self.logs[-200:]
        print(line)

    def is_running(self):
        with self._lock:
            return self.running

    def set_running(self, val: bool):
        with self._lock:
            if threading.current_thread() == self.thread:
                self.running = val

    def is_success(self):
        with self._lock:
            return self.success

    def set_success(self, val: bool):
        with self._lock:
            self.success = val

    def get_status(self):
        with self._lock:
            return {
                "running": self.running,
                "logs": list(self.logs),
                "success": self.success,
            }

    def start(self, config_data):
        with self._lock:
            if self.running:
                return False, "任务已在运行"
            self.logs = []
            self.success = False
            self.running = True
            self.thread = threading.Thread(target=self._run, args=(config_data,), daemon=True)
            self.thread.start()
            return True, "已启动"

    def stop(self):
        with self._lock:
            self.running = False
        self.log("⏹️ 收到停止指令，正在停止...")

    def _run(self, cfg):
        try:
            self.log("🚀 抢票任务已启动！")
            client = VenueClient(token=TOKEN)
            try:
                uinfo = client.get_user_info()
                user_idserial = uinfo.get("idserial", "")
                self.log(f"✅ 获取用户信息成功: {uinfo.get('username')}")
            except Exception as e:
                self.log(f"❌ 获取用户信息失败: {e}")
                self.set_running(False)
                return

            book_date = cfg.get("date")
            start_time_str = cfg.get("start_time")
            primary = cfg.get("primary", {})
            candidates = cfg.get("candidates", [])
            primary_tries = int(cfg.get("primary_tries", 3))
            retry_interval = float(cfg.get("retry_interval", 0.3))

            if start_time_str:
                target_dt = datetime.strptime(f"{book_date} {start_time_str}", "%Y-%m-%d %H:%M:%S")
                start_dt = target_dt - timedelta(seconds=0.5)
                while self.is_running():
                    now = datetime.now()
                    remaining = (start_dt - now).total_seconds()
                    if remaining <= 0:
                        self.log("🔔 时间到！开始疯狂抢票！")
                        break
                    if remaining > 10:
                        if int(remaining) % 10 == 0:
                            self.log(f"⏳ 等待放票，还剩 {int(remaining)} 秒...")
                        time.sleep(1)
                    else:
                        time.sleep(0.05)

            if not self.is_running():
                return

            attempt = 0
            while self.is_running() and not self.is_success():
                for _ in range(primary_tries):
                    if not self.is_running():
                        break
                    if self._try_target(client, primary, book_date, user_idserial, attempt):
                        self.set_success(True)
                        break
                    attempt += 1
                    time.sleep(retry_interval)

                if self.is_success() or not self.is_running():
                    break

                for cand in candidates:
                    if not self.is_running():
                        break
                    if self._try_target(client, cand, book_date, user_idserial, attempt):
                        self.set_success(True)
                        break
                    attempt += 1
                    time.sleep(retry_interval)

            if self.is_success():
                self.log("🎉 抢票大成功！任务结束。")
            else:
                self.log("⏹️ 抢票已停止。")
        except Exception as e:
            self.log(f"❌ 严重错误: {e}")
            traceback.print_exc()
        finally:
            with self._lock:
                if threading.current_thread() == self.thread:
                    self.running = False

    def _try_target(self, client, target, book_date, user_idserial, attempt):
        nodeid = target.get("nodeid")
        name = target.get("name", nodeid)
        slots = target.get("slots", [])
        min_slots = int(target.get("min_slots", 1))

        try:
            data = client.get_available_times(nodeid, book_date)
            tl = data.get("timeList", [])
            nl = data.get("nodeList", [])
            if not tl:
                return False

            avail = []
            for idx in range(len(tl) - 1):
                slot = tl[idx]
                if str(slot.get("status", "1")) != "0":
                    continue
                t = slot.get("time", "")
                if slots and not any(kw in t for kw in slots):
                    continue
                avail.append((t, idx))

            if len(avail) < min_slots:
                self.log(f"[第{attempt}次] [{name}] 满足条件的时段不足，继续...")
                return False

            selected = avail[:max(min_slots, 1)]
            coords = [f"0-{ti}" for _, ti in selected]
            t_strs = [
                f"{t}-{(tl[ti+1].get('time') if (ti + 1) < len(tl) else '结束')}"
                for t, ti in selected
            ]

            txamt = 0
            try:
                txamt = fetch_pay_price(client, nodeid, nl, coords, book_date, user_idserial, max_retries=3)
            except Exception as pe:
                self.log(f"[第{attempt}次] [{name}] 获取价格失败: {pe}")
                return False

            param = {
                "unitPrice": txamt,
                "nodeList": nl,
                "payprice": txamt,
                "txamt": txamt,
                "isLastDay": False,
                "appointmentDate": book_date,
                "timeList": tl,
                "coordinatesList": coords,
                "booktype": 2,
                "nodeid": nodeid,
                "childrennum": 0,
                "followList": [],
                "payway": "72",
            }
            res = client.create_booking(param)
            if res.get("success"):
                order_id = (res.get("resultData") or {}).get("orderid", "")
                self.log(f"✅ [{name}] 预约成功！时段:{','.join(t_strs)} 订单号:{order_id}")
                return True
            else:
                msg = res.get("message", "未知")
                if "已满" not in msg:
                    self.log(f"[第{attempt}次] [{name}] 失败: {msg}")
                return False
        except Exception as e:
            self.log(f"[第{attempt}次] [{name}] 异常: {e}")
            return False


auto_grabber = AutoGrabber()


def get_html():
    with open(os.path.join(os.path.dirname(__file__), "templates", "index.html"), "r", encoding="utf-8") as f:
        return f.read()


class H(BaseHTTPRequestHandler):
    def ok_json(self, d):
        b = json.dumps(d, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json;charset=utf-8")
        self.send_header("Content-Length", len(b))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = urlparse(self.path)
        path = p.path
        qs = parse_qs(p.query)
        try:
            if path in ("/", "/index.html"):
                b = get_html().encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html;charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.send_header("Content-Length", len(b))
                self.end_headers()
                self.wfile.write(b)
            elif path == "/api/user":
                u = get_client().get_user_info()
                self.ok_json({"success": True, "data": u})
            elif path == "/api/venues":
                n = get_client().get_booking_nodes(booktype="1")
                self.ok_json({"success": True, "data": n})
            elif path == "/api/slots":
                nid = qs.get("nodeid", [""])[0]
                dt = qs.get("date", [""])[0]
                d = get_client().get_available_times(nid, dt)
                self.ok_json({
                    "success": True,
                    "timeList": d.get("timeList", []),
                    "nodeList": d.get("nodeList", []),
                    "priceList": d.get("priceList", []),
                    "conflictList": d.get("conflictList", []),
                    "mintimeselect": d.get("mintimeselect"),
                    "maxtimeselect": d.get("maxtimeselect"),
                    "maxAppointmentNodeNum": d.get("maxAppointmentNodeNum"),
                })
            elif path == "/api/orders":
                o = get_client().get_orders()
                self.ok_json({"success": True, "orders": o})
            elif path == "/api/cancel_info":
                oid = qs.get("id", [""])[0]
                try:
                    res = get_client().check_cancel_count(oid)
                    self.ok_json({"success": True, "message": res.get("message", "")})
                except Exception as e:
                    self.ok_json({"success": False, "message": str(e)})
            elif path == "/api/autograb/status":
                status = auto_grabber.get_status()
                self.ok_json({"success": True, "running": status["running"], "logs": status["logs"]})
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            self.ok_json({"success": False, "message": str(e)})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n)) if n else {}
        path = urlparse(self.path).path
        try:
            if path == "/api/login":
                raw_id = body.get("openid", "").strip()
                import re
                match = re.search(r'openid=([^&]+)', raw_id)
                if match:
                    openid = match.group(1)
                else:
                    openid = raw_id

                if not openid:
                    self.ok_json({"success": False, "message": "无效的 openid"})
                    return

                c = VenueClient()
                token = c.login_by_openid(openid, '2')

                global _client, TOKEN
                with _client_lock:
                    TOKEN = token
                    _client = VenueClient(token=token)

                try:
                    config_path = os.path.join(os.path.dirname(__file__), "config.py")
                    if not os.path.exists(config_path):
                        config_path = "config.py"
                    with open(config_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    config_dir = os.path.dirname(os.path.abspath(config_path))
                    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=config_dir, delete=False) as tf:
                        temp_name = tf.name
                        for line in lines:
                            if line.startswith("TOKEN"):
                                tf.write(f'TOKEN = "{token}"\n')
                            else:
                                tf.write(line)
                    os.replace(temp_name, config_path)
                except Exception as e:
                    print("保存TOKEN到config.py失败:", e)

                self.ok_json({"success": True})
            elif path == "/api/price":
                nid = body["nodeid"]
                dt = body["date"]
                coords = body.get("coords", [])
                childrennum = body.get("childrennum", 0)
                c = get_client()
                fresh = c.get_available_times(nid, dt)
                nl = fresh.get("nodeList", [])
                txamt = 0
                try:
                    uinfo = c.get_user_info()
                    uid = uinfo.get("idserial", "")
                    txamt = fetch_pay_price(c, nid, nl, coords, dt, uid, max_retries=3)
                except Exception as e:
                    print("PRICE ERROR:", e)
                    return self.ok_json({"success": False, "message": str(e)})

                self.ok_json({"success": True, "price": txamt})

            elif path == "/api/book":
                nid = body["nodeid"]
                dt = body["date"]
                coords = body.get("coords", [])
                childrennum = body.get("childrennum", 0)
                c = get_client()
                fresh = c.get_available_times(nid, dt)
                tl = fresh.get("timeList", [])
                nl = fresh.get("nodeList", [])

                txamt = 0
                try:
                    uinfo = c.get_user_info()
                    uid = uinfo.get("idserial", "")
                    txamt = fetch_pay_price(c, nid, nl, coords, dt, uid, max_retries=3)
                except Exception as e:
                    print(f"获取价格失败: {e}")
                    return self.ok_json({"success": False, "message": f"获取价格失败: {e}"})

                param = {
                    "unitPrice": txamt,
                    "nodeList": nl,
                    "payprice": txamt,
                    "txamt": txamt,
                    "isLastDay": False,
                    "appointmentDate": dt,
                    "timeList": tl,
                    "coordinatesList": coords,
                    "booktype": 2,
                    "nodeid": nid,
                    "childrennum": childrennum,
                    "followList": [],
                    "payway": "72",
                }
                r = c.create_booking(param)
                if r.get("success"):
                    rd = r.get("resultData") or {}
                    oid = rd.get("orderid") or rd.get("id", "")
                    self.ok_json({"success": True, "orderid": oid})
                else:
                    self.ok_json({"success": False, "message": r.get("message", "未知错误")})

            elif path == "/api/cancel":
                oid = body.get("id")
                if not oid:
                    return self.ok_json({"success": False, "message": "缺少订单ID"})
                get_client().smart_cancel(oid)
                self.ok_json({"success": True})

            elif path == "/api/autograb/start":
                ok, msg = auto_grabber.start(body)
                self.ok_json({"success": ok, "message": msg})
            elif path == "/api/autograb/stop":
                auto_grabber.stop()
                self.ok_json({"success": True})
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            traceback.print_exc()
            self.ok_json({"success": False, "message": str(e)})


def main():
    print("🏟️  地大体育馆可视化购票系统")
    try:
        get_client().get_user_info()
    except Exception as e:
        print(f"⚠️ 账号未配置或Token失效，请在网页端手动登录: {e}")

    url = f"http://localhost:{PORT}"
    print(f"🌐 服务已启动，容器内已绑定 0.0.0.0:{PORT}")
    try:
        threading.Thread(target=lambda: (time.sleep(0.5), webbrowser.open(url)), daemon=True).start()
    except Exception:
        pass
    server = HTTPServer(("0.0.0.0", PORT), H)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 已停止服务")


if __name__ == "__main__":
    main()
