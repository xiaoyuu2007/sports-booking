#!/usr/bin/env python3
"""
📋 订单管理工具
===============
查看、取消订单

用法:
  python3 manage_orders.py list              # 查看所有订单
  python3 manage_orders.py cancel <orderid>  # 取消指定订单
"""
import sys
import argparse
from datetime import datetime

sys.path.insert(0, ".")
from api_client import VenueClient
import config


STATUS_MAP = {
    "1": "✅ 待使用",
    "2": "❌ 已取消",
    "4": "🏁 已完成",
    "5": "⏳ 待付款",
    "7": "🔄 退款审批中",
    "8": "💰 已退款",
    "9": "🔄 退款中",
}


def get_client():
    token = getattr(config, "TOKEN", "")
    if not token:
        print("❌ 请先在 config.py 中设置 TOKEN")
        sys.exit(1)
    return VenueClient(token=token)


def list_orders(args):
    client = get_client()
    status = getattr(args, "status", None)
    
    print(f"\n{'='*65}")
    print(f"  📋 我的预约订单{'（状态：' + str(status) + '）' if status else ''}")
    print(f"{'='*65}")

    all_orders = []
    for page in range(1, 4):  # 最多读3页
        orders = client.get_orders(status=status, page=page)
        if not orders:
            break
        all_orders.extend(orders)
        if len(orders) < 10:
            break

    if not all_orders:
        print("  暂无订单")
        return

    for i, order in enumerate(all_orders):
        oid = order.get("orderid") or order.get("id", "")
        venue = order.get("nodename") or order.get("name", "未知场地")
        date_str = order.get("appointmentDate") or order.get("reservedate", "")
        time_str = order.get("reserveTimeStr") or order.get("reservetime", "")
        st = str(order.get("status", ""))
        status_label = STATUS_MAP.get(st, f"状态{st}")
        price = order.get("txamt", 0)
        price_str = f"{price/100:.2f}元" if price else "免费"

        print(f"\n  [{i+1:02d}] 订单号: {oid}")
        print(f"       场地: {venue}")
        print(f"       日期: {date_str}  时段: {time_str}")
        print(f"       状态: {status_label}  费用: {price_str}")

    print(f"\n{'='*65}")
    print(f"  共 {len(all_orders)} 条订单")


def cancel_order_cmd(args):
    client = get_client()
    order_id = args.orderid

    if not order_id:
        print("❌ 请指定订单号")
        sys.exit(1)

    # 先检查取消次数
    print(f"🔍 检查取消次数限制...")
    try:
        check = client.check_cancel_count(order_id)
        if check.get("resultData") is not None:
            remaining = check.get("resultData", {})
            print(f"   本月剩余取消次数: {remaining}")
    except Exception as e:
        print(f"   检查失败（继续尝试取消）: {e}")

    confirm = input(f"\n⚠️  确定取消订单 {order_id}？（注意：每月只能取消3次）[y/N] ").strip().lower()
    if confirm != "y":
        print("已取消操作")
        return

    print(f"🗑️  正在取消订单 {order_id}...")
    try:
        success = client.cancel_order(order_id)
        if success:
            print(f"✅ 订单 {order_id} 已成功取消")
        else:
            print(f"❌ 取消失败")
    except Exception as e:
        # 如果 cancelOrder 失败，尝试 userCancelBooking
        try:
            success = client.cancel_booking(order_id)
            if success:
                print(f"✅ 预约 {order_id} 已成功取消")
            else:
                print(f"❌ 取消失败")
        except Exception as e2:
            print(f"❌ 取消失败: {e2}")


def main():
    parser = argparse.ArgumentParser(description="📋 订单管理工具")
    subparsers = parser.add_subparsers(dest="command")

    # list 命令
    list_parser = subparsers.add_parser("list", help="查看订单列表")
    list_parser.add_argument("--status", help="过滤状态: 1=待使用 2=已取消 4=已完成 5=待付款")

    # cancel 命令
    cancel_parser = subparsers.add_parser("cancel", help="取消订单")
    cancel_parser.add_argument("orderid", help="订单号")

    args = parser.parse_args()

    if args.command == "list" or args.command is None:
        list_orders(args)
    elif args.command == "cancel":
        cancel_order_cmd(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
