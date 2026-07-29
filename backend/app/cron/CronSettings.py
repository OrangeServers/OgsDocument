from app.app_factory import app
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
import pytz
import warnings

# 抑制 pytz-deprecation-shim 的警告（tzlocal 4.x 通过 shim 包装时区对象触发）
warnings.filterwarnings('ignore', message='.*pytz.*interface.*|.*normalize method.*')

executors = {
    "default": ThreadPoolExecutor(max_workers=10)
}

# 显式指定 pytz 原生时区，绕过 tzlocal 的 pytz-deprecation-shim，避免 PytzUsageWarning
# ti3-HINT: scheduler 是动态挂载到 Flask app 的运行时属性, mypy 静态看不到
app.scheduler = BackgroundScheduler(executors=executors, timezone=pytz.timezone('Asia/Shanghai'))  # type: ignore[attr-defined]
scheduler = app.scheduler  # type: ignore[attr-defined]
