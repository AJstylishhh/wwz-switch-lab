"""Regression tests for two newly observed protocol gaps.

All player identities/tokens are synthetic. Zero-argument RPCs have
unverified method semantics: the experimental ACK does not change state.
"""
import http.client
import threading
import unittest
from types import SimpleNamespace
from uuid import UUID

from lobby_registry import HANDLERS, LobbyRegistry
from mvp_server import App, Server, make_handler
from request_shape import POST_MATCH_USER_LOOKUP_CANDIDATE
from wwz_wire import blob, scalar, string, fields

START = next(p for p, n in HANDLERS.items() if n == "start")
STOP = next(p for p, n in HANDLERS.items() if n == "stop")
UNKNOWN_A = "/b89429154e224660837a4a307391b0b4.svc/a5849554ff43457e88339d6a58fd6116"
UNKNOWN_B = "/b89429154e224660837a4a307391b0b4.svc/f05e89628988405c89a51dc520957cae"


def person(i):
    return SimpleNamespace(user_guid=UUID(int=i), access="access-"+str(i),
                           auth="auth-"+str(i))


def search(name):
    return blob(1, scalar(1, 2)) + blob(2, scalar(1, 1)) + string(3, name)


def uid(i):
    from lobby_registry import user_id
    return blob(1, user_id(UUID(int=i)))


class Clock:
    now = 100
    def __call__(self):
        return self.now


class ProfileGraceTests(unittest.TestCase):
    def test_stop_retains_verified_pair_but_expires_without_renewal(self):
        clock = Clock()
        reg = LobbyRegistry(clock=clock, profile_grace_seconds=12)
        for i, name in ((1, "alice"), (2, "bob"), (3, "other")):
            reg.attach(name, person(i))
        reg.respond("alice", START, search("playlist0"))
        reg.respond("bob", START, search("playlist0"))
        reg.respond("alice", STOP, b"")
        self.assertNotEqual(reg.member_group["alice"], reg.member_group["bob"])
        known, scope = reg.profile_identities_for("bob")
        self.assertEqual("recent_pair", scope)
        self.assertEqual({UUID(int=1), UUID(int=2)}, set(known))
        known, scope = reg.profile_identities_for("alice")
        self.assertEqual("recent_pair", scope)
        self.assertNotIn(UUID(int=3), known)
        clock.now += 11
        reg.profile_identities_for("bob")  # must NOT renew the deadline
        clock.now += 2
        known, scope = reg.profile_identities_for("bob")
        self.assertEqual("current_solo", scope)
        self.assertNotIn(UUID(int=1), known)
        with self.assertRaises(ValueError):
            reg.profile_identities_for("not-authenticated")

    def test_disabled_grace_returns_only_current_solo(self):
        reg = LobbyRegistry(profile_grace_seconds=0)
        reg.attach("a", person(1)); reg.attach("b", person(2))
        reg.respond("a", START, search("p"))
        reg.respond("b", START, search("p"))
        reg.respond("a", STOP, b"")
        users, scope = reg.profile_identities_for("a")
        self.assertEqual("current_solo", scope)
        self.assertEqual({UUID(int=1)}, set(users))

    def test_grace_does_not_migrate_to_new_identity(self):
        reg = LobbyRegistry(profile_grace_seconds=20)
        reg.attach("a", person(1)); reg.attach("b", person(2))
        reg.respond("a", START, search("p"))
        reg.respond("b", START, search("p"))
        reg.respond("a", STOP, b"")
        reg.attach("a", person(3))
        users, scope = reg.profile_identities_for("a")
        self.assertNotIn(UUID(int=2), users)

    def test_grace_range_is_rejected(self):
        for value in (-1, 31, True, "5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                LobbyRegistry(profile_grace_seconds=value)
        with self.assertRaises(ValueError):
            App({}, profile_grace_seconds=12)
        with self.assertRaises(ValueError):
            App({}, lobby_mvp=True, lobby_session_ids=True,
                profile_grace_seconds=12)

    def test_verified_http_profile_after_stop_is_temporary(self):
        app = App({}, lobby_mvp=True, lobby_session_ids=True,
                  profile_grace_seconds=12,
                  experimental_public_user_data=True)
        a,b,c=person(11),person(12),person(13)
        sid={}
        for who in (a,b,c):
            key,_ = app.lobby_sessions.attach(
                app.source_key("127.0.0.1"),who)
            app.lobby_registry.attach(key,who)
            sid[who.user_guid]=key
        app.lobby_registry.respond(sid[a.user_guid], START,search("p"))
        app.lobby_registry.respond(sid[b.user_guid], START,search("p"))
        app.lobby_registry.respond(sid[a.user_guid], STOP,b"")
        server = Server(("127.0.0.1",0),make_handler(app))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            def call(who,body):
                h=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=3)
                try:
                    h.request("POST",POST_MATCH_USER_LOOKUP_CANDIDATE,
                              body=body,headers=({"Acl-Token":who.access} if who else {}))
                    r=h.getresponse();return r.status,r.read()
                finally: h.close()
            status,data=call(b,uid(11))
            self.assertEqual(200,status)
            self.assertEqual(0,next(v for n,w,v in fields(data) if n==1))
            for who,body in ((b,uid(13)),(None,uid(11))):
                self.assertEqual(404,call(who,body)[0])
            app.lobby_registry._recent_pair_profiles.clear()
            self.assertEqual(404,call(b,uid(11))[0])
        finally:
            server.shutdown();server.server_close();worker.join(timeout=3)


class UnknownPresenceProbeTests(unittest.TestCase):
    def run_http(self, flag):
        app=App({},lobby_mvp=True,lobby_session_ids=True,
                experimental_presence_empty_acks=flag)
        alice=person(1)
        key,_=app.lobby_sessions.attach(app.source_key("127.0.0.1"),alice)
        app.lobby_registry.attach(key,alice)
        server=Server(("127.0.0.1",0),make_handler(app))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            def post(path,payload,header):
                c=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=3)
                try:
                    c.request("POST",path,body=payload,headers=header)
                    r=c.getresponse();return r.status,r.read()
                finally:c.close()
            token={"Acl-Token":alice.access}
            for route in (UNKNOWN_A,UNKNOWN_B):
                code,payload=post(route,b"",token)
                self.assertEqual(200 if flag else 404,code)
                if flag:self.assertEqual(b"\x08\x00",payload)
                if flag:
                    self.assertEqual(400,post(route,b"\x08\x00",token)[0])
                    self.assertEqual(409,post(route,b"",{"Acl-Token":"invalid"})[0])
                    self.assertEqual(409,post(route,b"",{})[0])
            self.assertEqual(0,len(app.lobby_registry.groups))
        finally:
            server.shutdown();server.server_close();worker.join(timeout=3)

    def test_off_is_404(self):self.run_http(False)
    def test_on_has_no_lobby_side_effects(self):self.run_http(True)

    def test_requires_session_safe_mode(self):
        with self.assertRaises(ValueError):
            App({},experimental_presence_empty_acks=True)
        with self.assertRaises(ValueError):
            App({},lobby_mvp=True,experimental_presence_empty_acks=True)


if __name__=="__main__": unittest.main()
