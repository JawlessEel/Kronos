import pytest
from flask import Flask, jsonify
from flask_cors import CORS
from webui.access import configure_access


def client():
    app = Flask(__name__)
    CORS(app)
    app.add_url_rule('/', endpoint='dashboard', view_func=lambda: 'dashboard')
    app.add_url_rule('/api/test', endpoint='test', view_func=lambda: jsonify(success=True), methods=['GET', 'POST'])
    configure_access(app, 'a' * 40)
    return app.test_client()


def test_requires_long_private_token():
    with pytest.raises(ValueError):
        configure_access(Flask(__name__), 'short')


def test_anonymous_api_and_page_blocked():
    c = client()
    assert c.get('/api/test').status_code == 401
    assert c.get('/').location == '/login'


def test_login_origin_logout_and_private_headers():
    c = client()
    assert c.post('/login', data={'token': 'wrong'}).status_code == 200
    response = c.post('/login', data={'token': 'a' * 40}, base_url='https://kronos.example')
    assert response.status_code == 302
    assert 'Secure' in response.headers['Set-Cookie']
    assert 'HttpOnly' in response.headers['Set-Cookie']
    assert c.get('/', base_url='https://kronos.example').data == b'dashboard'
    assert c.post('/api/test', base_url='https://kronos.example', headers={'Origin': 'https://evil.example'}).status_code == 403
    assert c.post('/api/test', base_url='https://kronos.example').status_code == 403
    response = c.post('/api/test', base_url='https://kronos.example', headers={'Origin': 'https://kronos.example'})
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    response = c.get('/api/test', base_url='https://kronos.example', headers={'Origin': 'https://evil.example'})
    assert 'Access-Control-Allow-Origin' not in response.headers
    assert c.post('/logout', base_url='https://kronos.example', headers={'Origin':'https://kronos.example'}).status_code == 302
    assert c.get('/api/test', base_url='https://kronos.example').status_code == 401


def test_login_attempts_bounded():
    c = client()
    for _ in range(5):
        assert c.post('/login', data={'token':'wrong'}).status_code == 200
    assert c.post('/login', data={'token':'wrong'}).status_code == 429
