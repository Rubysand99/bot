"""Stub 'rộng rãi' cho discord.* — mọi thuộc tính đều tồn tại, có thể kế thừa/gọi/làm decorator.
Chỉ dùng để import code cogs trong test; KHÔNG mô phỏng hành vi Discord thật."""
import sys, types

class _Meta(type):
    def __getitem__(cls, item):   # app_commands.Choice[str] ...
        return cls
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Any

class _Any(metaclass=_Meta):
    def __init_subclass__(cls, **kw): pass   # class X(Modal, title='...')
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k):
        return _Any()   # decorator → object (hỗ trợ cả @group.command(...) lồng nhau)
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Any()

class _Mod(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Any

class NotFound(Exception): pass
class HTTPException(Exception): pass
class Forbidden(HTTPException): pass

def install():
    if getattr(sys.modules.get("discord"), "_is_test_stub", False):
        return   # idempotent: nhiều file test cùng 1 process (unittest discover)
    for name in ("discord", "discord.ui", "discord.ext", "discord.ext.commands", "discord.ext.tasks",
                 "discord.app_commands", "discord.abc", "discord.utils"):
        m = _Mod(name)
        sys.modules[name] = m
    d = sys.modules["discord"]
    d._is_test_stub = True
    d.NotFound, d.HTTPException, d.Forbidden = NotFound, HTTPException, Forbidden
    d.ui = sys.modules["discord.ui"]; d.ext = sys.modules["discord.ext"]
    d.app_commands = sys.modules["discord.app_commands"]; d.abc = sys.modules["discord.abc"]
    d.utils = sys.modules["discord.utils"]
    d.ext.commands = sys.modules["discord.ext.commands"]; d.ext.tasks = sys.modules["discord.ext.tasks"]
    if "motor" not in sys.modules:
        m = types.ModuleType("motor"); ma = types.ModuleType("motor.motor_asyncio")
        ma.AsyncIOMotorClient = object; m.motor_asyncio = ma
        sys.modules["motor"] = m; sys.modules["motor.motor_asyncio"] = ma
    import os
    os.environ.setdefault("MONGO_URI", "mongodb://stub")

def install_optional_stubs():
    """aiohttp/httpx/... có thể chưa cài trong môi trường test — stub rỗng đủ để import."""
    import importlib
    for name in ("aiohttp", "httpx", "groq", "openai", "numpy"):
        try:
            importlib.import_module(name)
        except ImportError:
            sys.modules[name] = _Mod(name)
