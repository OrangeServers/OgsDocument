-- =============================================================================
-- REV51 (I18N): t_settings 增加界面语言字段
-- =============================================================================
-- 全站中英双语：语言偏好与主题(color_matching)一样走服务端持久化。
-- 取值白名单 zh-CN | en-US（Settings.py 校验）；存量部署默认 zh-CN，行为不变。
-- 幂等：列已存在时跳过，可重复执行。

SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 't_settings'
      AND COLUMN_NAME = 'language'
);
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE `t_settings` ADD COLUMN `language` VARCHAR(10) NOT NULL DEFAULT ''zh-CN''',
    'SELECT "language 列已存在, 跳过" AS info');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 升级操作者目检
SELECT `name`, `language` FROM `t_settings`;
