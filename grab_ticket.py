#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║      地大体育馆自动抢票脚本  v2.0                    ║
╠══════════════════════════════════════════════════════╣
║  功能:                                               ║
║    · 到点自动发起请求，疯狂抢票                      ║
║    · 支持主要场地 + 候选列表（主满自动切候选）        ║
║    · 自动获取真实价格，避免"支付金额异常"             ║
╠══════════════════════════════════════════════════════╣
║  快速使用:                                           ║
║    1. 修改 config.py 设置目标场地和时间              ║
║    2. source .venv/bin/activate                      ║
║    3. python3 grab_ticket.py                         ║
║                                                      ║
║  或一行命令:                                         ║
║    .venv/bin/python3 grab_ticket.py                  ║
╚══════════════════════════════════════════════════════╝
"""
import sys
import time
import argparse
from datetime import date, datetime, timedelta
from typing import Optional

sys.path.insert(0, ".")
from api_client import VenueClient
import config

# ══════════════════════════════════════════════════════
#   日志工具
# ══════════════════════════════════════════════════════

def _ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def log_info(msg):  print(f"[{_ts()}] ℹ️  {msg}", flush=True)
def log_ok(msg):    print(f"[{_ts()}] ✅ {msg}", flush=True)
def log_warn(msg):  print(f"[{_ts()}] ⚠️  {msg}", flush=True)
def log_err(msg):   print(f"[{_ts()}] ❌ {msg}", flush=True)
def log_grab(msg):  print(f"[{_ts()}] 🚀 {msg}", flush=True)


def notify(title: str, body: str):
    """成功后发通知"""
    method = getattr(config, "NOTIFY_METHOD", "print")
    if method == "bark":
        bark_key = getattr(config, "BARK_KEY", "")
        if bark_key:
            try:
                import urllib.request, urllib.parse
                url = f"https://api.day.app/{bark_key}/{urllib.parse.quote(title)}/{urllib.parse.quote(body)}"
                urllib.request.urlopen(url, timeout=5)
            except Exception as e:
                log_warn(f"Bark 推送失败: {e}")
    print(f"\n{'='*54}")
    print(f"  🎉 {title}")
    print(f"  {body}")
    print(f"{'='*54}\n", flush=True)


# ══════════════════════════════════════════════════════
#   等待到放票时间
# ══════════════════════════════════════════════════════

def wait_until(time_str: str, advance: float = 0.5):
    """
    等待到 time_str 时间（提前 advance 秒开始抢）。
    time_str 格式: "HH:MM:SS"
    """
    if not time_str:
        return

    today = date.today()
    target_dt = datetime.strptime(f"{today} {time_str}", "%Y-%m-%d %H:%M:%S")
    start_dt  = target_dt - timedelta(seconds=advance)
    now = datetime.now()

    if start_dt <= now:
        log_info("已过预定开始时间，立即开始抢票")
        return

    wait_secs = (start_dt - now).total_seconds()
    log_info(f"等待放票: {time_str}（提前 {advance}s 开始），"
             f"还需等待 {wait_secs/3600:.1f} 小时 / {wait_secs:.0f} 秒")

    # 距离开始时间 > 10s 时粗等，最后 10s 逐帧倒计时
    while True:
        now = datetime.now()
        remaining = (start_dt - now).total_seconds()
        if remaining <= 0:
            break
        if remaining <= 10:
            print(f"\r  ⏳ {remaining:.2f}s ...", end="", flush=True)
            time.sleep(0.05)
        else:
            time.sleep(min(remaining - 10, 1.0))

    print()
    log_grab("🔔 时间到！开始疯狂抢票！")


# ══════════════════════════════════════════════════════
#   单个场地抢票逻辑
# ══════════════════════════════════════════════════════

def _find_slots(time_list: list, want_slots: list) -> list:
    """
    从 timeList 中找可预约的时间段。
    want_slots: 期望时间关键词列表（如 ["14:00","15:00"]），空 = 任意。
    返回: [(time_str, index), ...]
    """
    result = []
    for idx, slot in enumerate(time_list):
        if str(slot.get("status", "1")) != "0":
            continue
        t = slot.get("time", "")
        if want_slots and not any(kw in t for kw in want_slots):
            continue
        result.append((t, idx))
    return result


def try_grab_target(client: VenueClient, target: dict,
                    book_date: str, user_idserial: str) -> Optional[str]:
    """
    尝试抢一个场地。
    Returns:
        订单号字符串（成功）或 None（未抢到）
    Raises:
        Exception: 网络/解析错误（让上层决定是否重试）
    """
    nodeid    = target["nodeid"]
    name      = target["name"]
    slots     = target.get("slots", [])
    min_slots = target.get("min_slots", 1)

    # 1. 查询可用时间段
    data      = client.get_available_times(nodeid, book_date)
    time_list = data.get("timeList", [])
    node_list = data.get("nodeList", [])

    if not time_list:
        return None  # 没有时间段数据，稍后重试

    avail = _find_slots(time_list, slots)

    if len(avail) < min_slots:
        return None  # 可用数量不足

    selected = avail[:max(min_slots, 1)]
    coords   = [f"0-{ti}" for _, ti in selected]
    t_strs   = [t for t, _ in selected]

    # 2. 获取真实价格（关键：必须和服务器一致，否则报"支付金额异常"）
    txamt = 0
    if node_list and user_idserial:
        try:
            price_info = client.get_pay_price(
                nodeid=nodeid,
                node_list=node_list,
                reserve_times=coords,
                reserve_date=book_date,
                user_idserial=user_idserial,
            )
            txamt = int(price_info.get("txamt", 0))
        except Exception:
            txamt = 0  # 获取失败就用 0 试一下

    # 3. 提交预约
    param = {
        "unitPrice":       txamt,
        "nodeList":        node_list,
        "payprice":        txamt,
        "txamt":           txamt,
        "isLastDay":       False,
        "appointmentDate": book_date,
        "timeList":        time_list,
        "coordinatesList": coords,
        "booktype":        2,
        "nodeid":          nodeid,
        "childrennum":     0,
        "followList":      [],
        "payway":          "72",
    }

    result = client.create_booking(param)

    if result.get("success"):
        rd       = result.get("resultData") or {}
        order_id = rd.get("orderid") or rd.get("id", "（未知）")
        price_str = f"{txamt/100:.2f}元" if txamt > 0 else "免费"
        log_ok(f"🎉 [{name}] 预约成功！"
               f"时段: {', '.join(t_strs)}  价格: {price_str}  订单: {order_id}")
        notify(
            f"体育馆预约成功！[{name}]",
            f"日期: {book_date}\n时间: {', '.join(t_strs)}\n"
            f"价格: {price_str}\n订单: {order_id}"
        )
        return order_id

    # 服务器返回失败（时段被抢走、时间窗口未开、额度不足……）
    msg = result.get("message", "未知")
    # 只有明确"时段已满"才返回 None，其他异常原因直接透传
    if any(kw in msg for kw in ["已满", "已预约", "无法预约", "不可预约"]):
        return None
    # 时间窗口未开、限额等情况 → 也返回 None 继续重试
    return None


# ══════════════════════════════════════════════════════
#   主抢票循环：主场地 + 候选轮换
# ══════════════════════════════════════════════════════

class MultiTargetGrabber:
    def __init__(self, token: str, book_date: str,
                 primary: dict, candidates: list,
                 primary_tries: int = 3,
                 retry_interval: float = 0.3,
                 max_retries: int = 0):
        self.client       = VenueClient(token=token,
                                        timeout=getattr(config, "REQUEST_TIMEOUT", 10))
        self.book_date    = book_date
        self.primary      = primary
        self.candidates   = candidates
        self.primary_tries = primary_tries
        self.retry_interval= retry_interval
        self.max_retries  = max_retries

        self.user_idserial = ""
        self.attempt       = 0
        self.success       = False

    def init(self):
        """登录并获取用户 idserial"""
        log_info("初始化：获取用户信息…")
        try:
            info = self.client.get_user_info()
            self.user_idserial = info.get("idserial", "")
            log_ok(f"用户: {info.get('username')}  idserial: {self.user_idserial}")
        except Exception as e:
            log_warn(f"获取用户信息失败（将继续）: {e}")

    def _try_one(self, target: dict) -> bool:
        """尝试抢一个目标，返回是否成功"""
        self.attempt += 1
        name = target["name"]
        try:
            order_id = try_grab_target(
                self.client, target, self.book_date, self.user_idserial
            )
            if order_id is not None:
                self.success = True
                return True
            log_warn(f"[第{self.attempt}次] [{name}] 暂无可用时段，继续…")
        except Exception as e:
            log_warn(f"[第{self.attempt}次] [{name}] 请求异常: {e}")
        return False

    def run(self):
        """
        主循环：
          · 先对主目标连续尝试 primary_tries 次
          · 若仍未成功，按顺序各试一次候选
          · 如此轮换，直到成功或达到 max_retries
        """
        all_targets = self.candidates  # 候选列表

        # 打印任务摘要
        slots_str = ", ".join(self.primary.get("slots", [])) or "任意"
        print(f"""
