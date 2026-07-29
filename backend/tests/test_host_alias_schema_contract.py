import inspect

from app.assets.ServerManagement import (
    ServerUpdate,
    _HOST_ALIAS_RE,
)


def test_host_alias_limit_matches_database_schema():
    assert _HOST_ALIAS_RE.fullmatch("a" * 25)
    assert _HOST_ALIAS_RE.fullmatch("a" * 26) is None


def test_host_update_validates_before_database_write():
    source = inspect.getsource(ServerUpdate.update.fget)
    assert source.index("_validate_params") < source.index("int(self.id)")
