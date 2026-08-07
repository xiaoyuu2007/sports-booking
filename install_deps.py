#!/usr/bin/env python3
"""
🔧 安装依赖
"""
import subprocess
import sys

def main():
    packages = ["requests", "pycryptodome"]
    print("📦 安装必要依赖...")
    for pkg in packages:
        print(f"  安装 {pkg}...")
        # 尝试普通安装，如果失败（如 Arch Linux），使用 --break-system-packages
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "-q"],
            capture_output=True
        )
        if result.returncode != 0:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", pkg, "-q",
                "--break-system-packages"
            ])
    print("✅ 依赖安装完成！")

if __name__ == "__main__":
    main()
