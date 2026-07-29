-- =============================================================================
-- REV47-M6: 全表 soft_delete 字段 (7 张业务表)
-- =============================================================================
-- 目的: 给 7 张业务实体表加 is_deleted 字段, 实现软删除
-- 背景: 之前 db.session.delete() 物理删除, 误删/恶意删后无恢复手段
--       软删除: 标记 is_deleted=True, 业务查询 .filter_by(is_deleted=False) 隐藏
-- 表范围 (7 张业务实体):
--   - t_host       : 资产主机
--   - t_sys_user   : 资产系统用户
--   - t_acc_user   : 平台账号
--   - t_group      : 主机组
--   - t_acc_group  : 账号组
--   - t_auth_host  : 授权策略
--   - t_cron       : 定时任务
-- 不涉及 (11 张):
--   - 日志表 (3): t_login_log / t_command_log / t_cz_log  -- append-only
--   - 统计表 (1): t_line_chart  -- 按日清理
--   - 配置表 (1): t_settings  -- 1 行配置, 无"删"概念
--   - join 表 (6): t_cron_host / t_cron_group / t_auth_host_user /
--                  t_auth_host_user_group / t_auth_host_host_group /
--                  t_auth_host_sys_user  -- FK CASCADE 自动清理
--
-- 设计:
--   - TINYINT(1) NOT NULL DEFAULT 0 (MySQL BOOLEAN 映射, 0=正常 1=软删)
--   - 每个表加 idx_xxx_is_deleted 索引 (业务查询 is_deleted=False 频繁)
--   - 幂等模式: IF NOT EXISTS 检查, 重复执行安全
--
-- 执行: mysql -u root -p orange < rev47_m6_soft_delete.sql
-- 验证:
--   SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS
--     WHERE TABLE_SCHEMA='orange' AND COLUMN_NAME='is_deleted';
--   -- 期望 7 行 (t_host/t_sys_user/t_acc_user/t_group/t_acc_group/t_auth_host/t_cron)
-- =============================================================================

-- 1) t_host
SET @col_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='t_host'
                      AND COLUMN_NAME='is_deleted');
SET @sql = IF(@col_exists = 0,
              'ALTER TABLE t_host ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0, ADD INDEX idx_t_host_is_deleted (is_deleted)',
              'SELECT "t_host.is_deleted already exists" AS info');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 2) t_sys_user
SET @col_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='t_sys_user'
                      AND COLUMN_NAME='is_deleted');
SET @sql = IF(@col_exists = 0,
              'ALTER TABLE t_sys_user ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0, ADD INDEX idx_t_sys_user_is_deleted (is_deleted)',
              'SELECT "t_sys_user.is_deleted already exists" AS info');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 3) t_acc_user
SET @col_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='t_acc_user'
                      AND COLUMN_NAME='is_deleted');
SET @sql = IF(@col_exists = 0,
              'ALTER TABLE t_acc_user ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0, ADD INDEX idx_t_acc_user_is_deleted (is_deleted)',
              'SELECT "t_acc_user.is_deleted already exists" AS info');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 4) t_group
SET @col_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='t_group'
                      AND COLUMN_NAME='is_deleted');
SET @sql = IF(@col_exists = 0,
              'ALTER TABLE t_group ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0, ADD INDEX idx_t_group_is_deleted (is_deleted)',
              'SELECT "t_group.is_deleted already exists" AS info');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 5) t_acc_group
SET @col_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='t_acc_group'
                      AND COLUMN_NAME='is_deleted');
SET @sql = IF(@col_exists = 0,
              'ALTER TABLE t_acc_group ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0, ADD INDEX idx_t_acc_group_is_deleted (is_deleted)',
              'SELECT "t_acc_group.is_deleted already exists" AS info');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 6) t_auth_host
SET @col_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='t_auth_host'
                      AND COLUMN_NAME='is_deleted');
SET @sql = IF(@col_exists = 0,
              'ALTER TABLE t_auth_host ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0, ADD INDEX idx_t_auth_host_is_deleted (is_deleted)',
              'SELECT "t_auth_host.is_deleted already exists" AS info');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 7) t_cron
SET @col_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='t_cron'
                      AND COLUMN_NAME='is_deleted');
SET @sql = IF(@col_exists = 0,
              'ALTER TABLE t_cron ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0, ADD INDEX idx_t_cron_is_deleted (is_deleted)',
              'SELECT "t_cron.is_deleted already exists" AS info');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

