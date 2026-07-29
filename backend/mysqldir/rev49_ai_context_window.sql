-- =============================================================================
-- REV49: AI Provider 上下文能力
-- =============================================================================
-- 旧配置统一回填标准 256K。管理员确认模型支持百万上下文后，才可在设置页
-- 将能力上限切换为 1M；会话仍默认使用标准档。

SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 't_ai_provider'
      AND COLUMN_NAME = 'context_window_tokens'
);
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE `t_ai_provider` ADD COLUMN `context_window_tokens` INT NOT NULL DEFAULT 262144',
    'SELECT "context_window_tokens 列已存在, 跳过" AS info');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SELECT
    `provider_code`,
    `model`,
    `context_window_tokens`
FROM `t_ai_provider`
ORDER BY `provider_code`;
