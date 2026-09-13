from app import app
client = app.test_client()
with client.session_transaction() as sess:
    sess['username'] = 'admin'
    sess['role'] = 'admin'
    sess['auditor'] = ''
    sess['csrf_token'] = 'abc123'
    print('session_before', dict(sess))
resp = client.get('/?tab=engagements')
print('status', resp.status_code)
print('location', resp.headers.get('Location'))
print(resp.get_data(as_text=True)[:300])
