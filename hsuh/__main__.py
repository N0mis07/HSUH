"""Explicit loopback bind. Public traffic must arrive through authenticated Access."""
import argparse
import uvicorn
from .app import create_app


def main():
    parser = argparse.ArgumentParser(description='HSUH browser workspace (loopback only)')
    parser.add_argument('--port', type=int, default=8110)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose an unprivileged port between 1024 and 65535')
    uvicorn.run(create_app(port=args.port), host='127.0.0.1', port=args.port,
                access_log=False, proxy_headers=False, log_level='warning', limit_concurrency=32,
                timeout_keep_alive=5)


if __name__ == '__main__':
    main()
