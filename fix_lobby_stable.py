#!/usr/bin/env python3
"""Download research lobby_registry + apply stable online + soft-match patches."""
from __future__ import annotations

import ssl
import sys
import urllib.request
from pathlib import Path

URL = (
    "https://raw.githubusercontent.com/AJstylishhh/wwz-switch-lab/"
    "research/chatgpt-hydra-server-mvp/lobby_registry.py"
)


def main() -> None:
    path = Path(__file__).resolve().parent / "lobby_registry.py"
    ctx = ssl.create_default_context()
    print("Downloading research lobby_registry.py ...")
    with urllib.request.urlopen(URL, context=ctx, timeout=60) as resp:
        text = resp.read().decode("utf-8")
    if "matchmake_playlist" not in text or len(text) < 5000:
        sys.exit("Download failed or file too small")

    text = text.replace(
        '    return playlist.decode("utf-8")\n',
        '    return playlist.decode("utf-8", errors="replace").strip()\n',
        1,
    )

    old = """                playlist = matchmake_playlist(raw)
                # Join only a *queued* lobby with the same playlist. A squad
                # left in the local UI is not automatically public.
                others = [g for g in self.groups.values()
                          if g.queued and source not in g.members]
                compatible = [g for g in others if g.playlist == playlist]
                available = [g for g in compatible if len(g.members) < self._size(g)]
                candidate = min(available, key=lambda g: (g.created, g.lid.int),
                                default=None)
                details = {
                    "playlist_tag": self._playlist_tag(playlist),
                    "playlist_bytes": len(playlist.encode("utf-8")),
                    "other_queued_groups": len(others),
                    "same_playlist_groups": len(compatible),
                    "same_playlist_open_seats": len(available),
                }
                if candidate:
                    self._join_queue(source, candidate)
                    group = candidate
                    details["decision"] = "joined_existing_queue"
                else:
                    group = group or self._group(source, create=True)
                    group.playlist = playlist
                    group.queued = True
                    self._touch(group)
                    details["decision"] = ("no_other_queue" if not others else
                                           "playlist_differs" if not compatible else
                                           "matching_queue_full")
                details["max_count"] = self._size(group)
"""
    new = """                playlist = matchmake_playlist(raw)
                others = [g for g in self.groups.values()
                          if g.queued and source not in g.members]
                compatible = [g for g in others if g.playlist == playlist]
                available = [g for g in compatible if len(g.members) < self._size(g)]
                soft = [g for g in others if len(g.members) < self._size(g)]
                candidate = min(available, key=lambda g: (g.created, g.lid.int),
                                default=None)
                soft_candidate = soft[0] if (candidate is None and len(soft) == 1) else None
                details = {
                    "playlist_tag": self._playlist_tag(playlist),
                    "playlist_bytes": len(playlist.encode("utf-8")),
                    "request_bytes": len(raw),
                    "other_queued_groups": len(others),
                    "same_playlist_groups": len(compatible),
                    "same_playlist_open_seats": len(available),
                    "soft_open_seats": len(soft),
                }
                if candidate:
                    self._join_queue(source, candidate)
                    group = candidate
                    details["decision"] = "joined_existing_queue"
                elif soft_candidate is not None:
                    self._join_queue(source, soft_candidate)
                    group = soft_candidate
                    details["decision"] = "joined_soft_playlist_mismatch"
                else:
                    group = group or self._group(source, create=True)
                    group.playlist = playlist
                    group.queued = True
                    self._touch(group)
                    details["decision"] = ("no_other_queue" if not others else
                                           "playlist_differs" if not compatible else
                                           "matching_queue_full")
                details["max_count"] = self._size(group)
"""
    if old not in text:
        sys.exit("match block not found in downloaded file")
    text = text.replace(old, new, 1)

    old2 = """        with self.lock:
            self._expire()
            self._require(source)
            group = self._group(source)
            details = {}
"""
    new2 = """        with self.lock:
            self._expire()
            # Status polls must not 400 if Dequeue was not correlated yet.
            if kind in ("squad_status", "match_status", "observed_scalar"):
                if source not in self.identities:
                    if kind == "squad_status":
                        return presence_status_reply("squad"), {
                            "stage": "lobby_mvp_status_no_auth", "kind": kind}
                    if kind == "match_status":
                        return presence_status_reply("matchmake"), {
                            "stage": "lobby_mvp_status_no_auth", "kind": kind}
                    return SUCCESS, None
            self._require(source)
            group = self._group(source)
            details = {}
"""
    if old2 not in text:
        sys.exit("respond() lock block not found")
    text = text.replace(old2, new2, 1)

    path.write_text(text, encoding="utf-8")
    print("Wrote", path, "bytes=", path.stat().st_size)
    print("OK: soft-match + status-without-Dequeue")
    print("Restart server WITH --lobby-mvp after both clients fully quit.")


if __name__ == "__main__":
    main()
