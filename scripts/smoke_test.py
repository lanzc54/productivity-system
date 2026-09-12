import time, re, requests
s = requests.Session()
# wait for /health
for i in range(30):
    try:
        r = s.get('http://127.0.0.1:5000/health', timeout=2)
        if r.status_code == 200:
            print('health ok')
            break
    except Exception:
        pass
    time.sleep(1)
else:
    print('health failed')
    raise SystemExit(1)

# get login page and csrf token
r = s.get('http://127.0.0.1:5000/login')
match = re.search(r"name=[\'\"]csrf_token[\'\"] value=[\'\"]([^\'\"]+)[\'\"]", r.text)
if not match:
    print('no csrf')
    raise SystemExit(1)
token = match.group(1)
print('csrf:', token[:8])
# post login
payload = {'username':'admin','password':'ChangeMe123!','csrf_token':token}
r = s.post('http://127.0.0.1:5000/login', data=payload, allow_redirects=False)
print('login status', r.status_code)
# fetch admin sessions
r = s.get('http://127.0.0.1:5000/admin/sessions')
print('admin/sessions status', r.status_code)
print(r.text[:1600])