╔══════════════════════════════════════════════════════╗
║  🏟️  地大体育馆自动抢票  v2.0                        ║
╠══════════════════════════════════════════════════════╣
║  主要目标 : {self.primary['name']:<41}║
║  期望时段 : {slots_str:<41}║
║  预约日期 : {self.book_date:<41}║
║  候选数量 : {len(all_targets)} 个{'':<38}║
║  重试间隔 : {self.retry_interval}s{'':<39}║
╚══════════════════════════════════════════════════════╝
""")
        if all_targets:
            for c in all_targets:
                log_info(f"  候选: [{c['name']}] {c['nodeid']}"
                         f"  期望时段: {c.get('slots') or '任意'}")
            print()

        log_grab(f"开始抢票！主目标每轮尝试 {self.primary_tries} 次后切换候选")

        while not self.success:
            # --- 主要目标：连续 primary_tries 次 ---
            for _ in range(self.primary_tries):
                if self._try_one(self.primary):
                    return True
                if self.max_retries > 0 and self.attempt >= self.max_retries:
                    log_err(f"达到最大重试次数 {self.max_retries}，退出")
                    return False
                time.sleep(self.retry_interval)

            # --- 候选：各试一次 ---
            for cand in all_targets:
                if self._try_one(cand):
                    return True
                if self.max_retries > 0 and self.attempt >= self.max_retries:
                    log_err(f"达到最大重试次数 {self.max_retries}，退出")
                    return False
                time.sleep(self.retry_interval)

        return self.success


# ══════════════════════════════════════════════════════
#   入口
# ══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="🎫 地大体育馆自动抢票脚本 v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 grab_ticket.py                        # 使用 config.py 配置
  python3 grab_ticket.py --date 2026-08-10      # 指定日期
  python3 grab_ticket.py --start-time 07:30:00  # 指定开抢时间
  python3 grab_ticket.py --now                  # 立即开始（忽略 config 时间）
        """
    )
    parser.add_argument("--token",        help="账号 token（覆盖 config.py）")
    parser.add_argument("--date",         help="预约日期 YYYY-MM-DD（默认明天）")
    parser.add_argument("--start-time",   help="开抢时间 HH:MM:SS（覆盖 config.py）")
    parser.add_argument("--now",          action="store_true", help="立即开始，忽略时间配置")
    parser.add_argument("--interval",     type=float, help="重试间隔秒数")
    parser.add_argument("--max-retries",  type=int,   help="最大重试次数（0=无限）")
    args = parser.parse_args()

    # 读配置
    token          = args.token      or getattr(config, "TOKEN", "")
    book_date      = args.date       or getattr(config, "TARGET_DATE", "") \
                     or str(date.today() + timedelta(days=1))
    start_time     = getattr(config, "GRAB_START_TIME", "") if not args.now else ""
    if args.start_time:
        start_time = args.start_time
    if args.now:
        start_time = ""
    retry_interval = args.interval    if args.interval    is not None \
                     else getattr(config, "RETRY_INTERVAL", 0.3)
    max_retries    = args.max_retries if args.max_retries is not None \
                     else getattr(config, "MAX_RETRIES", 0)
    advance        = getattr(config, "ADVANCE_SECONDS", 0.5)
    primary_tries  = getattr(config, "PRIMARY_TRIES_PER_ROUND", 3)

    primary    = getattr(config, "PRIMARY",    {})
    candidates = getattr(config, "CANDIDATES", [])

    if not token:
        log_err("请先获取 token！运行: python3 get_token.py")
        sys.exit(1)
    if not primary.get("nodeid"):
        log_err("请在 config.py 中配置 PRIMARY（主要场地）")
        sys.exit(1)

    grabber = MultiTargetGrabber(
        token=token,
        book_date=book_date,
        primary=primary,
        candidates=candidates,
        primary_tries=primary_tries,
        retry_interval=retry_interval,
        max_retries=max_retries,
    )
    grabber.init()

    # 等待放票时间
    wait_until(start_time, advance)

    # 开始抢！
    success = grabber.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
