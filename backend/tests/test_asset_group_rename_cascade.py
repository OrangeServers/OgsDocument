import inspect

from app.assets.ServerGroup import ServerGroupUpdate
from app.core.db.database import (
    t_auth_host_host_group,
    t_host,
)


def _foreign_key(column):
    return next(iter(column.foreign_keys))


def test_asset_group_update_relies_on_atomic_database_cascade():
    source = inspect.getsource(ServerGroupUpdate.update.fget)
    assert "t_host.query.filter_by(id=" not in source
    assert "t_auth_host_host_group.query" not in source
    assert "t_group.query.filter_by(id=self.id).update" in source


def test_asset_group_dependents_cascade_on_rename():
    host_fk = _foreign_key(t_host.__table__.columns["group"])
    auth_fk = _foreign_key(
        t_auth_host_host_group.__table__.columns["group_name"],
    )
    assert host_fk.onupdate == "CASCADE"
    assert auth_fk.onupdate == "CASCADE"
