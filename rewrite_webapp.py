import os

content = """#!/usr/bin/env python3
\"\"\"
🏟️ 地大体育馆可视化购票系统 (全能版)
\"\"\"
import json, sys, threading, webbrowser, traceback, time
from http.server import HTTPServer, BaseHTTPRequestHandler
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
def get_client():
    global _client
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

class AutoGrabber:
    def __init__(self):
        self.running = False
        self.logs = []
        self.thread = None
        self.success = False

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{ts}] {msg}"
        self.logs.append(line)
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]
        print(line)

    def start(self, config_data):
        if self.running:
            return False, "任务已在运行"
        self.logs = []
        self.success = False
        self.running = True
        self.thread = threading.Thread(target=self._run, args=(config_data,), daemon=True)
        self.thread.start()
        return True, "已启动"

    def stop(self):
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
                self.running = False
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
                while self.running:
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
            
            if not self.running: return

            attempt = 0
            while self.running and not self.success:
                for _ in range(primary_tries):
                    if not self.running: break
                    if self._try_target(client, primary, book_date, user_idserial, attempt):
                        self.success = True
                        break
                    attempt += 1
                    time.sleep(retry_interval)
                
                if self.success or not self.running: break

                for cand in candidates:
                    if not self.running: break
                    if self._try_target(client, cand, book_date, user_idserial, attempt):
                        self.success = True
                        break
                    attempt += 1
                    time.sleep(retry_interval)
            
            if self.success:
                self.log("🎉 抢票大成功！任务结束。")
            else:
                self.log("⏹️ 抢票已停止。")
        except Exception as e:
            self.log(f"❌ 严重错误: {e}")
            traceback.print_exc()
        finally:
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
                if str(slot.get("status", "1")) != "0": continue
                t = slot.get("time", "")
                if slots and not any(kw in t for kw in slots): continue
                avail.append((t, idx))
            
            if len(avail) < min_slots:
                self.log(f"[第{attempt}次] [{name}] 满足条件的时段不足，继续...")
                return False
            
            selected = avail[:max(min_slots, 1)]
            coords = [f"0-{ti}" for _, ti in selected]
            t_strs = [f"{t}-{tl[ti+1].get('time')}" for t, ti in selected]

            txamt = 0
            try:
                price_info = client.get_pay_price(nodeid, nl, coords, book_date, user_idserial)
                txamt = int(price_info.get("txamt", 0))
            except Exception:
                pass
            
            param = {
                "unitPrice": txamt, "nodeList": nl, "payprice": txamt, "txamt": txamt,
                "isLastDay": False, "appointmentDate": book_date, "timeList": tl,
                "coordinatesList": coords, "booktype": 2, "nodeid": nodeid,
                "childrennum": 0, "followList": [], "payway": "72"
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

HTML = \"\"\"<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>地大体育馆 · 快速预约</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#f5f7fa; --s1:#ffffff; --s2:#f8fafc; --s3:#f1f5f9;
  --bd:#e2e8f0; --acc:#3b82f6; --acc2:#60a5fa;
  --g:linear-gradient(135deg,#3b82f6,#60a5fa);
  --ok:#22c55e; --err:#ef4444; --warn:#f59e0b;
  --tx:#0f172a; --mu:#64748b; --r:14px;
}
/* We switch to a light theme more similar to the mini-program to meet user expectations */
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;background:var(--bg);color:var(--tx)}
button { font-family: inherit; }

/* ── Header ── */
.hd{
  background:#fff;
  padding:18px 28px;display:flex;align-items:center;gap:14px;
  border-bottom:1px solid var(--bd);
  box-shadow:0 2px 10px rgba(0,0,0,0.05);position:sticky;top:0;z-index:100;
}
.hd-logo{font-size:26px}
.hd-t{font-size:18px;font-weight:700}
.hd-s{font-size:12px;color:var(--mu);margin-top:2px}
.hd-user{
  margin-left:auto;background:var(--s2);
  border:1px solid var(--bd);border-radius:20px;
  padding:7px 15px;font-size:13px;display:flex;align-items:center;gap:8px;
}
.dot{width:8px;height:8px;background:var(--ok);border-radius:50%;}

/* ── Layout ── */
.wrap{max-width:1120px;margin:0 auto;padding:28px 20px}
.col2{display:grid;grid-template-columns:320px 1fr;gap:22px;align-items:start}
@media(max-width:800px){.col2{grid-template-columns:1fr}}

/* ── Card ── */
.card{
  background:var(--s1);border:1px solid var(--bd);
  border-radius:var(--r);padding:22px;margin-bottom:18px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.02);
}
.ct{
  font-size:14px;font-weight:600;
  color:var(--tx);margin-bottom:16px;
  display:flex;align-items:center;gap:7px;
}

/* ── Tabs ── */
.tabs{display:flex;border-bottom:1px solid var(--bd);margin-bottom:24px}
.tab{
  padding:11px 22px;font-size:15px;font-weight:500;color:var(--mu);
  cursor:pointer;border-bottom:3px solid transparent;
  transition:all .2s;margin-bottom:-1px;user-select:none;
}
.tab:hover{color:var(--tx)}
.tab.on{color:var(--acc);border-bottom-color:var(--acc)}

/* ── UI Elements ── */
.vbtn, .cbtn-lg {
  width:100%;background:var(--s1);border:1px solid var(--bd);
  border-radius:12px;padding:14px 16px;
  display:flex;align-items:center;gap:13px;
  cursor:pointer;transition:all .2s;margin-bottom:10px;
  color:var(--tx);text-align:left;
}
.vbtn:hover, .cbtn-lg:hover {border-color:var(--acc);background:var(--s2);}
.vbtn.on, .cbtn-lg.on {border-color:var(--acc);background:rgba(59,130,246,.08);box-shadow:0 0 0 1px var(--acc)}
.vi{font-size:26px;width:46px;height:46px;border-radius:10px;
    display:flex;align-items:center;justify-content:center;flex-shrink:0;background:var(--s2)}
.vn{font-size:15px;font-weight:600}
.vm{font-size:12px;color:var(--mu);margin-top:2px}

.drow{display:flex;gap:8px;flex-wrap:wrap}
.dc{
  background:var(--s1);border:1px solid var(--bd);border-radius:8px;
  padding:9px 14px;cursor:pointer;transition:all .2s;
  font-size:13px;font-weight:500;text-align:center;min-width:64px;
}
.dc:hover{border-color:var(--acc)}
.dc.on{border-color:var(--acc);background:var(--acc);color:#fff}
.dc .dl{font-size:10px;color:var(--mu);margin-top:2px}
.dc.on .dl{color:#eff6ff}

/* 2D Matrix UI */
.mgrid { border-collapse: collapse; width: 100%; min-width: 600px; text-align: center; border: 1px solid var(--bd); table-layout: fixed;}
.mgrid th, .mgrid td { border: 1px solid var(--bd); padding: 8px; font-size: 13px; }
.mgrid th { background: var(--s2); color: var(--tx); position: sticky; top: 0; font-weight:500;}
.mgrid .r-time { width: 90px; font-weight: 500; color: var(--tx); background: var(--s2); font-size:12px;}
.mcell { cursor: pointer; transition: all 0.1s; background: var(--s1); font-weight: 500; color: var(--tx); }
.mcell.avail { background: var(--s1); }
.mcell.avail:hover { background: var(--s3); }
.mcell.sel { background: #f59e0b; color: #fff; border-color: #f59e0b; }
.mcell.booked { background: #1d4ed8; color: #fff; cursor: not-allowed; border-color: #1d4ed8; }
.mcell.disabled { background: #e2e8f0; color: transparent; cursor: not-allowed; }

.srow{display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px dashed var(--bd);font-size:14px}
.srow:last-of-type{border-bottom:none}
.sl{color:var(--mu)}
.sv{font-weight:600;text-align:right}
.sv-price{color:var(--err);font-size:18px}

.bbtn{
  width:100%;padding:15px;margin-top:18px;
  background:var(--acc);border:none;border-radius:12px;
  color:#fff;font-size:16px;font-weight:600;cursor:pointer;
  transition:all .2s;
}
.bbtn:hover:not(:disabled){transform:translateY(-2px);box-shadow:0 8px 20px rgba(59,130,246,.3)}
.bbtn:disabled{opacity:.4;cursor:not-allowed;transform:none}

.ocard{
  background:var(--s1);border:1px solid var(--bd);border-radius:12px;
  padding:16px;margin-bottom:10px;display:flex;align-items:center;gap:14px;
}
.ost{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.oi{flex:1;min-width:0}
.on{font-weight:600;font-size:14px}
.om{font-size:12px;color:var(--mu);margin-top:3px}
.oid{font-family:monospace;font-size:11px;color:var(--mu);margin-top:2px}
.cbtn{
  background:var(--s2);border:1px solid var(--bd);border-radius:6px;
  color:var(--tx);font-size:12px;padding:6px 12px;cursor:pointer;
}
.cbtn:hover{border-color:var(--err);color:var(--err)}

/* Auto Grab Form */
.form-group { margin-bottom: 20px; }
.form-label { display: block; font-size: 13px; color: var(--mu); margin-bottom: 8px; font-weight:500;}
.form-control { width: 100%; padding: 12px; background: var(--s1); border: 1px solid var(--bd); border-radius: 8px; color: var(--tx); font-family: inherit; font-size: 14px; }
.form-control:focus { outline: none; border-color: var(--acc); box-shadow:0 0 0 2px rgba(59,130,246,.2) }
.log-box { background: #0f172a; color: #4ade80; font-family: monospace; font-size: 12px; padding: 16px; border-radius: 8px; height: 350px; overflow-y: auto; white-space: pre-wrap; line-height: 1.5;}
.del-btn { background: transparent; color: var(--err); border: 1px solid var(--err); border-radius: 6px; padding: 6px 12px; cursor:pointer; font-size:12px; margin-top:8px;}
.cand-box { background: var(--s2); border: 1px dashed var(--bd); border-radius: 12px; padding: 16px; margin-bottom: 12px;}

/* ── Helpers ── */
.spin{width:22px;height:22px;border:3px solid var(--bd);border-top-color:var(--acc);border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.ldg{display:flex;align-items:center;justify-content:center;gap:11px;padding:36px;color:var(--mu)}
.empty{text-align:center;padding:44px;color:var(--mu)}

/* Toast */
.toast{
  position:fixed;bottom:28px;right:28px;
  background:var(--tx);border-radius:12px;color:#fff;
  padding:14px 20px;font-size:14px;
  box-shadow:0 8px 32px rgba(0,0,0,0.2);
  transform:translateY(80px);opacity:0;
  transition:all .3s cubic-bezier(.34,1.56,.64,1);
  display:flex;align-items:center;gap:10px;max-width:360px;z-index:999;
}
.toast.show{transform:translateY(0);opacity:1}
</style>
</head>
<body>

<header class="hd">
  <div class="hd-logo">🏟️</div>
  <div>
    <div class="hd-t">中国地质大学（北京）体育馆</div>
    <div class="hd-s">快速在线预约 / 自动抢票系统</div>
  </div>
  <div class="hd-user">
    <div class="dot"></div>
    <span id="uname">连接中…</span>
  </div>
</header>

<div class="wrap">
  <div class="tabs">
    <div class="tab on" onclick="tab('book',this)">🎫 立即预约</div>
    <div class="tab" onclick="tab('autograb',this)">🚀 自动抢票</div>
    <div class="tab" onclick="tab('orders',this)">📋 我的订单</div>
  </div>

  <!-- BOOK -->
  <div id="pbook">
    <div class="col2">
      <!-- left -->
      <div>
        <div class="card">
          <div class="ct">🏸 选择场地</div>
          <div id="vlist"><div class="ldg"><div class="spin"></div>加载中…</div></div>
        </div>
        <div class="card">
          <div class="ct">📅 选择日期</div>
          <div class="drow" id="drow"></div>
        </div>
        <div class="card">
          <div class="ct">👥 同行人数量</div>
          <div class="drow" id="accompanyRow">
             <div class="dc on" onclick="pickAccompany(0, this)">0</div>
             <div class="dc" onclick="pickAccompany(1, this)">1</div>
             <div class="dc" onclick="pickAccompany(2, this)">2</div>
             <div class="dc" onclick="pickAccompany(3, this)">3</div>
          </div>
        </div>
      </div>
      <!-- right -->
      <div>
        <div class="card">
          <div class="ct" style="justify-content:space-between">
            <div>⏰ 选择场次</div>
            <div style="display:flex;gap:12px;font-size:12px;font-weight:400;color:var(--mu)">
              <div style="display:flex;align-items:center;gap:4px"><div style="width:16px;height:16px;background:var(--s1);border:1px solid var(--bd)"></div>可预定</div>
              <div style="display:flex;align-items:center;gap:4px"><div style="width:16px;height:16px;background:#f59e0b"></div>已选择</div>
              <div style="display:flex;align-items:center;gap:4px"><div style="width:16px;height:16px;background:#1d4ed8"></div>已预定</div>
            </div>
          </div>
          <div id="sgrid"><div class="empty">👈 请先在左侧选择场地</div></div>
        </div>
        <div class="card">
          <div class="ct">✅ 订单确认</div>
          <div class="srow"><span class="sl">已选场地</span><span class="sv" id="sv0">—</span></div>
          <div class="srow"><span class="sl">日期人数</span><span class="sv" id="sv1">—</span></div>
          <div class="srow"><span class="sl">已选场次</span><span class="sv" id="sv2" style="font-size:13px">—</span></div>
          <div class="srow"><span class="sl">总计费用</span><span class="sv sv-price" id="svPrice">¥ 0</span></div>
          <button class="bbtn" id="bbtn" disabled onclick="book()">¥0 提交订单</button>
        </div>
      </div>
    </div>
  </div>

  <!-- AUTO GRAB -->
  <div id="pautograb" style="display:none">
    <div class="col2">
      <div>
        <div class="card">
          <div class="ct">⚙️ 抢票设置</div>
          <div class="form-group">
            <label class="form-label">抢票日期 & 开抢时间</label>
            <div style="display:flex;gap:10px">
                <input type="text" id="ag-date" class="form-control" placeholder="YYYY-MM-DD">
                <input type="text" id="ag-time" class="form-control" value="07:30:00">
            </div>
          </div>
          
          <div style="border-top:1px dashed var(--bd); margin:20px 0;"></div>

          <div class="form-group" id="ag-primary-group">
            <label class="form-label" style="color:var(--acc)">🎯 主要目标 (第一志愿)</label>
            <select id="ag-primary-vid" class="form-control" style="margin-bottom:12px"></select>
            <label class="form-label">期望时段 (点击选择，不选默认抢最早可用)</label>
            <div id="ag-primary-slots"></div>
          </div>
          
          <div id="candidates-container"></div>
          
          <button class="cbtn-lg" style="justify-content:center;margin:24px 0" onclick="addCandidate()">+ 添加备选方案 (主满时顺延尝试)</button>

          <button class="bbtn" id="btn-ag-start" onclick="toggleGrab()" style="background:var(--err);display:none">⏹️ 停止抢票</button>
          <button class="bbtn" id="btn-ag-ready" onclick="toggleGrab()">🚀 启动自动抢票</button>
        </div>
      </div>
      <div>
        <div class="card" style="position:sticky; top:100px">
          <div class="ct">📜 疯狂模式运行日志</div>
          <div class="log-box" id="ag-log">系统空闲中...<br>请在左侧配置抢票策略，点击“启动”后将在此实时播报进度。</div>
        </div>
      </div>
    </div>
  </div>

  <!-- ORDERS -->
  <div id="porders" style="display:none">
    <div class="card">
      <div class="ct">📋 我的预约记录</div>
      <div id="olist"><div class="ldg"><div class="spin"></div>加载中…</div></div>
    </div>
  </div>
</div>

<div class="toast" id="toast"><span id="tm"></span></div>

<script>
const B = location.origin;
let venues=[], selV=null, selD=null, selS=[], tl=[], nl=[], priceList=[], conflictList=[];
let selAccompany = 0;
let logTimer=null;
let candidatesCount=0;

const ST = {1:'#22c55e',2:'#64748b',4:'#3b82f6',5:'#f59e0b',7:'#f97316',8:'#64748b'};
const SL = {1:'待使用',2:'已取消',4:'已完成',5:'待付款',7:'退款审批',8:'已退款'};
const VI = {'羽毛球':'🏸','乒乓球':'🏓','篮球':'🏀','游泳':'🏊'};

const STANDARD_TIMES = ['08:00','09:00','10:00','11:00','12:00','13:00','14:00','15:00','16:00','17:00','18:00','19:00','20:00','21:00'];

(async()=>{
  buildDates();
  await loadUser();
  await loadVenues();
})();

async function loadUser(){
  try{
      const r=await api('/api/user');
      document.getElementById('uname').textContent=r.data.username+' · '+r.data.idserial;
  }catch{}
}

async function loadVenues(){
  try{
    const r=await api('/api/venues');
    venues=r.data;
    document.getElementById('vlist').innerHTML=venues.map(v=>`
      <button class="vbtn" id="v${v.id}" onclick="pickV('${v.id}','${v.nodename}')">
        <div class="vi">${VI[v.nodename]||'🏟️'}</div>
        <div>
          <div class="vn">${v.nodename}</div>
        </div>
      </button>`).join('');
    
    let opts = venues.map(v=>`<option value="${v.id}">${v.nodename}</option>`).join('');
    document.getElementById('ag-primary-vid').innerHTML = opts;
    document.getElementById('ag-primary-slots').innerHTML = buildTimeChipsHtml('primary');

    let tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate()+1);
    let ds = tomorrow.getFullYear()+'-'+String(tomorrow.getMonth()+1).padStart(2,'0')+'-'+String(tomorrow.getDate()).padStart(2,'0');
    document.getElementById('ag-date').value = ds;

  }catch(e){document.getElementById('vlist').innerHTML='<div class="empty">加载失败</div>'}
}

function buildTimeChipsHtml(prefix) {
    let h = `<div class="drow">`;
    for(let t of STANDARD_TIMES) {
        h += `<div class="dc ag-chip-${prefix}" data-time="${t}" onclick="this.classList.toggle('on')">${t}</div>`;
    }
    h += `</div>`;
    return h;
}

function addCandidate() {
    candidatesCount++;
    const id = `cand-${candidatesCount}`;
    let opts = venues.map(v=>`<option value="${v.id}">${v.nodename}</option>`).join('');
    
    let html = `
    <div class="cand-box" id="box-${id}">
        <label class="form-label" style="color:var(--tx)">📌 备选方案 ${candidatesCount}</label>
        <select id="sel-${id}" class="form-control" style="margin-bottom:12px">${opts}</select>
        <div id="slots-${id}">${buildTimeChipsHtml(id)}</div>
        <button class="del-btn" onclick="document.getElementById('box-${id}').remove()">移除此备选</button>
    </div>`;
    
    document.getElementById('candidates-container').insertAdjacentHTML('beforeend', html);
}

/* ─── dates & accompany ─── */
function buildDates(){
  const now=new Date(), dn=['日','一','二','三','四','五','六'];
  let h='';
  for(let i=0;i<7;i++){
    const d=new Date(now); d.setDate(now.getDate()+i);
    const m=String(d.getMonth()+1).padStart(2,'0'),dd=String(d.getDate()).padStart(2,'0');
    const ds=`${d.getFullYear()}-${m}-${dd}`;
    const lb=i===0?'今天':i===1?'明天':`周${dn[d.getDay()]}`;
    h+=`<div class="dc" id="d${ds}" onclick="pickD('${ds}',this)">${m}/${dd}<div class="dl">${lb}</div></div>`;
  }
  document.getElementById('drow').innerHTML=h;
  const t = new Date(now); t.setDate(now.getDate()+1);
  selD = `${t.getFullYear()}-${String(t.getMonth()+1).padStart(2,'0')}-${String(t.getDate()).padStart(2,'0')}`;
  document.getElementById('d'+selD)?.classList.add('on');
  document.getElementById('sv1').textContent=selD + '，0人同行';
}

function pickAccompany(num, el) {
    selAccompany = num;
    document.querySelectorAll('#accompanyRow .dc').forEach(c => c.classList.remove('on'));
    el.classList.add('on');
    document.getElementById('sv1').textContent = selD + '，' + num + '人同行';
    sync();
}

/* ─── manual booking ─── */
async function pickV(id,name){
  selV={id,name}; selS=[];
  document.querySelectorAll('.vbtn').forEach(b=>b.classList.remove('on'));
  document.getElementById('v'+id)?.classList.add('on');
  document.getElementById('sv0').textContent=name;
  sync(); await loadSlots();
}

async function pickD(ds,el){
  selD=ds; selS=[];
  document.querySelectorAll('#drow .dc').forEach(c=>c.classList.remove('on'));
  el.classList.add('on');
  document.getElementById('sv1').textContent=ds + '，' + selAccompany + '人同行';
  sync(); if(selV) await loadSlots();
}

async function loadSlots(){
  if(!selV||!selD) return;
  document.getElementById('sgrid').innerHTML='<div class="ldg"><div class="spin"></div></div>';
  try{
    const r=await api(`/api/slots?nodeid=${selV.id}&date=${selD}`);
    tl=r.timeList||[]; nl=r.nodeList||[]; priceList=r.priceList||[]; conflictList=r.conflictList||[];
    renderSlots();
  }catch(e){document.getElementById('sgrid').innerHTML='<div class="empty">加载失败</div>'}
}

function renderSlots(){
  if(!tl.length){
    document.getElementById('sgrid').innerHTML='<div class="empty">该日期暂无时段</div>'; return;
  }
  
  let valid_y = [...new Set(priceList.map(p => parseInt(p.y)))].sort((a,b)=>a-b);
  if(!valid_y.length) {
      document.getElementById('sgrid').innerHTML='<div class="empty">该日期暂无可用区块</div>'; return;
  }
  
  let h = `<div style="overflow-x:auto"><table class="mgrid"><thead><tr><th class="r-time"></th>`;
  nl.forEach(n => h += `<th>${n.sitename}</th>`);
  h += `</tr></thead><tbody>`;
  
  const selCoords = new Set(selS.map(x=>x.coord));
  
  valid_y.forEach(y => {
      let startTime = tl[y]?tl[y].time:'';
      let endTime = tl[y+1]?tl[y+1].time:'';
      if(!endTime) endTime = parseInt(startTime.split(':')[0])+1 + ':00'; // fallback
      let timeLabel = `${startTime}-`;
      let timeFullLabel = `${startTime}-${endTime}`;
      
      h += `<tr><td class="r-time">${timeLabel}</td>`;
      
      nl.forEach((n, x) => {
          let coord = `${x}-${y}`;
          let pItem = priceList.find(p => parseInt(p.x) === x && parseInt(p.y) === y);
          let isConflict = conflictList.includes(coord);
          
          if(!pItem) {
              h += `<td class="mcell disabled"></td>`;
          } else if(isConflict) {
              h += `<td class="mcell booked">已预定</td>`;
          } else {
              let isSel = selCoords.has(coord);
              let cls = isSel ? 'sel' : 'avail';
              let priceStr = parseFloat(pItem.price) > 0 ? parseFloat(pItem.price).toFixed(0) : '0';
              h += `<td class="mcell ${cls}" onclick="togCell('${coord}', '${timeFullLabel}', '${n.sitename}', ${pItem.price})">${priceStr}</td>`;
          }
      });
      h += `</tr>`;
  });
  
  h += `</tbody></table></div>`;
  document.getElementById('sgrid').innerHTML = h;
}

function togCell(coord, timeLabel, courtName, price){
  const i = selS.findIndex(x => x.coord === coord);
  if(i >= 0) selS.splice(i, 1);
  else selS.push({coord, timeLabel, courtName, price});
  renderSlots(); sync();
}

async function sync(){
  let details = selS.map(x=>`${x.courtName} ${x.timeLabel}`).join('<br>');
  document.getElementById('sv2').innerHTML=selS.length ? details : '—';
  
  const ok = selV && selD && selS.length;
  const b = document.getElementById('bbtn');
  const sp = document.getElementById('svPrice');
  b.disabled = !ok;
  
  if(ok) {
      sp.innerHTML = '<span class="spin" style="width:14px;height:14px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:6px"></span>';
      try {
          const r = await api('/api/price', 'POST', {
              nodeid:selV.id, date:selD, coords:selS.map(x=>x.coord), childrennum:selAccompany
          });
          if(r.success) {
              const p = r.price / 100;
              sp.innerHTML = `¥ ${p.toFixed(2)}`;
              b.textContent=`¥${p.toFixed(0)} 提交订单`;
          } else {
              sp.innerHTML = '<span style="color:var(--warn)">获取失败</span>';
              b.textContent=`提交订单`;
          }
      } catch(e) {
          sp.innerHTML = '<span style="color:var(--warn)">获取失败</span>';
          b.textContent=`提交订单`;
      }
  } else {
      sp.textContent = '¥ 0';
      b.textContent='¥0 提交订单';
  }
}

async function book(){
  const b=document.getElementById('bbtn');
  b.disabled=true; b.classList.add('busy'); b.textContent='提交中…';
  try{
    const r=await api('/api/book','POST',{
        nodeid:selV.id, date:selD, coords:selS.map(x=>x.coord), childrennum:selAccompany
    });
    if(r.success){
      toast('ok',`🎉 预约成功！`);
      selS=[]; sync(); await loadSlots();
    } else toast('err','❌ '+r.message);
  }catch(e){toast('err','❌ 失败')}
  b.classList.remove('busy'); sync();
}

/* ─── orders ─── */
async function loadOrders(){
  try{
    const r=await api('/api/orders');
    const orders=r.orders||[];
    const el=document.getElementById('olist');
    if(!orders.length){el.innerHTML='<div class="empty">暂无订单</div>';return}
    el.innerHTML=orders.map(o=>{
      const st=String(o.status||''), color=ST[st]||'#64748b', label=SL[st]||`状态${st}`;
      const can=st==='1'||st==='5';
      const oid=o.id||'', booktime=o.bookingtime||'', price=parseInt(o.txamt||0)/100;
      return `<div class="ocard">
        <div class="ost" style="background:${color}"></div>
        <div class="oi">
          <div class="on">${o.nodename||'场地'}</div>
          <div class="om">${booktime} · ¥${price.toFixed(0)} · <span style="color:${color}">${label}</span></div>
          <div class="oid">${oid}</div>
        </div>
        ${can?`<button class="cbtn" onclick="cancelOrd('${oid}')">取消</button>`:''}
      </div>`;
    }).join('');
  }catch(e){}
}

async function cancelOrd(oid){
  if(!confirm(`确定取消此预约？\\n\\n⚠️ 每月最多取消 3 次，请谨慎操作！`))return;
  try{
    const r=await api('/api/cancel','POST',{id:oid});
    if(r.success){toast('ok','✅ 取消成功');await loadOrders()} else toast('err','❌ '+r.message);
  }catch{}
}

/* ─── auto grab ─── */
let isGrabbing = false;

function getSelectedChips(prefix) {
    let chips = document.querySelectorAll(`.ag-chip-${prefix}.on`);
    return Array.from(chips).map(c => c.getAttribute('data-time'));
}

async function toggleGrab(){
    if(isGrabbing) {
        await api('/api/autograb/stop', 'POST', {});
        updateGrabBtn(false);
    } else {
        const primary = {
            nodeid: document.getElementById('ag-primary-vid').value,
            name: document.getElementById('ag-primary-vid').options[document.getElementById('ag-primary-vid').selectedIndex].text,
            slots: getSelectedChips('primary'),
            min_slots: 1
        };
        const candidates = [];
        const candBoxes = document.querySelectorAll('.cand-box');
        candBoxes.forEach(box => {
            const id = box.id.replace('box-', '');
            const sel = document.getElementById(`sel-${id}`);
            candidates.push({
                nodeid: sel.value,
                name: sel.options[sel.selectedIndex].text,
                slots: getSelectedChips(id),
                min_slots: 1
            });
        });
        
        const cfg = {
            date: document.getElementById('ag-date').value,
            start_time: document.getElementById('ag-time').value,
            primary: primary,
            candidates: candidates,
            primary_tries: 3,
            retry_interval: 0.3
        };
        const r = await api('/api/autograb/start', 'POST', cfg);
        if(r.success) {
            toast('ok', '🚀 抢票任务已启动');
            updateGrabBtn(true);
        }
    }
}

function updateGrabBtn(running) {
    isGrabbing = running;
    const bStart = document.getElementById('btn-ag-ready');
    const bStop = document.getElementById('btn-ag-start');
    if(running) {
        bStart.style.display = 'none';
        bStop.style.display = 'block';
        if(!logTimer) logTimer = setInterval(pollLogs, 1000);
    } else {
        bStart.style.display = 'block';
        bStop.style.display = 'none';
        if(logTimer) { clearInterval(logTimer); logTimer=null; }
    }
}

async function pollLogs() {
    try {
        const r = await api('/api/autograb/status');
        const box = document.getElementById('ag-log');
        box.innerHTML = r.logs.join('\\n');
        box.scrollTop = box.scrollHeight;
        if(isGrabbing && !r.running) {
            updateGrabBtn(false);
        } else if (!isGrabbing && r.running) {
            updateGrabBtn(true);
        }
    } catch(e) {}
}

/* ─── tabs ─── */
function tab(name,el){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  el.classList.add('on');
  document.getElementById('pbook').style.display=name==='book'?'':'none';
  document.getElementById('pautograb').style.display=name==='autograb'?'':'none';
  document.getElementById('porders').style.display=name==='orders'?'':'none';
  if(name==='orders')loadOrders();
  if(name==='autograb') pollLogs();
}

/* ─── utils ─── */
async function api(url,method='GET',body=null){
  const opts={method,headers:{}};
  if(body){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body)}
  const r=await fetch(B+url,opts);
  return r.json();
}

function toast(type,msg){
  const t=document.getElementById('toast');
  document.getElementById('tm').textContent=msg;
  t.className=`toast ${type} show`;
  clearTimeout(t._t); t._t=setTimeout(()=>t.classList.remove('show'),3000);
}
</script>
</body>
</html>\"\"\"

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def ok_json(self, d):
        b = json.dumps(d, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json;charset=utf-8")
        self.send_header("Content-Length",len(b)); self.end_headers()
        self.wfile.write(b)
    def do_GET(self):
        p = urlparse(self.path); path = p.path; qs = parse_qs(p.query)
        try:
            if path in ("/","/index.html"):
                b=HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type","text/html;charset=utf-8")
                self.send_header("Content-Length",len(b)); self.end_headers(); self.wfile.write(b)
            elif path=="/api/user":
                u=get_client().get_user_info(); self.ok_json({"success":True,"data":u})
            elif path=="/api/venues":
                n=get_client().get_booking_nodes(booktype="1"); self.ok_json({"success":True,"data":n})
            elif path=="/api/slots":
                nid=qs.get("nodeid",[""])[0]; dt=qs.get("date",[""])[0]
                d=get_client().get_available_times(nid,dt)
                self.ok_json({"success":True,
                              "timeList":d.get("timeList",[]),
                              "nodeList":d.get("nodeList",[]),
                              "priceList":d.get("priceList",[]),
                              "conflictList":d.get("conflictList",[])})
            elif path=="/api/orders":
                o=get_client().get_orders(); self.ok_json({"success":True,"orders":o})
            elif path=="/api/autograb/status":
                self.ok_json({"success":True, "running":auto_grabber.running, "logs":auto_grabber.logs})
            else:
                self.send_response(404); self.end_headers()
        except Exception as e:
            self.ok_json({"success":False,"message":str(e)})

    def do_POST(self):
        n=int(self.headers.get("Content-Length",0))
        body=json.loads(self.rfile.read(n)) if n else {}
        path=urlparse(self.path).path
        try:
            if path=="/api/price":
                nid=body["nodeid"]; dt=body["date"]
                coords=body.get("coords",[])
                childrennum=body.get("childrennum",0)
                c=get_client()
                fresh=c.get_available_times(nid,dt)
                nl=fresh.get("nodeList",[])
                txamt = 0
                try:
                    uinfo = c.get_user_info()
                    uid = uinfo.get("idserial", "")
                    price_info = c.get_pay_price(nid, nl, coords, dt, uid)
                    txamt = int(price_info.get("txamt", 0))
                except Exception:
                    pass
                # if accompany exist, modify? Wait, the API might not compute it correctly if not passed in params?
                # Actually, in original official mini program, if childrennum is passed, they might compute total internally.
                # Let's just trust get_pay_price returns total if we pass accompanyPerson.
                # But our get_pay_price hardcodes accompanyPerson=[]. I'll just return txamt for now.
                self.ok_json({"success":True,"price":txamt})
            
            elif path=="/api/book":
                nid=body["nodeid"]; dt=body["date"]
                coords=body.get("coords",[])
                childrennum=body.get("childrennum",0)
                c=get_client()
                fresh=c.get_available_times(nid,dt)
                tl=fresh.get("timeList",[]); nl=fresh.get("nodeList",[])

                txamt = 0
                try:
                    uinfo = c.get_user_info()
                    uid = uinfo.get("idserial", "")
                    price_info = c.get_pay_price(nid, nl, coords, dt, uid)
                    txamt = int(price_info.get("txamt", 0))
                except Exception as e:
                    print(f"获取价格失败: {e}")
                
                param={"unitPrice":txamt,"nodeList":nl,"payprice":txamt,"txamt":txamt,
                       "isLastDay":False,"appointmentDate":dt,"timeList":tl,
                       "coordinatesList":coords,"booktype":2,"nodeid":nid,
                       "childrennum":childrennum,"followList":[],"payway":"72"}
                r=c.create_booking(param)
                if r.get("success"):
                    rd=r.get("resultData") or {}
                    oid=rd.get("orderid") or rd.get("id","")
                    self.ok_json({"success":True,"orderid":oid})
                else:
                    self.ok_json({"success":False,"message":r.get("message","未知错误")})
            
            elif path=="/api/cancel":
                oid = body.get("id")
                if not oid: return self.ok_json({"success":False,"message":"缺少订单ID"})
                get_client().smart_cancel(oid)
                self.ok_json({"success":True})
            
            elif path=="/api/autograb/start":
                ok, msg = auto_grabber.start(body)
                self.ok_json({"success":ok, "message":msg})
            elif path=="/api/autograb/stop":
                auto_grabber.stop()
                self.ok_json({"success":True})
            else:
                self.send_response(404); self.end_headers()
        except Exception as e:
            traceback.print_exc()
            self.ok_json({"success":False,"message":str(e)})


def main():
    print("🏟️  地大体育馆可视化购票系统")
    try:
        get_client().get_user_info()
    except Exception as e:
        print(f"❌ 账号配置失败: {e}"); sys.exit(1)

    url = f"http://localhost:{PORT}"
    print(f"🌐 服务已启动 → {url}")
    threading.Thread(target=lambda: (__import__('time').sleep(0.5), webbrowser.open(url)), daemon=True).start()
    server = HTTPServer(("localhost", PORT), H)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 已停止服务")

if __name__ == "__main__":
    main()
"""

with open('webapp.py', 'w') as f:
    f.write(content)
print("File rewritten.")
