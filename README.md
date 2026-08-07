# 地大体育馆自动购票脚本

> 为 **中国地质大学（北京）体育馆** 预约系统开发的个人自动购票工具。

---

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `config.py` | **配置文件**（必须先填写） |
| `api_client.py` | API 封装库（核心） |
| `get_token.py` | **步骤1**：获取登录 token |
| `query_venues.py` | **步骤2**：查看场地列表和时间段 |
| `grab_ticket.py` | **步骤3**：自动抢票主脚本 |
| `manage_orders.py` | 查看和取消订单 |
| `install_deps.py` | 安装依赖 |

---

## 🚀 快速开始

### 第一步：安装依赖

```bash
python3 install_deps.py
# 或
pip install requests pycryptodome
```

### 第二步：获取 Token

Token 是你的登录凭证，需要从浏览器中提取：

```bash
python3 get_token.py
```

**手动提取方法：**
1. 用浏览器打开：`https://bdtyg.cugb.edu.cn/#/pages/wxlogin/logging?openid=你的_OPENID&orgid=2`
2. 登录后按 `F12` 打开开发者工具
3. 点击 **Application** → **Local Storage** → `https://bdtyg.cugb.edu.cn`
4. 找到 key 为 **`token`** 的值，复制
5. 将值填入 `config.py` 的 `TOKEN` 字段

> ⚠️ Token 会定期过期，过期后需要重新获取。

### 第三步：查看场地列表

```bash
python3 query_venues.py
```

这会列出所有可预约场地及其 `nodeid`，例如：
```
[01] nodeid=101      羽毛球场A区  (类型: 2)
[02] nodeid=102      篮球场      (类型: 2)
[03] nodeid=103      游泳池      (类型: 3)
```

查看某个场地的可用时间段：
```bash
python3 query_venues.py --nodeid 101
python3 query_venues.py --nodeid 101 --date 2026-08-05
```

### 第四步：配置抢票参数

编辑 `config.py`：

```python
TOKEN = "你从浏览器复制的token"    # 必填
TARGET_NODE_ID = "101"              # 场地 nodeid
TARGET_DATE = "2026-08-05"          # 预约日期（留空=明天）
TARGET_TIME_SLOTS = ["08:00", "09:00"]  # 目标时间段（留空=自动选最早）
GRAB_START_TIME = "08:00:00"        # 抢票开始时间（留空=立即）
RETRY_INTERVAL = 0.5               # 重试间隔（秒）
```

### 第五步：开始抢票！

```bash
python3 grab_ticket.py
```

也可以通过命令行参数覆盖配置：
```bash
python3 grab_ticket.py --nodeid 101 --date 2026-08-05 --start-time 08:00:00
```

---

## 📋 订单管理

### 查看所有订单
```bash
python3 manage_orders.py list
```

### 只看待使用的订单
```bash
python3 manage_orders.py list --status 1
```

### 取消订单
```bash
python3 manage_orders.py cancel <订单号>
```

> ⚠️ **注意：每个月只能取消订单 3 次**，请谨慎操作！

---

## ⚙️ 高级用法

### 定时抢票（Linux/Mac Cron）

每天早上 7:59 自动执行（在系统层面定时，脚本内部等到 08:00 才发请求）：
```bash
crontab -e
# 添加：
59 7 * * * cd /home/xiaoyu/Desktop/地大体育馆脚本 && python3 grab_ticket.py >> grab.log 2>&1
```

### 在精确时间抢票

设置 `GRAB_START_TIME` 后，脚本会精确在该时间发出第一个请求（支持毫秒级精度）：
```python
GRAB_START_TIME = "08:00:00"  # 在 08:00:00 开始第一次请求
ADVANCE_SECONDS = 1            # 提前1秒开始准备
RETRY_INTERVAL = 0.3          # 每0.3秒重试一次
```

### 抢多个场次

```python
TARGET_TIME_SLOTS = ["08:00", "09:00", "10:00"]
MIN_TIME_SLOTS = 2  # 至少抢到2个时间段才算成功
```

---

## 🔍 技术说明

### API 信息（逆向自前端 JS）
- **基础地址**: `https://bdtyg.cugb.edu.cn/service/appointment/appointment`
- **认证方式**: 请求头 `token: <token值>`
- **加密算法**: AES-CBC，key=`0102030405060708`，iv=`0102030405060708`
- **请求格式**: POST，body 为 `item=<AES加密后的JSON大写HEX>`

### 关键 API 端点
| 端点 | 功能 |
|------|------|
| `/phone/getBookingNode` | 获取可预约场地列表 |
| `/phone/bookingByTime` | 查询某场地某日可用时间段 |
| `/phone/getPayPrice` | 获取预约价格 |
| `/phone/createBookingBytime` | **创建预约订单** |
| `/phone/payOrderForPhone` | 查看订单列表 |
| `/phone/payOrderDetails` | 订单详情 |
| `/phone/cancelOrder` | 取消订单 |
| `/userAddress/getUserInfo` | 获取用户信息 |

---

## ❓ 常见问题

**Q: 运行后报 "登录超时"？**
A: Token 已过期，重新运行 `python3 get_token.py` 获取新 token。

**Q: 一直重试但无法预约？**
A: 可能是该日期/时间段还未开放预约，或场地已满。检查开放时间后再设置 `GRAB_START_TIME`。

**Q: 如何知道抢票开放时间？**
A: 手动在微信公众号查看，通常是前一天某个固定时间开放。

**Q: 支持付费场地吗？**
A: 目前脚本针对免费场地。付费场地需要微信支付，暂未实现自动支付流程。
