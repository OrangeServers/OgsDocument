from types import SimpleNamespace

from flask import Flask

from app.api import route


def test_property_view_is_evaluated_once_per_request():
    """状态变更型 @property 不能被路由存在性检查提前执行一次。"""
    import init

    calls = []

    class MutatingPropertyView:
        @property
        def create(self):
            calls.append("create")
            return {"code": 0, "call_count": len(calls)}

    isolated_app = Flask(__name__)
    module = SimpleNamespace(ROUTES=[
        route(
            "/test/property-single-evaluation",
            MutatingPropertyView,
            "create",
            need_auth=False,
            is_property=True,
            skip_csrf=True,
        ),
    ])

    original_app = init.app
    init.app = isolated_app
    init._reset_route_dup_state()
    try:
        init._register_routes_from_module(module)
        response = isolated_app.test_client().post(
            "/test/property-single-evaluation",
        )
    finally:
        init.app = original_app
        init._reset_route_dup_state()

    assert response.status_code == 200
    assert response.get_json() == {"code": 0, "call_count": 1}
    assert calls == ["create"]
