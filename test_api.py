import requests
import json
import os

# 1. 准备测试环境
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

LOGIN_URL = config["api"]["login_url"]
UPLOAD_URL = config["api"]["upload_url"]
USERNAME = config["api"]["username"]
PASSWORD = config["api"]["password"]
UPLOAD_TIMEOUT = config["upload"].get("timeout_seconds", 60)

# 随便找一个本地的测试文件，或者创建一个假的 excel 文件
TEST_FILE_PATH = "test_impedance.xlsx"
if not os.path.exists(TEST_FILE_PATH):
    with open(TEST_FILE_PATH, "wb") as f:
        f.write(b"dummy excel content")

print("=== 开始接口连通性测试 ===")
print("说明: 此脚本仅验证登录链路与上传接口联通性，测试文件是伪造的 Excel。")

# 2. 先登录获取 token
session = requests.Session()
login_payload = {
    "username": USERNAME,
    "password": PASSWORD
}

try:
    print(f"登录地址: {LOGIN_URL}")
    login_response = session.post(LOGIN_URL, json=login_payload, timeout=10)
    print(f"登录 HTTP 状态码: {login_response.status_code}")
    login_result = login_response.json()
    print("登录返回内容:")
    print(json.dumps(login_result, indent=4, ensure_ascii=False))

    token = login_result.get("token")
    if str(login_result.get("code")) != "20220" or not token:
        raise RuntimeError("登录失败，无法继续测试上传接口")

    session.headers.update({
        "Authorization": f"Bearer {token}"
    })

    # 3. 构造上传参数
    data = {
        "serialNo": ""
    }

    with open(TEST_FILE_PATH, "rb") as f:
        files = {
            "file": ("test_impedance.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        }
        
        print(f"请求地址: {UPLOAD_URL}")
        print(f"请求参数: {data}")
        print("发送请求中...")
        
        # 4. 发送请求
        response = session.post(UPLOAD_URL, files=files, data=data, timeout=UPLOAD_TIMEOUT)
        
        # 5. 打印结果
        print(f"\nHTTP 状态码: {response.status_code}")
        print("接口返回内容:")
        try:
            print(json.dumps(response.json(), indent=4, ensure_ascii=False))
        except ValueError:
            print(response.text)

except Exception as e:
    print(f"\n请求发生异常: {e}")

print("\n=== 测试结束 ===")
