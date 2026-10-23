"""python -m server [--host 0.0.0.0] [--port 8600]"""

import argparse

from server.app import serve

parser = argparse.ArgumentParser(description="Deutsch mit Geschichten accounts server")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=8600)
args = parser.parse_args()

httpd = serve(args.host, args.port)
print(f"Accounts server on http://{args.host}:{args.port}")
try:
    httpd.serve_forever()
except KeyboardInterrupt:
    pass
