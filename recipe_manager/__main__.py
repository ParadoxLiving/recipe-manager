"""python -m recipe_manager run [--host H --port P --config config.json]

RECIPE_MANAGER_TOKEN (if set) is the bearer token required to change or delete an existing
saved recipe; reading, searching and importing/saving new recipes never need it.
RECIPE_NEXUS_TOKEN (named by config's nexus.token_env) is the Nexus-Compute client credential
used for the LLM-backed improve/merge flows; without it those two endpoints return 503."""
import argparse
import os
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m recipe_manager')
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run')
    run.add_argument('--host', default='127.0.0.1')
    run.add_argument('--port', type=int, default=8807)
    run.add_argument('--config', help='JSON file (see recipe_manager/config.py)')
    run.add_argument('--forwarded-allow-ips', help='Proxies (comma-separated IPs, or *) whose '
                      'X-Forwarded-For/-Proto headers are trusted. Default: only this computer')
    options = parser.parse_args(argv)
    if options.command == 'run':
        if options.host not in ('127.0.0.1', 'localhost', '::1') and not os.environ.get('RECIPE_MANAGER_TOKEN'):
            sys.exit('Set RECIPE_MANAGER_TOKEN before listening beyond this computer')
        import logging

        import uvicorn

        from .app import create_app
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
        app = create_app(config_path=options.config)
        proxy = {'proxy_headers': True, 'forwarded_allow_ips': options.forwarded_allow_ips} if options.forwarded_allow_ips else {}
        uvicorn.run(app, host=options.host, port=options.port, log_level='info', **proxy)


if __name__ == '__main__':
    main()
