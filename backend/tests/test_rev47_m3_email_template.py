"""REV46-M3: 邮件模板系统 (EMAIL_TEMPLATES + render).

- 新增 EMAIL_TEMPLATES 配置 (env OGS_EMAIL_TEMPLATES, JSON 格式)
- 新增 render_email_template(template_id, **kwargs) 函数
- 新增 SendMail.send_template(template_id, to_mail, to_send='', **kwargs) 方法
- 模板占位符用 {key} 形式, render 时替换为 kwargs[key]

测试覆盖:
  TestM3Config: EMAIL_TEMPLATES 配置存在
  TestM3RenderBasic: 基础模板渲染
  TestM3RenderNoKwargs: 无 kwargs 时不替换占位符
  TestM3TemplateNotFound: 不存在模板 ID 抛 EmailTemplateError
  TestM3TemplateBadFormat: 模板值非 dict 抛 EmailTemplateError
  TestM3PlaceholderRender: 占位符 {key} 被替换
  TestM3MimeType: mime_type 字段支持
  TestM3SendTemplate: send_template 完整流程
  TestM3StaticAnalysis: 源码标记
"""
import inspect
import json
from unittest import mock

import pytest


# =============================================================================
# TestM3Config: EMAIL_TEMPLATES 配置
# =============================================================================
class TestM3Config:
    """REV46-M3: EMAIL_TEMPLATES 配置存在."""

    def test_email_templates_exists(self):
        from app.core.config import EMAIL_TEMPLATES
        assert isinstance(EMAIL_TEMPLATES, dict)


# =============================================================================
# TestM3RenderBasic: 基础模板渲染
# =============================================================================
class TestM3RenderBasic:
    """REV46-M3: render_email_template 基础功能."""

    def test_render_with_kwargs(self):
        from app.tools.sendmail import render_email_template
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {
            'register': {
                'subject': '注册验证码',
                'body': '您的验证码: {code}, 5 分钟内有效',
                'mime_type': 'plain',
            }
        }):
            subject, body, mime_type = render_email_template(
                'register', code='123456'
            )
        assert subject == '注册验证码'
        assert '123456' in body
        assert mime_type == 'plain'

    def test_render_html_template(self):
        from app.tools.sendmail import render_email_template
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {
            'welcome': {
                'subject': 'Welcome {username}',
                'body': '<h1>Hello {username}</h1>',
                'mime_type': 'html',
            }
        }):
            subject, body, mime_type = render_email_template(
                'welcome', username='alice'
            )
        assert subject == 'Welcome alice'
        assert body == '<h1>Hello alice</h1>'
        assert mime_type == 'html'

    def test_render_no_kwargs(self):
        """无 kwargs 时, 占位符不被替换 (保留原文)."""
        from app.tools.sendmail import render_email_template
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {
            'static': {
                'subject': '静态主题',
                'body': '静态内容',
                'mime_type': 'plain',
            }
        }):
            subject, body, mime_type = render_email_template('static')
        assert subject == '静态主题'
        assert body == '静态内容'

    def test_render_with_empty_template(self):
        """模板无 subject/body 字段时返空."""
        from app.tools.sendmail import render_email_template
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {
            'empty': {'mime_type': 'plain'}
        }):
            subject, body, mime_type = render_email_template('empty')
        assert subject == ''
        assert body == ''


# =============================================================================
# TestM3TemplateNotFound: 不存在模板 ID 抛 EmailTemplateError
# =============================================================================
class TestM3TemplateNotFound:
    """REV46-M3: 不存在模板 ID 抛 EmailTemplateError."""

    def test_unknown_template_id_raises(self):
        from app.tools.sendmail import (
            render_email_template, EmailTemplateError
        )
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {}):
            with pytest.raises(EmailTemplateError) as exc_info:
                render_email_template('nonexistent')
        assert 'nonexistent' in str(exc_info.value)

    def test_empty_email_templates_raises(self):
        from app.tools.sendmail import (
            render_email_template, EmailTemplateError
        )
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {}):
            with pytest.raises(EmailTemplateError):
                render_email_template('any')


# =============================================================================
# TestM3TemplateBadFormat: 模板值非 dict 抛 EmailTemplateError
# =============================================================================
class TestM3TemplateBadFormat:
    """REV46-M3: 模板值非 dict 抛 EmailTemplateError."""

    def test_template_value_not_dict(self):
        from app.tools.sendmail import (
            render_email_template, EmailTemplateError
        )
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {
            'bad_template': 'not a dict',
        }):
            with pytest.raises(EmailTemplateError):
                render_email_template('bad_template')

    def test_email_templates_not_dict(self):
        """EMAIL_TEMPLATES 自身非 dict 时 (e.g. 配置错误), 抛错."""
        from app.tools.sendmail import (
            render_email_template, EmailTemplateError
        )
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES',
                        'not a dict'):
            with pytest.raises(EmailTemplateError):
                render_email_template('any')


