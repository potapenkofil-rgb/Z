import aiohttp

from config import CRYPTOBOT_TOKEN

API_URL = 'https://pay.crypt.bot/api'

try:
    from aiohttp_socks import ProxyConnector
    _connector_factory = lambda: ProxyConnector.from_url('socks5://127.0.0.1:10808')
except ImportError:
    _connector_factory = lambda: None


async def _post(method: str, payload: dict | None = None) -> dict:
    headers = {'Crypto-Pay-API-Token': CRYPTOBOT_TOKEN}
    async with aiohttp.ClientSession(connector=_connector_factory()) as s:
        async with s.post(f'{API_URL}/{method}', json=payload or {}, headers=headers) as r:
            data = await r.json()
    if not data.get('ok'):
        raise RuntimeError(f'CryptoBot API {method}: {data}')
    return data['result']


async def create_invoice(amount: float, asset: str = 'USDT',
                         description: str = '') -> dict:
    """Создать инвойс. Возвращает dict с invoice_id, pay_url, status."""
    return await _post('createInvoice', {
        'asset': asset,
        'amount': str(amount),
        'description': description,
        'paid_btn_name':  'callback',
        'paid_btn_url':   'https://t.me/rassyl_W_robot',
        'allow_anonymous': False,
    })


async def get_invoice(invoice_id: int) -> dict | None:
    """Получить инвойс по ID. Возвращает None если не найден."""
    result = await _post('getInvoices', {'invoice_ids': str(invoice_id)})
    items = result.get('items', [])
    return items[0] if items else None
