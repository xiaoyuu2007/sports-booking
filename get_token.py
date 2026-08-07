#!/usr/bin/env python3
"""
🔑 获取 Token 工具
=================
通过打开浏览器登录页面自动提取 token，并保存到 config.py

用法: python3 get_token.py
"""
import sys
import json
import time
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# 你的 openid 和 orgid
OPENID = "你的_OPENID_填在这里"
ORG_ID = "2"
LOGIN_URL = f"https://bdtyg.cugb.edu.cn/#/pages/wxlogin/logging?openid={OPENID}&orgid={ORG_ID}"

EXTRACTED_TOKEN = None


def save_token_to_config(token: str):
    """将 token 写入 config.py"""
    try:
        with open("config.py", "r", encoding="utf-8") as f:
            content = f.read()

        # 替换或添加 TOKEN
        if 'TOKEN = ' in content:
            lines = content.split('\n')
            new_lines = []
            for line in lines:
                if line.strip().startswith('TOKEN ='):
                    new_lines.append(f'TOKEN = "{token}"')
                else:
                    new_lines.append(line)
            new_content = '\n'.join(new_lines)
        else:
            new_content = content + f'\n\n# 自动获取的 Token\nTOKEN = "{token}"\n'

        with open("config.py", "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    except Exception as e:
        print(f"保存 token 失败: {e}")
        return False


def try_api_login():
    """通过 openid 直接调用登录接口获取 token"""
    import requests
    from api_client import encrypt

    print("🔍 尝试通过 openid 自动登录...")

    base = "https://bdtyg.cugb.edu.cn/service/appointment/appointment"
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36",
        "Referer": "https://bdtyg.cugb.edu.cn/",
        "Origin": "https://bdtyg.cugb.edu.cn",
    })

    try:
        data = {"openid": OPENID, "orgid": ORG_ID}
        # 登录接口：JSON body，加密 item 字段
        resp = session.post(
            base + "/phone/login/wxLogin",
            json={"item": encrypt(data)},
            headers={"token": "", "Content-Type": "application/json"},
            timeout=10,
        )
        result = resp.json()
        print(f"  登录响应: {json.dumps(result, ensure_ascii=False)[:300]}")

        if result.get("success") and result.get("resultData"):
            rd = result["resultData"]
            token = rd.get("token")
            if token:
                name = rd.get("name", "")
                print(f"✅ 登录成功！用户: {name}")
                return token

        msg = result.get("message", "")
        if "微信未绑定" in msg:
            print("⚠️  该 openid 未绑定学工号，请手动登录")
        else:
            print(f"⚠️  登录失败: {msg}")

    except Exception as e:
        print(f"❌ 登录请求异常: {e}")

    return None


def extract_from_browser():
    """引导用户从浏览器中复制 token"""
    print("""
╔══════════════════════════════════════════════════════╗
║          🔑 手动获取 Token 指南                       ║
╠══════════════════════════════════════════════════════╣
║  1. 在浏览器中打开以下链接（或扫描学校公众号）         ║
║  2. 登录成功后，按 F12 打开开发者工具                  ║
║  3. 点击 Application → Local Storage                  ║
║  4. 找到 key 为 "token" 的值并复制                    ║
║  5. 将复制的值粘贴到下方                              ║
╚══════════════════════════════════════════════════════╝

""")
    print(f"🌐 登录链接:\n   {LOGIN_URL}\n")

    try:
        webbrowser.open(LOGIN_URL)
        print("（已尝试自动打开浏览器）\n")
    except Exception:
        pass

    while True:
        token = input("📋 请粘贴 token（直接回车跳过）: ").strip()
        if token:
            if len(token) > 10:
                return token
            else:
                print("token 太短，请重新输入")
        else:
            return None


def main():
    print("=" * 55)
    print("   🔑 地大体育馆 Token 获取工具")
    print("=" * 55)

    # 首先尝试 API 直接登录
    token = try_api_login()

    # 如果 API 登录失败，引导手动获取
    if not token:
        print("\n⚠️  自动获取失败，请手动提取 token\n")
        token = extract_from_browser()

    if not token:
        print("\n❌ 未获取到 token，请手动设置 config.py 中的 TOKEN 字段")
        sys.exit(1)

    # 验证 token
    print(f"\n🔍 正在验证 token...")
    try:
        from api_client import VenueClient
        client = VenueClient(token=token)
        user = client.get_user_info()
        username = user.get("username") or user.get("name", "未知")
        print(f"✅ Token 有效！用户: {username}")
    except Exception as e:
        print(f"⚠️  Token 验证失败: {e}（仍将保存）")

    # 保存 token
    if save_token_to_config(token):
        print(f"\n💾 Token 已保存到 config.py")
        print(f"   TOKEN = \"{token[:20]}...\"")
    else:
        print(f"\n📋 Token: {token}")
        print("（请手动将上方 token 填入 config.py 的 TOKEN 字段）")

    print("\n🎉 完成！现在可以运行:")
    print("   python3 query_venues.py          # 查看场地列表")
    print("   python3 grab_ticket.py           # 开始抢票")


if __name__ == "__main__":
    main()
