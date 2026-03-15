"""
checkin.py 核心逻辑测试

覆盖:
- get_user_info: 成功、空响应体、HTTP 错误、网络异常
- execute_check_in: 成功、已签到、失败
- check_in_account: anyrouter 手动签到流程、agentrouter 自动签到流程
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 添加项目根目录到 PATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from checkin import execute_check_in, get_user_info
from utils.config import AccountConfig, AppConfig

# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def app_config():
	return AppConfig.load_from_env()


@pytest.fixture
def anyrouter_account():
	return AccountConfig(
		cookies={'session': 'test-session-anyrouter'},
		api_user='97750',
		provider='anyrouter',
		name='AnyRouter账号',
	)


@pytest.fixture
def agentrouter_account():
	return AccountConfig(
		cookies={'session': 'test-session-agentrouter'},
		api_user='76920',
		provider='agentrouter',
		name='AgentRouter账号',
	)


def make_mock_client(status_code: int, body=None, raise_exc=None):
	"""构造一个模拟的 httpx.AsyncClient"""
	mock_client = MagicMock()
	mock_response = MagicMock()
	mock_response.status_code = status_code

	if body is not None:
		text = json.dumps(body) if isinstance(body, dict) else body
		mock_response.text = text
		mock_response.json.return_value = body if isinstance(body, dict) else {}
	else:
		mock_response.text = ''

	if raise_exc:
		mock_client.get = AsyncMock(side_effect=raise_exc)
		mock_client.post = AsyncMock(side_effect=raise_exc)
	else:
		mock_client.get = AsyncMock(return_value=mock_response)
		mock_client.post = AsyncMock(return_value=mock_response)

	return mock_client


# ─────────────────────────────────────────────
# get_user_info 测试
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_user_info_anyrouter_success():
	"""AnyRouter 账号能正常获取用户信息"""
	client = make_mock_client(200, {'success': True, 'data': {'quota': 5000000, 'used_quota': 1000000}})
	result = await get_user_info(client, {}, 'https://anyrouter.top/api/user/self')
	assert result['success'] is True
	assert result['quota'] == 10.0  # 5000000 / 500000
	assert result['used_quota'] == 2.0  # 1000000 / 500000
	assert '$10.0' in result['display']


@pytest.mark.asyncio
async def test_get_user_info_agentrouter_success():
	"""AgentRouter 账号能正常获取用户信息"""
	client = make_mock_client(200, {'success': True, 'data': {'quota': 3000000, 'used_quota': 500000}})
	result = await get_user_info(client, {}, 'https://agentrouter.org/api/user/self')
	assert result['success'] is True
	assert result['quota'] == 6.0  # 3000000 / 500000
	assert result['used_quota'] == 1.0  # 500000 / 500000


@pytest.mark.asyncio
async def test_get_user_info_empty_body_returns_error():
	"""空响应体时返回明确错误（修复前会抛出 JSONDecodeError）"""
	client = make_mock_client(200, body='')
	result = await get_user_info(client, {}, 'https://agentrouter.org/api/user/self')
	assert result['success'] is False
	assert 'Empty response body' in result['error']


@pytest.mark.asyncio
async def test_get_user_info_whitespace_body_returns_error():
	"""全空白响应体也视为空"""
	client = make_mock_client(200, body='   ')
	result = await get_user_info(client, {}, 'https://agentrouter.org/api/user/self')
	assert result['success'] is False
	assert 'Empty response body' in result['error']


@pytest.mark.asyncio
async def test_get_user_info_http_401():
	"""HTTP 401 时返回错误"""
	client = make_mock_client(401)
	result = await get_user_info(client, {}, 'https://anyrouter.top/api/user/self')
	assert result['success'] is False
	assert 'HTTP 401' in result['error']


@pytest.mark.asyncio
async def test_get_user_info_http_500():
	"""HTTP 500 时返回错误"""
	client = make_mock_client(500)
	result = await get_user_info(client, {}, 'https://agentrouter.org/api/user/self')
	assert result['success'] is False
	assert 'HTTP 500' in result['error']


@pytest.mark.asyncio
async def test_get_user_info_network_exception():
	"""网络异常时返回错误而非崩溃"""
	client = make_mock_client(0, raise_exc=Exception('Connection refused'))
	result = await get_user_info(client, {}, 'https://anyrouter.top/api/user/self')
	assert result['success'] is False
	assert 'Connection refused' in result['error']


@pytest.mark.asyncio
async def test_get_user_info_api_returns_failure():
	"""API 返回 success=False 时处理正确"""
	client = make_mock_client(200, {'success': False, 'message': 'Unauthorized'})
	result = await get_user_info(client, {}, 'https://anyrouter.top/api/user/self')
	assert result['success'] is False


# ─────────────────────────────────────────────
# execute_check_in 测试
# ─────────────────────────────────────────────


def make_provider(domain: str, sign_in_path: str):
	p = MagicMock()
	p.domain = domain
	p.sign_in_path = sign_in_path
	return p


@pytest.mark.asyncio
async def test_execute_check_in_anyrouter_ret1():
	"""AnyRouter 签到接口返回 ret=1 表示成功"""
	client = make_mock_client(200, {'ret': 1, 'msg': '签到成功，获得10积分'})
	provider = make_provider('https://anyrouter.top', '/api/user/sign_in')
	result = await execute_check_in(client, 'AnyRouter账号', provider, {})
	assert result is True


@pytest.mark.asyncio
async def test_execute_check_in_code0_success():
	"""签到接口返回 code=0 表示成功"""
	client = make_mock_client(200, {'code': 0, 'msg': 'OK'})
	provider = make_provider('https://anyrouter.top', '/api/user/sign_in')
	result = await execute_check_in(client, 'AnyRouter账号', provider, {})
	assert result is True


@pytest.mark.asyncio
async def test_execute_check_in_already_checked():
	"""已签到时也算成功"""
	client = make_mock_client(200, {'ret': 0, 'msg': '已经签到过了'})
	provider = make_provider('https://anyrouter.top', '/api/user/sign_in')
	result = await execute_check_in(client, 'AnyRouter账号', provider, {})
	assert result is True


@pytest.mark.asyncio
async def test_execute_check_in_failure():
	"""签到失败时返回 False"""
	client = make_mock_client(200, {'ret': 0, 'msg': '签到失败'})
	provider = make_provider('https://anyrouter.top', '/api/user/sign_in')
	result = await execute_check_in(client, 'AnyRouter账号', provider, {})
	assert result is False


@pytest.mark.asyncio
async def test_execute_check_in_http_error():
	"""HTTP 错误时返回 False"""
	client = make_mock_client(500)
	provider = make_provider('https://anyrouter.top', '/api/user/sign_in')
	result = await execute_check_in(client, 'AnyRouter账号', provider, {})
	assert result is False


# ─────────────────────────────────────────────
# check_in_account 集成场景测试
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anyrouter_full_checkin_flow(anyrouter_account, app_config):
	"""
	AnyRouter 完整流程：WAF cookies → 获取签到前余额 → 手动签到 → 获取签到后余额
	验证两个账号信息都能被正确获取
	"""
	from checkin import check_in_account

	user_info_payload = {'success': True, 'data': {'quota': 5000000, 'used_quota': 1000000}}
	sign_in_payload = {'ret': 1, 'msg': '签到成功'}

	mock_response_user = MagicMock()
	mock_response_user.status_code = 200
	mock_response_user.text = json.dumps(user_info_payload)
	mock_response_user.json.return_value = user_info_payload

	mock_response_sign = MagicMock()
	mock_response_sign.status_code = 200
	mock_response_sign.text = json.dumps(sign_in_payload)
	mock_response_sign.json.return_value = sign_in_payload

	mock_client = MagicMock()
	# GET returns user info twice (before + after), POST returns sign-in result
	mock_client.get = AsyncMock(return_value=mock_response_user)
	mock_client.post = AsyncMock(return_value=mock_response_sign)
	mock_client.cookies = MagicMock()

	mock_async_cm = MagicMock()
	mock_async_cm.__aenter__ = AsyncMock(return_value=mock_client)
	mock_async_cm.__aexit__ = AsyncMock(return_value=None)

	with (
		patch('checkin.get_waf_cookies_with_playwright', new=AsyncMock(return_value={'acw_tc': 'waf-value'})),
		patch('httpx.AsyncClient', return_value=mock_async_cm),
	):
		success, info_before, info_after = await check_in_account(anyrouter_account, 0, app_config)

	assert success is True
	assert info_before['success'] is True
	assert info_after['success'] is True
	assert info_before['quota'] == 10.0
	assert info_after['quota'] == 10.0


@pytest.mark.asyncio
async def test_agentrouter_auto_checkin_success(agentrouter_account, app_config):
	"""
	AgentRouter 自动签到流程：第一次用户信息请求触发签到
	sign_in_path=None，仅通过用户信息请求确认签到
	"""
	from checkin import check_in_account

	user_info_payload = {'success': True, 'data': {'quota': 3000000, 'used_quota': 500000}}

	mock_response = MagicMock()
	mock_response.status_code = 200
	mock_response.text = json.dumps(user_info_payload)
	mock_response.json.return_value = user_info_payload

	mock_client = MagicMock()
	mock_client.get = AsyncMock(return_value=mock_response)
	mock_client.cookies = MagicMock()

	mock_async_cm = MagicMock()
	mock_async_cm.__aenter__ = AsyncMock(return_value=mock_client)
	mock_async_cm.__aexit__ = AsyncMock(return_value=None)

	with (
		patch('checkin.get_waf_cookies_with_playwright', new=AsyncMock(return_value={'acw_tc': 'waf-value'})),
		patch('httpx.AsyncClient', return_value=mock_async_cm),
	):
		success, info_before, info_after = await check_in_account(agentrouter_account, 1, app_config)

	assert success is True
	assert info_before['success'] is True
	assert info_after['success'] is True
	assert info_before['quota'] == 6.0


@pytest.mark.asyncio
async def test_agentrouter_auto_checkin_empty_body_is_failure(agentrouter_account, app_config):
	"""
	AgentRouter 两次用户信息请求均返回空体时，正确判断为失败（修复前误报成功）
	"""
	from checkin import check_in_account

	mock_response = MagicMock()
	mock_response.status_code = 200
	mock_response.text = ''  # 空响应体

	mock_client = MagicMock()
	mock_client.get = AsyncMock(return_value=mock_response)
	mock_client.cookies = MagicMock()

	mock_async_cm = MagicMock()
	mock_async_cm.__aenter__ = AsyncMock(return_value=mock_client)
	mock_async_cm.__aexit__ = AsyncMock(return_value=None)

	with (
		patch('checkin.get_waf_cookies_with_playwright', new=AsyncMock(return_value={'acw_tc': 'waf-value'})),
		patch('httpx.AsyncClient', return_value=mock_async_cm),
	):
		success, info_before, info_after = await check_in_account(agentrouter_account, 1, app_config)

	# 修复后：两次均为空体，auto_success=False
	assert success is False
	assert info_before['success'] is False
	assert info_after['success'] is False


@pytest.mark.asyncio
async def test_both_accounts_load_correctly():
	"""两个账号的配置（provider 名、cookie、api_user）能正确解析"""
	import os

	accounts_json = json.dumps(
		[
			{'name': 'AnyRouter账号', 'provider': 'anyrouter', 'cookies': {'session': 'abc'}, 'api_user': '97750'},
			{'name': 'AgentRouter账号', 'provider': 'agentrouter', 'cookies': {'session': 'xyz'}, 'api_user': '76920'},
		]
	)
	os.environ['ANYROUTER_ACCOUNTS'] = accounts_json

	from utils.config import load_accounts_config

	accounts = load_accounts_config()
	assert accounts is not None
	assert len(accounts) == 2

	ar = accounts[0]
	assert ar.name == 'AnyRouter账号'
	assert ar.provider == 'anyrouter'
	assert ar.api_user == '97750'
	assert ar.cookies == {'session': 'abc'}

	agent = accounts[1]
	assert agent.name == 'AgentRouter账号'
	assert agent.provider == 'agentrouter'
	assert agent.api_user == '76920'
	assert agent.cookies == {'session': 'xyz'}
