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

### 第二步：配置账号

由于系统支持通过 OpenID 自动无限刷新 Token，所以你**不再需要手动抓取 Token**！

1. 在 `config.py` 中填写你的 `OPENID`：
```python
OPENID = "你的真实_OPENID"
```
2. 运行任意脚本或启动 web 服务时，系统会自动调用接口换取最新的 Token 并保持登录状态。Token 过期也会自动刷新，彻底解放双手！

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
OPENID = "你的真实_OPENID"          # 必填，后续系统会自动获取 Token
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

## 🌐 服务器部署 (Web 可视化版本)

为了获得最佳体验（图形化界面选座选时间），强烈推荐将本系统部署在服务器上 24 小时运行。

### 🐳 方式一：Docker 部署（推荐）
如果你服务器装有 Docker，只需在项目根目录运行：
```bash
docker-compose up -d
```
服务将在后台运行，挂掉也会自动重启。然后浏览器访问 `http://你的服务器IP:8765` 即可打开美观的 Web 抢票界面。

### 🐧 方式二：原生 Linux 脚本部署
如果你没有 Docker，我也提供了一键拉起服务的 Bash 脚本：
```bash
chmod +x deploy.sh
./deploy.sh
```
该脚本会自动创建虚拟环境、安装依赖，并用 `nohup` 将服务放入后台长期运行。
停止服务可使用：`pkill -f webapp.py`

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
59 7 * * * cd /path/to/project && python3 grab_ticket.py >> grab.log 2>&1
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
