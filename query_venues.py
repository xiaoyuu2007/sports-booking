#!/usr/bin/env python3
"""
查询场地工具 - 列出所有可预约场地及其 nodeid
用法: python3 query_venues.py [--date YYYY-MM-DD]
"""
import sys
import argparse
from datetime import date, timedelta

# 先从浏览器获取token（见 README 获取方法）
sys.path.insert(0, ".")
from api_client import VenueClient
import config

def main():
    parser = argparse.ArgumentParser(description="查询地大体育馆可预约场地")
    parser.add_argument("--token", help="账号token（可省略，使用config.py中的配置）")
    parser.add_argument("--date", help="查询日期 YYYY-MM-DD（默认明天）")
    parser.add_argument("--nodeid", help="查询指定场地的可用时间段")
    args = parser.parse_args()

    token = args.token or getattr(config, "TOKEN", "")
    if not token:
        print("❌ 请先在 config.py 中设置 TOKEN，或通过 --token 参数传入")
        print("   获取方法见 README.md")
        sys.exit(1)

    with VenueClient(token=token) as client:
        # 查询用户信息
        print("🔍 正在获取用户信息...")
        try:
            user = client.get_user_info()
            print(f"✅ 当前用户: {user.get('username', '未知')} ({user.get('idserial', '')})")
        except Exception as e:
            print(f"⚠️  获取用户信息失败: {e}")

        # 查询可预约场地列表
        print("\n🏟️  正在获取场地列表...")
        try:
            nodes = client.get_booking_nodes()
            print(f"✅ 共找到 {len(nodes)} 个可预约场地：\n")
            
            for i, node in enumerate(nodes):
                nodeid = node.get("nodeid") or node.get("id", "")
                name = node.get("nodename") or node.get("name", "未知")
                nodetype = node.get("nodetype", "")
                print(f"  [{i+1:02d}] nodeid={nodeid:<8} {name}  (类型: {nodetype})")
        except Exception as e:
            print(f"❌ 获取场地列表失败: {e}")
            return

        # 如果指定了 nodeid，查询该场地的可用时间
        if args.nodeid:
            target_date = args.date or str(date.today() + timedelta(days=1))
            print(f"\n⏰ 正在查询场地 {args.nodeid} 在 {target_date} 的可用时间...")
            try:
                data = client.get_available_times(args.nodeid, target_date)
                time_list = data.get("timeList", [])
                node_list = data.get("nodeList", [])
                price = data.get("price", 0)
                
                print(f"\n📋 场地信息:")
                print(f"   - 场地数量: {len(node_list)}")
                print(f"   - 单价: {price/100 if isinstance(price, int) else price} 元/格")
                print(f"\n🕐 可用时间段 (共 {len(time_list)} 个):")
                
                for j, slot in enumerate(time_list):
                    slot_time = slot.get("time") or slot.get("starttime", "")
                    available = slot.get("available", slot.get("status", ""))
                    print(f"   [{j:02d}] {slot_time}  状态: {available}")
                    
            except Exception as e:
                print(f"❌ 查询时间段失败: {e}")


if __name__ == "__main__":
    main()
