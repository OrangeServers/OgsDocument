-- =============================================================================
-- REV45-H8 (R2-5): 给关键业务表加 created_at / updated_at 时间戳
-- =============================================================================
-- 问题: t_host / t_sys_user / t_acc_user / t_auth_host / t_cron 无时间戳字段,
--   无法审计: 何时添加的资产/账号/SSH 用户/cron, 何时被修改
-- 修复:
--   - 5 张关键业务表加 created_at, updated_at 两列 (DATETIME, UTC)
--   - 老数据回填: created_at/updated_at = NOW() (上线时间作为近似创建时间)
--   - 加索引: 按时间范围查/排序 频繁
--
-- 注意:
--   - DATETIME 不带时区, 业务读出后按需转本地时区
--   - 用 UTC 是为跨时区一致; 业务层显示时转为本地时间
--   - 幂等: 用 stored procedure 防重复加列

DROP PROCEDURE IF EXISTS _add_timestamps;
DELIMITER //
CREATE PROCEDURE _add_timestamps(IN p_table VARCHAR(64))
BEGIN
    DECLARE has_created INT DEFAULT 0;
    DECLARE has_updated INT DEFAULT 0;

    -- 检查列是否已存在 (information_schema)
    SELECT COUNT(*) INTO has_created
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = p_table
      AND COLUMN_NAME = 'created_at';

    SELECT COUNT(*) INTO has_updated
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = p_table
      AND COLUMN_NAME = 'updated_at';

    -- 加 created_at (若不存在)
    IF has_created = 0 THEN
        SET @sql = CONCAT(
            'ALTER TABLE `', p_table, '` ADD COLUMN `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP'
        );
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;

        -- 加索引
        SET @sql = CONCAT(
            'ALTER TABLE `', p_table, '` ADD INDEX `idx_', p_table, '_created_at` (`created_at`)'
        );
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;

    -- 加 updated_at (若不存在)
    IF has_updated = 0 THEN
        SET @sql = CONCAT(
            'ALTER TABLE `', p_table, '` ADD COLUMN `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'
        );
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;

        -- 加索引
        SET @sql = CONCAT(
            'ALTER TABLE `', p_table, '` ADD INDEX `idx_', p_table, '_updated_at` (`updated_at`)'
        );
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

-- 1) t_host
CALL _add_timestamps('t_host');
-- 2) t_sys_user
CALL _add_timestamps('t_sys_user');
-- 3) t_acc_user
CALL _add_timestamps('t_acc_user');
-- 4) t_auth_host
CALL _add_timestamps('t_auth_host');
-- 5) t_cron
CALL _add_timestamps('t_cron');

-- 清理 stored procedure
DROP PROCEDURE _add_timestamps;

-- 验证: 5 张表都应有 created_at / updated_at 列
SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('t_host', 't_sys_user', 't_acc_user', 't_auth_host', 't_cron')
  AND COLUMN_NAME IN ('created_at', 'updated_at')
ORDER BY TABLE_NAME, COLUMN_NAME;

-- 期望: 上面 SELECT 返回 10 行 (5 张表 x 2 列)
-- R2-5 ALTER 完成
