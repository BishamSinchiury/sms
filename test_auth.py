import requests
import json
import redis

base_url = "http://localhost:8000/api"

print("--- Login ---")
res1 = requests.post(f"{base_url}/sys/auth/login/", json={
    "email": "bishamsinchiury1116@gmail.com",
    "password": "Bisham@0411"
})
print("Login status:", res1.status_code, res1.text)

r = redis.Redis(host='127.0.0.1', port=6379, db=4)
keys = r.keys("*sys_admin_otp*")
if not keys:
    print("Could not find any OTP keys in DB=4!")
    print("Keys in DB=2:", redis.Redis(db=2).keys("*sys_admin_otp*"))
    print("Keys in DB=1:", redis.Redis(db=1).keys("*sys_admin_otp*"))
    exit(1)

import pickle
otp_bytes = r.get(keys[0])
otp = pickle.loads(otp_bytes)
print("Fetched OTP:", otp)

if not otp:
    print("Could not fetch OTP!")
    exit(1)

print("\n--- Verify OTP ---")
client = requests.Session()
res2 = client.post(f"{base_url}/sys/auth/verify-otp/", json={
    "email": "bishamsinchiury1116@gmail.com",
    "otp": otp
})
print("Verify OTP status:", res2.status_code, res2.text)
print("Cookies received:", client.cookies.get_dict())

print("\n--- Me Endpoint ---")
res3 = client.get(f"{base_url}/sys/auth/me/")
print("Me status:", res3.status_code, res3.text)