# =============================================================================
# TestM3PlaceholderRender: 占位符被替换
# =============================================================================
class TestM3PlaceholderRender:
    """REV46-M3: {key} 占位符被 kwargs 替换."""

    def test_multiple_placeholders(self):
        from app.tools.sendmail import render_email_template
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {
            'multi': {
                'subject': '{action} for {name}',
                'body': 'Hi {name}, please {action}.',
                'mime_type': 'plain',
            }
        }):
            subject, body, _ = render_email_template(
                'multi', action='confirm', name='alice'
            )
        assert subject == 'confirm for alice'
        assert body == 'Hi alice, please confirm.'

    def test_kwargs_values_str_converted(self):
        """kwargs 值非 str 时被转为 str."""
        from app.tools.sendmail import render_email_template
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {
            'code': {
                'subject': 'code {n}',
                'body': 'pin: {n}',
                'mime_type': 'plain',
            }
        }):
            subject, body, _ = render_email_template('code', n=1234)
        assert subject == 'code 1234'
        assert body == 'pin: 1234'

    def test_missing_placeholder_raises(self):
        """模板有 {key} 但 kwargs 未提供 → 抛 EmailTemplateError."""
        from app.tools.sendmail import (
            render_email_template, EmailTemplateError
        )
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {
            'need_code': {
                'subject': '您的验证码',
                'body': 'code: {code}',
                'mime_type': 'plain',
            }
        }):
            with pytest.raises(EmailTemplateError):
                render_email_template('need_code')  # 缺 code


# =============================================================================
# TestM3MimeType: mime_type 字段支持
# =============================================================================
class TestM3MimeType:
    """REV46-M3: mime_type 字段 (plain / html / 默认 plain)."""

    def test_mime_type_default_plain(self):
        from app.tools.sendmail import render_email_template
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {
            'no_mime': {'subject': 's', 'body': 'b'}
        }):
            _, _, mime = render_email_template('no_mime')
        assert mime == 'plain'

    def test_mime_type_invalid_fallback_plain(self):
        from app.tools.sendmail import render_email_template
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {
            'bad_mime': {'subject': 's', 'body': 'b', 'mime_type': 'exe'}
        }):
            _, _, mime = render_email_template('bad_mime')
        assert mime == 'plain'


# =============================================================================
# TestM3SendTemplate: send_template 完整流程
# =============================================================================
class TestM3SendTemplate:
    """REV46-M3: SendMail.send_template 集成测试."""

    def test_send_template_calls_send(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {
            'verify': {
                'subject': 'verify {code}',
                'body': '您的验证码: {code}',
                'mime_type': 'plain',
            }
        }), \
             mock.patch.object(SendMail, 'send') as mock_send:
            sm.send_template('verify', to_mail='a@b.com',
                             to_send='S', code='9999')
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        # send(template_id, to_mail, to_send='', **kwargs) 实际是 send(to_mail, to_send, subject, body, mime_type)
        args = mock_send.call_args.args
        assert args[0] == 'a@b.com'  # to_mail
        assert args[1] == 'S'  # to_send
        assert 'verify 9999' in args[2]  # subject
        assert '9999' in args[3]  # body
        assert call_kwargs.get('mime_type') == 'plain'

    def test_send_template_missing_id_raises(self):
        from app.tools.sendmail import SendMail, EmailTemplateError
        sm = SendMail.__new__(SendMail)
        with mock.patch('app.tools.sendmail.EMAIL_TEMPLATES', {}):
            with pytest.raises(EmailTemplateError):
                sm.send_template('nonexistent', to_mail='a@b.com')


# =============================================================================
# TestM3StaticAnalysis: 源码标记
# =============================================================================
class TestM3StaticAnalysis:
    """REV46-M3: 源码标记."""

    def test_sendmail_has_m3_marker(self):
        from app.tools import sendmail
        source = inspect.getsource(sendmail)
        assert 'REV46-M3' in source

    def test_config_has_m3_marker(self):
        from app.core import config
        source = inspect.getsource(config)
        assert 'REV46-M3' in source
        assert 'EMAIL_TEMPLATES' in source

    def test_render_email_template_exists(self):
        from app.tools.sendmail import render_email_template
        assert callable(render_email_template)

    def test_send_template_method_exists(self):
        from app.tools.sendmail import SendMail
        assert hasattr(SendMail, 'send_template')
        assert callable(SendMail.send_template)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
