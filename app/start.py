import os
import uvicorn
if __name__ == '__main__':
    from app.infrastructure.observability.logging import configure
    configure()
    uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.getenv('PORT','8000')), workers=1, access_log=False, log_level='info', log_config=None, proxy_headers=True, forwarded_allow_ips=os.getenv('FORWARDED_ALLOW_IPS','127.0.0.1'), timeout_graceful_shutdown=30)
