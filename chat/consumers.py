"""Matchmaking + WebRTC signaling. State is in memory, so run ONE server process."""
import json
import time
import uuid
from channels.generic.websocket import AsyncWebsocketConsumer

USERS = {}      # id -> consumer
PARTNER = {}    # id -> partner id
WAITING = None  # id waiting for a partner
IP_COUNT = {}   # ip -> open connections (never sent to clients)
BANS = {}       # ip -> ban expiry (epoch)
REPORTS = {}    # ip -> set of distinct reporter ips
MAX_CONN_PER_IP = 4
LAST_CLEAN = time.time()


def client_ip(scope):
    h = dict(scope.get("headers", []))
    fwd = h.get(b"x-forwarded-for", b"").decode().split(",")[0].strip()
    return fwd or (scope.get("client") or ["unknown"])[0]


class ChatConsumer(AsyncWebsocketConsumer):
    async def send_j(self, data):
        try:
            await self.send(text_data=json.dumps(data))
        except Exception:
            pass

    async def connect(self):
        global LAST_CLEAN
        self.id = uuid.uuid4().hex
        self.ip = client_ip(self.scope)
        self.bt, self.bn, self.registered = time.time(), 0, False
        now = time.time()
        if now - LAST_CLEAN > 3600:
            LAST_CLEAN = now
            REPORTS.clear()
            for k in [k for k, t in BANS.items() if t < now]:
                del BANS[k]
        await self.accept()
        if BANS.get(self.ip, 0) > now:
            await self.send_j({"t": "error", "msg": "You are temporarily blocked."})
            return await self.close()
        if IP_COUNT.get(self.ip, 0) >= MAX_CONN_PER_IP:
            await self.send_j({"t": "error", "msg": "Too many open tabs from your network."})
            return await self.close()
        IP_COUNT[self.ip] = IP_COUNT.get(self.ip, 0) + 1
        USERS[self.id] = self
        self.registered = True

    async def disconnect(self, code):
        if not self.registered:
            return
        USERS.pop(self.id, None)
        await self._leave()
        n = IP_COUNT.get(self.ip, 1) - 1
        if n > 0:
            IP_COUNT[self.ip] = n
        else:
            IP_COUNT.pop(self.ip, None)

    async def _leave(self):
        global WAITING
        if WAITING == self.id:
            WAITING = None
        p = PARTNER.pop(self.id, None)
        if p:
            PARTNER.pop(p, None)
            other = USERS.get(p)
            if other:
                await other.send_j({"t": "partner-left"})

    async def _find(self):
        global WAITING
        await self._leave()
        if self.id not in USERS:
            return
        if WAITING and WAITING != self.id and WAITING in USERS:
            other = USERS[WAITING]
            WAITING = None
            PARTNER[self.id], PARTNER[other.id] = other.id, self.id
            await other.send_j({"t": "matched", "initiator": True})
            await self.send_j({"t": "matched", "initiator": False})
        else:
            WAITING = self.id
            await self.send_j({"t": "waiting"})

    async def receive(self, text_data=None, bytes_data=None):
        now = time.time()
        if now - self.bt > 10:
            self.bt, self.bn = now, 0
        self.bn += 1
        if self.bn > 200:                       # rate limit: 200 msgs / 10s
            return
        if not text_data or len(text_data) > 20000:
            return
        try:
            d = json.loads(text_data)
        except ValueError:
            return
        if not isinstance(d, dict):
            return
        t = d.get("t")
        if t == "find":
            await self._find()
        elif t == "stop":
            await self._leave()
        elif t == "signal":
            await self._signal(d)
        elif t == "report":
            await self._report()

    async def _signal(self, d):
        other = USERS.get(PARTNER.get(self.id))
        if not other:
            return
        sdp, cand = d.get("sdp"), d.get("candidate")
        if isinstance(sdp, dict) and sdp.get("type") in ("offer", "answer") and isinstance(sdp.get("sdp"), str):
            await other.send_j({"t": "signal", "sdp": {"type": sdp["type"], "sdp": sdp["sdp"]}})
        elif isinstance(cand, dict) and isinstance(cand.get("candidate"), str):
            await other.send_j({"t": "signal", "candidate": cand})

    async def _report(self):
        other = USERS.get(PARTNER.get(self.id))
        if not other:
            return
        s = REPORTS.setdefault(other.ip, set())
        s.add(self.ip)
        if len(s) >= 3:                          # 3 distinct reporters -> 1 hour ban
            BANS[other.ip] = time.time() + 3600
            REPORTS.pop(other.ip, None)
            await other.send_j({"t": "error", "msg": "You have been blocked for reports."})
            await other.close()
