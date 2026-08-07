"""
地大体育馆购票系统 - 核心API封装库
"""
import json
import time
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import binascii

# ===== AES 加解密（与网页端完全一致）=====
AES_KEY = b'0102030405060708'
AES_IV  = b'0102030405060708'


def encrypt(data: dict) -> str:
    """将字典数据加密为 AES-CBC HEX 大写字符串（与前端 Encrypt 函数一致）"""
    plaintext = json.dumps(data, ensure_ascii=False)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    ciphertext = cipher.encrypt(pad(plaintext.encode('utf-8'), AES.block_size))
    return binascii.hexlify(ciphertext).decode().upper()


def decrypt(hex_str: str) -> dict:
    """解密 AES-CBC HEX 字符串（与前端 Decrypt 函数一致）"""
    raw = binascii.unhexlify(hex_str)
    import base64
    b64 = base64.b64encode(raw)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    decrypted = unpad(cipher.decrypt(base64.b64decode(b64)), AES.block_size)
    return json.loads(decrypted.decode('utf-8'))


# ===== API 客户端 =====
class VenueClient:
    """地大体育馆 API 客户端"""

    BASE_URL = "https://bdtyg.cugb.edu.cn/service/appointment/appointment"

    def __init__(self, token: str = None, timeout: int = 10):
        self.token = token or ""
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36",
            "Referer": "https://bdtyg.cugb.edu.cn/",
            "Origin": "https://bdtyg.cugb.edu.cn",
        })

    def _request(self, endpoint: str, data: dict = None) -> dict:
        """发送加密请求到 API（JSON 格式，加密 item 字段）"""
        url = self.BASE_URL + endpoint
        headers = {
            "token": self.token,
            "Content-Type": "application/json",
        }
        # 所有接口统一使用 JSON body，包含加密的 item 字段
        payload = {"item": encrypt(data or {})}
        resp = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _request_shell(self, endpoint: str, data: dict = None) -> dict:
        """不加密的 shell 请求（用于特殊接口）"""
        url = self.BASE_URL + endpoint
        resp = self.session.post(url, json=data or {}, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ---- 登录相关 ----
    def login_by_openid(self, openid: str, orgid: str) -> str:
        """通过 openid 登录，返回 token
        
        这是系统正式登录接口 - POST /phone/login/wxLogin
        传入 openid 和 orgid，返回 token、code、name 等用户信息。
        """
        login_data = {"openid": openid, "orgid": orgid}
        # 登录接口：JSON 格式，body 为 {"item": AES加密后的数据}
        resp = self.session.post(
            self.BASE_URL + "/phone/login/wxLogin",
            json={"item": encrypt(login_data)},
            headers={"token": "", "Content-Type": "application/json"},
            timeout=self.timeout,
        )
        result = resp.json()
        if result.get("success") and result.get("resultData"):
            rd = result["resultData"]
            self.token = rd.get("token", "")
            return self.token
        msg = result.get("message", "未知错误")
        raise Exception(f"登录失败: {msg}")

    def get_user_info(self) -> dict:
        """获取当前用户信息"""
        result = self._request("/userAddress/getUserInfo")
        return result.get("resultData", {})

    # ---- 场地查询 ----
    def get_booking_nodes(self, booktype: str = "2") -> list:
        """获取可预约场地列表
        
        Returns:
            场地节点列表，每项包含: nodeid, nodename, nodetype 等
        """
        result = self._request("/phone/getBookingNode", {"booktype": booktype})
        if result.get("success"):
            return result.get("resultData", [])
        raise Exception(f"获取场地列表失败: {result.get('message')}")

    def get_available_times(self, nodeid: str, selectdate: str) -> dict:
        """查询指定场地在某日期的可用时间段
        
        Args:
            nodeid: 场地节点ID
            selectdate: 日期，格式 YYYY-MM-DD
            
        Returns:
            包含 timeList（时间段列表）、nodeList（场地列表）等信息
        """
        result = self._request("/phone/bookingByTime", {
            "nodeid": nodeid,
            "selectdate": selectdate,
        })
        if result.get("success"):
            return result.get("resultData", {})
        raise Exception(f"查询时间段失败: {result.get('message')}")

    def get_pay_price(self, nodeid: str, node_list: list, reserve_times: list,
                      reserve_date: str, user_idserial: str) -> dict:
        """计算预约价格
        
        Args:
            nodeid: 场地节点ID
            node_list: 场地节点列表（从 get_available_times 返回）
            reserve_times: 选择的时间段列表（格式: [[行, 列], ...]）
            reserve_date: 预约日期
            user_idserial: 用户证件号
            
        Returns:
            包含 txamt（价格，单位分）等信息
        """
        result = self._request("/phone/getPayPrice", {
            "nodeList": node_list,
            "nodeid": nodeid,
            "reserveTime": reserve_times,
            "reserveDate": reserve_date,
            "accompanyPerson": [],
            "reservationPerson": user_idserial,
            "appointmentType": "2",
            "timeList": [],
        })
        if result.get("success") and result.get("message") == "成功":
            return result.get("resultData", {})
        raise Exception(f"获取价格失败: {result.get('message')}")

    def create_booking(self, param: dict) -> dict:
        """创建预约订单（免费场地）
        
        Args:
            param: 预约参数字典
            
        Returns:
            预约结果
        """
        param["payway"] = "72"
        result = self._request("/phone/createBookingBytime", param)
        return result

    # ---- 订单管理 ----
    def get_orders(self, status=None, page: int = 1, page_size: int = 20) -> list:
        """获取订单列表
        
        Args:
            status: 订单状态（None=全部, 5=待付款, 1=待使用, 2=已取消, 4=已完成）
            page: 页码
            page_size: 每页数量
            
        Returns:
            订单列表
        """
        data = {"pageNumber": page, "pageSize": page_size, "ordertype": 1}
        if status is not None:
            data["status"] = status
        result = self._request("/phone/payOrderForPhone", data)
        if result.get("success"):
            return result.get("resultData", {}).get("content", [])
        return []

    def get_order_detail(self, order_id: str) -> dict:
        """获取订单详情（包含取消所需的所有字段）
        
        参数: order_id 是订单列表中的 "id" 字段（非 orderid）
        返回字段: id, payallamt(金额), booktype, payway, paywayCode, status 等
        """
        result = self._request("/phone/payOrderDetails", {"id": str(order_id)})
        if result.get("success"):
            return result.get("resultData", {})
        raise Exception(f"获取订单详情失败: {result.get('message')}")

    def check_cancel_count(self, orderid: str) -> dict:
        """检查本月还可以取消几次"""
        result = self._request("/phone/cancelNumCheck", {"orderid": str(orderid)})
        return result

    def cancel_order(self, order_id: str) -> bool:
        """取消订单（免费/不需退款的情况）
        
        接口: POST /phone/cancelOrder
        参数: {"id": 订单列表中的 id 字段}
        
        Returns:
            True 表示取消成功
        """
        result = self._request("/phone/cancelOrder", {"id": str(order_id)})
        if result.get("success"):
            return True
        raise Exception(f"取消订单失败: {result.get('message')}")

    def cancel_booking(self, order_id: str) -> bool:
        """取消预约（适用于已付款或需退款的订单）
        
        接口: POST /phone/userCancelBooking
        参数: {"id", "txamt", "booktype", "payway", "paywayCode"}
        均来自订单详情 API
        """
        # 必须先获取订单详情
        detail = self.get_order_detail(str(order_id))
        cancel_data = {
            "id": detail.get("id", str(order_id)),
            "txamt": detail.get("payallamt") or detail.get("resamt") or "0",
            "booktype": detail.get("booktype", "2"),
            "payway": detail.get("payway", "72"),
            "paywayCode": detail.get("paywayCode", ""),
        }
        result = self._request("/phone/userCancelBooking", cancel_data)
        if result.get("success"):
            return True
        raise Exception(f"取消预约失败: {result.get('message')}")

    def smart_cancel(self, order_id: str) -> bool:
        """智能取消：自动判断使用哪种取消方式
        
        - 免费订单 (txamt=0 或 payway='72'): 用 cancelOrder
        - 付费订单: 用 userCancelBooking
        
        Returns:
            True 表示取消成功
        """
        detail = self.get_order_detail(str(order_id))
        txamt = int(detail.get("payallamt") or detail.get("resamt") or 0)
        
        if txamt == 0:
            # 免费: 用 cancelOrder
            result = self._request("/phone/cancelOrder", {"id": str(order_id)})
            if result.get("success"):
                return True
            raise Exception(f"取消失败: {result.get('message')}")
        else:
            # 付费: 用 userCancelBooking
            cancel_data = {
                "id": detail.get("id", str(order_id)),
                "txamt": str(txamt),
                "booktype": detail.get("booktype", "2"),
                "payway": detail.get("payway", "72"),
                "paywayCode": detail.get("paywayCode", ""),
            }
            result = self._request("/phone/userCancelBooking", cancel_data)
            if result.get("success"):
                return True
            raise Exception(f"取消失败: {result.get('message')}")
