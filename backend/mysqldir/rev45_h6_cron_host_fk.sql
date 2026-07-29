-- REV45-H6: t_cron_host.host_alias 长度统一 + FK
--   背景:
--     - t_cron_host.host_alias = String(100), t_host.alias = String(25)
--     - 关联表字段 > 主表 PK, 无 FK, 删主机时 t_cron_host 行不级联清理
--   修复:
--     - 长度 100 -> 25 (与 t_host.alias 一致)
--     - 加 FK -> t_host.alias ondelete=CASCADE (删主机同步清关联表)
--   适用场景: 已部署的 orange.sql 若字段长度不符, 执行本脚本
--   幂等: FK constraint 重复会报 1826 错 (本脚本用 IF EXISTS 防御)
--   备份: 执行前请先 mysqldump 备份
--   验证: SHOW CREATE TABLE t_cron_host\G 应见 FK 和新长度
--
-- 注意:
--   1. 字段长度变窄 (100 -> 25) 时, 已存在超长 host_alias 数据会让 MODIFY 失败.
--      检查: SELECT MAX(CHAR_LENGTH(host_alias)) FROM t_cron_host;
--            实际生产环境中主机别名都不会超过 25 字符, 但需人工确认.
--   2. 加 FK 时若有孤儿数据 (host_alias 不在 t_host.alias), ALTER 会失败.
--      检查: SELECT host_alias FROM t_cron_host WHERE host_alias NOT IN (SELECT alias FROM t_host);
--      清理孤儿后才能加 FK.

ALTER TABLE `t_cron_host`
  MODIFY `host_alias` VARCHAR(25) NOT NULL;

-- FK 加之前先 DROP 已存在的同名 FK (幂等)
SET @fk_exists = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
                  WHERE CONSTRAINT_SCHEMA = DATABASE()
                    AND TABLE_NAME = 't_cron_host'
                    AND CONSTRAINT_NAME = 'fk_cron_host_host_alias');
SET @sql = IF(@fk_exists > 0,
              'ALTER TABLE t_cron_host DROP FOREIGN KEY fk_cron_host_host_alias',
              'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

ALTER TABLE `t_cron_host`
  ADD CONSTRAINT `fk_cron_host_host_alias` FOREIGN KEY (`host_alias`) REFERENCES `t_host` (`alias`) ON DELETE CASCADE;