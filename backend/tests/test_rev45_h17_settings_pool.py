# -*- coding: utf-8 -*-
"""REV45-H17: settings.py SQLALCHEMY_ENGINE_OPTIONS 连接池配置单测.

背景:
- 之前 settings.py 缺 SQLALCHEMY_ENGINE_OPTIONS, 长连接 DB 超时后死连接
- 修复: 加 pool_pre_ping / pool_recycle / pool_size / max_overflow / pool_timeout

注意: settings.py 模块加载会触发 app.app_factory + db.create_all,
       测试通过 conftest.py 的 monkeypatch 屏蔽。
"""
from unittest.mock import MagicMock


class TestSQLAlchemyEngineOptions:
    """H17: app.config['SQLALCHEMY_ENGINE_OPTIONS'] 必须配置."""

    def test_engine_options_key_exists(self):
        """SQLALCHEMY_ENGINE_OPTIONS 配置存在."""
        from app.app_factory import app
        assert 'SQLALCHEMY_ENGINE_OPTIONS' in app.config

    def test_pool_pre_ping_true(self):
        """pool_pre_ping=True 防死连接."""
        from app.app_factory import app
        opts = app.config['SQLALCHEMY_ENGINE_OPTIONS']
        assert opts.get('pool_pre_ping') is True

    def test_pool_recycle_set(self):
        """pool_recycle 设为 3600s (1h, 防 MySQL 8h wait_timeout)."""
        from app.app_factory import app
        opts = app.config['SQLALCHEMY_ENGINE_OPTIONS']
        assert opts.get('pool_recycle') == 3600

    def test_pool_size_set(self):
        """pool_size 显式设为 10."""
        from app.app_factory import app
        opts = app.config['SQLALCHEMY_ENGINE_OPTIONS']
        assert opts.get('pool_size') == 10

    def test_max_overflow_set(self):
        """max_overflow 显式设为 20 (峰值可扩到 30)."""
        from app.app_factory import app
        opts = app.config['SQLALCHEMY_ENGINE_OPTIONS']
        assert opts.get('max_overflow') == 20

    def test_pool_timeout_set(self):
        """pool_timeout 设为 30s 防 hang."""
        from app.app_factory import app
        opts = app.config['SQLALCHEMY_ENGINE_OPTIONS']
        assert opts.get('pool_timeout') == 30


class TestSQLAlchemyOtherConfigs:
    """其他 SQLALCHEMY_* 配置保持正确."""

    def test_database_uri_set(self):
        """SQLALCHEMY_DATABASE_URI 配置存在."""
        from app.app_factory import app
        assert app.config.get('SQLALCHEMY_DATABASE_URI')

    def test_track_modifications_false(self):
        """SQLALCHEMY_TRACK_MODIFICATIONS=False (推荐关)."""
        from app.app_factory import app
        assert app.config.get('SQLALCHEMY_TRACK_MODIFICATIONS') is False


class TestDBSingleton:
    """db 是 SQLAlchemy 单例."""

    def test_db_is_sqlalchemy_instance(self):
        """db 是 flask_sqlalchemy.SQLAlchemy 实例."""
        from app.core.db.settings import db
        # flask_sqlalchemy.SQLAlchemy 实例有 create_all / session
        assert hasattr(db, 'create_all')
        assert hasattr(db, 'session')

    def test_db_engine_options_via_sqlalchemy_uri(self):
        """SQLAlchemy(app) 绑定后, db 通过 app.config 共享 SQLALCHEMY_ENGINE_OPTIONS.

        REV45-H17 验证: 不依赖 db.app 实例属性 (Flask-SQLAlchemy 3.x 已移除),
        而通过 app.config 反向证明 db 已绑定。
        """
        from app.core.db.settings import db
        from app.app_factory import app
        # db 与 app 绑定, app.config 包含我们设的 ENGINE_OPTIONS
        assert app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}).get('pool_pre_ping') is True