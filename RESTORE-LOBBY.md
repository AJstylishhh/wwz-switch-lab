Run once after git pull:

```
py restore_lobby_registry.py
```

This rebuilds lobby_registry.py with soft playlist match + status-without-Dequeue.
Then:

```
py mvp_server.py --host 0.0.0.0 --ports 11702,11704 --routes routes.session-test.local.json --lobby-mvp
```
