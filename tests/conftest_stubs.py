"""Stub tối thiểu cho discord / motor để test logic thuần mà không cần cài thư viện thật."""
import sys, types, copy

def install():
    """Dùng chung 1 bộ stub 'rộng rãi' (stubs_discord) cho mọi file test."""
    import stubs_discord
    stubs_discord.install()

class FakeCol:
    def __init__(self):
        self.docs = {}
        self.fail_reads = 0
        self.fail_writes = 0
        self.writes = []   # (filter_id, ops)
    async def find_one(self, flt):
        if self.fail_reads > 0:
            self.fail_reads -= 1
            raise RuntimeError("simulated Mongo read failure")
        d = self.docs.get(flt["_id"])
        return copy.deepcopy(d) if d is not None else None
    async def insert_one(self, doc):
        self.docs[doc["_id"]] = copy.deepcopy(doc)
    async def update_one(self, flt, ops, upsert=False):
        if self.fail_writes > 0:
            self.fail_writes -= 1
            raise RuntimeError("simulated Mongo write failure")
        self.writes.append((flt["_id"], copy.deepcopy(ops)))
        d = self.docs.setdefault(flt["_id"], {"_id": flt["_id"]}) if upsert else self.docs[flt["_id"]]
        for k, v in ops.get("$set", {}).items():
            d[k] = copy.deepcopy(v)
        for k in ops.get("$unset", {}):
            d.pop(k, None)
    def find(self, flt):
        docs = list(self.docs.values())
        class _It:
            def __aiter__(self_):
                async def gen():
                    for x in docs: yield x
                return gen()
        return _It()
