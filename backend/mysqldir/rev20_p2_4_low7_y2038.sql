-- =============================================================================
-- REV20-P2-4-LOW-7: 解决 Y2038 问题
--   t_login_log / t_command_log / t_cz_log 的 log_time 字段
--   MySQL TIMESTAMP 类型使用 32-bit Unix timestamp, 范围 1970-01-01 ~ 2038-01-19 03:14:07 UTC
--   超过 2038 写入会失败或溢出
--   修复: 改为 DATETIME (8 字节, 范围 1000-01-01 ~ 9999-12-31)

-- 适用场景: 已部署的 orange.sql 若用 MySQL TIMESTAMP, 执行本脚本迁移
-- 幂等: 可重复执行 (MODIFY COLUMN 操作)
-- 备份: 执行前请先 mysqldump 备份
-- 验证: 迁移后 SHOW CREATE TABLE t_login_log\G 应显示 log_time datetime NOT NULL

-- 注意: 如果 t_login_log 当前数据中 log_time 已超过 2038-01-19 03:14:07 UTC
--   (即 epoch > 2147483647), 需要先转为 NULL 再 MODIFY
--   实际生产环境 2026 不会遇到, 仅作防御

ALTER TABLE `t_login_log`   MODIFY `log_time` DATETIME NOT NULL;
ALTER TABLE `t_command_log` MODIFY `log_time` DATETIME NOT NULL;
ALTER TABLE `t_cz_log`      MODIFY `log_time` DATETIME NOT NULL;
