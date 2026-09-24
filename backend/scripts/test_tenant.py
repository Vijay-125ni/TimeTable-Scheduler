import requests

# Assuming backend runs on 8000
BASE_URL = "http://localhost:8000/api"

print("1. Registering new admin...")
reg_data = {
    "username": "test_tenant_admin1",
    "email": "tenant1@example.com",
    "password": "password123",
    "full_name": "Tenant One Admin",
    "role": "admin"
}
res = requests.post(f"{BASE_URL}/auth/register", json=reg_data)
if res.status_code == 200:
    admin_data = res.json()
    print("✅ Admin Registered:", admin_data)
else:
    print("❌ Failed:", res.status_code, res.text)
    

print("\n2. Logging in as new admin...")
login_res = requests.post(f"{BASE_URL}/auth/login", data={"username": "test_tenant_admin1", "password": "password123"})
if login_res.status_code == 200:
    token = login_res.json()["access_token"]
    print("✅ Admin Logged In")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\n3. Creating a department in Tenant DB...")
    dept_res = requests.post(f"{BASE_URL}/departments", json={"name": "Computer Science", "code": "CS"}, headers=headers)
    print(dept_res.status_code, dept_res.text)
    
    print("\n4. Creating a faculty login account...")
    fac_data = {
        "username": "fac1_cs",
        "email": "fac1@tenant1.com",
        "password": "password123",
        "full_name": "Faculty One"
    }
    fac_res = requests.post(f"{BASE_URL}/auth/faculty", json=fac_data, headers=headers)
    print(fac_res.status_code, fac_res.text)

else:
    print("❌ Failed Login:", login_res.status_code, login_res.text)
