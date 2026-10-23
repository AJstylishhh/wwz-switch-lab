"""Patch local mvp_server.py with soft-session layer. Safe to re-run."""
from pathlib import Path
import sys
p = Path("mvp_server.py")
if not p.exists():
    sys.exit("mvp_server.py not found")
text = p.read_text(encoding="utf-8")
if "soft_session=True" in text and "TEARDOWN_ROUTES" in text:
    print("Already soft-patched")
    sys.exit(0)
if "from wwz_wire import ENVIRONMENT_ROUTE, environment_result, describe_environment_request" in text and "scalar" not in text.split("from wwz_wire")[1].split("\n")[0]:
    text = text.replace(
        "from wwz_wire import ENVIRONMENT_ROUTE, environment_result, describe_environment_request",
        "from wwz_wire import ENVIRONMENT_ROUTE, environment_result, describe_environment_request, scalar",
    )
if "TEARDOWN_ROUTES" not in text:
    text = text.replace(
        'GUID_ROUTE = re.compile(r"^/[0-9a-f]{32}\\.svc/[0-9a-f]{32}$", re.I)\n',
        'GUID_ROUTE = re.compile(r"^/[0-9a-f]{32}\\.svc/[0-9a-f]{32}$", re.I)\n\n'
        'SIGNOUT_ROUTE = "/fb383fc41afb42ce8c3f91bf828ce5a6.svc/f81fca3efea5407ab0cd288a2ae2b9ca"\n'
        'PRESENCE_DISCONNECT_ROUTE = "/b89429154e224660837a4a307391b0b4.svc/2299e0e7d40548838e89bba0268ed3b2"\n'
        'TEARDOWN_ROUTES = {SIGNOUT_ROUTE, PRESENCE_DISCONNECT_ROUTE}\n\n'
        'def success_empty():\n    return scalar(1, 0)\n\n',
    )
text = text.replace(
    "def __init__(self, routes, capture_dir=None, max_body=2_000_000):\n"
    "        self.routes, self.capture_dir, self.max_body = routes, capture_dir, max_body\n"
    "        self.queue = QueueState()\n"
    "        self.auth_sessions = AuthSessions(self.queue)\n",
    "def __init__(self, routes, capture_dir=None, max_body=2_000_000, soft_session=True):\n"
    "        self.routes, self.capture_dir, self.max_body = routes, capture_dir, max_body\n"
    "        self.soft_session = soft_session\n"
    "        self.queue = QueueState(ttl=900, limit=512)\n"
    "        self.auth_sessions = AuthSessions(self.queue, limit=512)\n",
)
if "soft Success" not in text:
    text = text.replace(
        '            answer = app.routes.get(path)\n'
        '            if answer is None:\n'
        '                LOG.warning("Unmapped RPC: %s", path)\n'
        '                return self.reply(404, b"Unknown RPC", "text/plain")\n',
        '            if path in TEARDOWN_ROUTES or (length == 0 and path not in app.routes):\n'
        '                LOG.info("Teardown/empty Success on %s", path)\n'
        '                return self.reply(200, success_empty())\n'
        '            answer = app.routes.get(path)\n'
        '            if answer is None:\n'
        '                if getattr(app, "soft_session", True):\n'
        '                    LOG.warning("Unmapped RPC %s - soft Success", path)\n'
        '                    return self.reply(200, success_empty())\n'
        '                LOG.warning("Unmapped RPC: %s", path)\n'
        '                return self.reply(404, b"Unknown RPC", "text/plain")\n',
    )
old = (
    '            if path in POST_LOGIN_ROUTES and isinstance(answer[1], dict):\n'
    '                try:\n'
    '                    data, info = app.post_login.respond(path, raw)\n'
    '                except ValueError as exc:\n'
    '                    LOG.warning("Experimental post-login request rejected on %s: %s", path, exc)\n'
    '                    return self.reply(400, b"Invalid experimental RPC", "text/plain")\n'
    '                LOG.info("Experimental post-login reply: %s", info)\n'
    '                return self.reply(answer[0], data)\n'
)
new = (
    '            if path in POST_LOGIN_ROUTES and isinstance(answer[1], dict):\n'
    '                try:\n'
    '                    data, info = app.post_login.respond(path, raw)\n'
    '                    LOG.info("Experimental post-login reply: %s", info)\n'
    '                    return self.reply(answer[0], data)\n'
    '                except ValueError as exc:\n'
    '                    LOG.warning("Experimental post-login request rejected on %s: %s", path, exc)\n'
    '                    if getattr(app, "soft_session", True):\n'
    '                        return self.reply(200, success_empty())\n'
    '                    return self.reply(400, b"Invalid experimental RPC", "text/plain")\n'
)
if old in text:
    text = text.replace(old, new)
text = text.replace('ap.add_argument("--host", default="127.0.0.1")', 'ap.add_argument("--host", default="0.0.0.0")')
if "--no-soft" not in text:
    text = text.replace(
        'ap.add_argument("--no-tls", action="store_true", help="local testing ONLY")',
        'ap.add_argument("--no-tls", action="store_true", help="local testing ONLY")\n'
        '    ap.add_argument("--no-soft", action="store_true", help="strict 404/400 like pure research MVP")',
    )
text = text.replace(
    'app = App(read_routes(args.routes), args.capture_dir, args.max_body)',
    'app = App(read_routes(args.routes), args.capture_dir, args.max_body, soft_session=not getattr(args, "no_soft", False))\n'
    '    LOG.info("soft_session=%s (Grok session-hold layer on Matty MVP)", app.soft_session)',
)
if 'conf.get("datacenter_id", "local")' not in text:
    text = text.replace(
        '''            if route == ENVIRONMENT_ROUTE and conf["handler"] == "environment_list":
                data = environment_result(conf["address"], conf["port"], conf["name"],
                                          conf["environment_id"], conf["region"],
                                          datacenter_id=conf.get("datacenter_id"))''',
        '''            if route == ENVIRONMENT_ROUTE and conf["handler"] == "environment_list":
                dc = conf.get("datacenter_id", "local")
                if dc is False or dc == "":
                    dc = None
                data = environment_result(conf["address"], conf["port"], conf["name"],
                                          conf["environment_id"], conf["region"],
                                          datacenter_id=dc)'''
    )
if 'handler"] == "success_empty"' not in text:
    text = text.replace(
        '''            elif route in POST_LOGIN_ROUTES and conf["handler"] == POST_LOGIN_ROUTES[route]:
                data = {"post_login_handler": conf["handler"]}
            else:
                raise ValueError("unsupported handler")''',
        '''            elif route in POST_LOGIN_ROUTES and conf["handler"] == POST_LOGIN_ROUTES[route]:
                data = {"post_login_handler": conf["handler"]}
            elif conf["handler"] == "success_empty":
                data = success_empty()
            else:
                raise ValueError("unsupported handler")'''
    )
p.write_text(text, encoding="utf-8")
print("Patched", p)
