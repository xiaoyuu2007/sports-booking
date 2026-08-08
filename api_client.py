"""
地大体育馆购票系统 - 核心API封装库
"""
import json
import time
import base64
import binascii
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


class APIClientError(Exception):
    """API 客户端异常"""
    pass


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
    try:
        raw = binascii.unhexlify(hex_str)
        cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
        decrypted = unpad(cipher.decrypt(raw), AES.block_size)
        return json.loads(decrypted.decode('utf-8'))
    except Exception as e:
        raise APIClientError(f"解密失败: {e}") from e


# ===== API 客户端 =====
class VenueClient:
    """地大体育馆 API 客户端"""

    BASE_URL = "https://bdtyg.cugb.edu.cn/service/appointment/appointment"

    def __init__(self, token: str = None, timeout=(3.05, 10)):
        self.token = token or ""
        if isinstance(timeout, (int, float)):
            self.timeout = (float(timeout), float(timeout))
        else:
            self.timeout = timeout or (3.05, 10)
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36",
            "Referer": "https://bdtyg.cugb.edu.cn/",
            "Origin": "https://bdtyg.cugb.edu.cn",
        })

    def close(self):
        """关闭 Session 资源"""
        if hasattr(self, "session") and self.session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _request(self, endpoint: str, data: dict = None) -> dict:
        """发送加密请求到 API（JSON 格式，加密 item 字段）"""
        url = self.BASE_URL + endpoint
        headers = {
            "token": self.token,
            "Content-Type": "application/json",
        }
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
        """通过 openid 登录，返回 token"""
        login_data = {"openid": openid, "orgid": orgid}
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
        raise APIClientError(f"登录失败: {msg}")

    def get_user_info(self) -> dict:
        """获取当前用户信息"""
        result = self._request("/userAddress/getUserInfo")
        if result.get("success"):
            return result.get("resultData", {})
        raise APIClientError(f"获取用户信息失败: {result.get('message', '未知错误')}")

    # ---- 场地查询 ----
    def get_booking_nodes(self, booktype: str = "2") -> list:
        """获取可预约场地列表"""
        result = self._request("/phone/getBookingNode", {"booktype": booktype})
        if result.get("success"):
            return result.get("resultData", [])
        raise APIClientError(f"获取场地列表失败: {result.get('message', '未知错误')}")

    def get_available_times(self, nodeid: str, selectdate: str) -> dict:
        """查询指定场地在某日期的可用时间段"""
        result = self._request("/phone/bookingByTime", {
            "nodeid": nodeid,
            "selectdate": selectdate,
        })
        if result.get("success"):
            return result.get("resultData", {})
        raise APIClientError(f"查询时间段失败: {result.get('message', '未知错误')}")

    def get_pay_price(self, nodeid: str, node_list: list, reserve_times: list,
                      reserve_date: str, user_idserial: str) -> dict:
        """计算预约价格"""
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
        raise APIClientError(f"获取价格失败: {result.get('message', '未知错误')}")

    def create_booking(self, param: dict) -> dict:
        """创建预约订单（免费场地）"""
        param["payway"] = "72"
        result = self._request("/phone/createBookingBytime", param)
        if isinstance(result, dict):
            return result
        raise APIClientError("创建预约接口返回非字典类型")

    # ---- 订单管理 ----
    def get_orders(self, status=None, page: int = 1, page_size: int = 20) -> list:
        """获取订单列表"""
        data = {"pageNumber": page, "pageSize": page_size, "ordertype": 1}
        if status is not None:
            data["status"] = status
        result = self._request("/phone/payOrderForPhone", data)
        if result.get("success"):
            return result.get("resultData", {}).get("content", [])
        raise APIClientError(f"获取订单列表失败: {result.get('message', '未知错误')}")

    def get_order_detail(self, order_id: str) -> dict:
        """获取订单详情"""
        result = self._request("/phone/payOrderDetails", {"id": str(order_id)})
        if result.get("success"):
            return result.get("resultData", {})
        raise APIClientError(f"获取订单详情失败: {result.get('message', '未知错误')}")

    def check_cancel_count(self, orderid: str) -> dict:
        """检查本月还可以取消几次"""
        result = self._request("/phone/cancelNumCheck", {"orderid": str(orderid)})
        if result.get("success"):
            return result
        raise APIClientError(f"检查取消次数失败: {result.get('message', '未知错误')}")

    def cancel_order(self, order_id: str) -> bool:
        """取消订单（免费/不需退款的情况）"""
        result = self._request("/phone/cancelOrder", {"id": str(order_id)})
        if result.get("success"):
            return True
        raise APIClientError(f"取消订单失败: {result.get('message', '未知错误')}")

    def cancel_booking(self, order_id: str) -> bool:
        """取消预约（适用于已付款或需退款的订单）"""
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
        raise APIClientError(f"取消预约失败: {result.get('message', '未知错误')}")

    def smart_cancel(self, order_id: str) -> bool:
        """智能取消：自动判断使用哪种取消方式"""
        detail = self.get_order_detail(str(order_id))
        txamt = int(detail.get("payallamt") or detail.get("resamt") or 0)
        
        if txamt == 0:
            result = self._request("/phone/cancelOrder", {"id": str(order_id)})
            if result.get("success"):
                return True
            raise APIClientError(f"取消失败: {result.get('message', '未知错误')}")
        else:
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
            raise APIClientError(f"取消失败: {result.get('message', '未知错误')}")
