-- REV45-H3/H4/H5: FK + 长度统一 (5 个表的 5 个字段)
--   背景:
--     H3: t_host.group 长度 20, t_group.name 长度 25, 无 FK, 删组时 host 不会察觉
--     H4: t_auth_host_user_group/group_name + t_auth_host_host_group/group_name
--         长度 100, 主表 PK 长度 25, 无 FK
--     H5: 关联表字段 > 主表 PK 字段, 攻击者可构造 100 字符写入但主表限制 24/25/30
--   修复:
--     - 长度统一为对应主表 PK 长度 (24/25/30)
--     - 加 FK 到主表 (t_group.name / t_acc_group.name / t_host.alias)
--     - ondelete:
--         t_host.group           -> SET NULL (删组时 host 保留, group 置空)
--         t_auth_host_*_group    -> CASCADE  (删组时关联表行同步清理)
--   适用场景: 已部署的 orange.sql 若字段长度不符, 执行本脚本
--   幂等: 不可重复执行 (FK constraint 重复会报 1826 错, MODIFY 已是幂等)
--   备份: 执行前请先 mysqldump 备份
--   验证: SHOW CREATE TABLE t_host\G / t_auth_host_user\G / 等 应见 FK 和新长度
--
-- 注意:
--   1. 字段长度变窄 (100 -> 24/25/30) 时, 已存在超长数据会让 MODIFY 失败.
--      检查: SELECT MAX(CHAR_LENGTH(user_name)) FROM t_auth_host_user;
--            SELECT MAX(CHAR_LENGTH(group_name)) FROM t_auth_host_user_group;
--            SELECT MAX(CHAR_LENGTH(group_name)) FROM t_auth_host_host_group;
--            SELECT MAX(CHAR_LENGTH(sys_user_alias)) FROM t_auth_host_sys_user;
--      实际生产环境中用户名/组名长度都不会超过 25 字符, 但需人工确认.
--   2. 加 FK 时若有孤儿数据, ALTER 会失败 (Cannot add foreign key constraint).
--      检查: SELECT group_name FROM t_auth_host_user_group WHERE group_name NOT IN (SELECT name FROM t_acc_group);
--            SELECT group_name FROM t_auth_host_host_group WHERE group_name NOT IN (SELECT name FROM t_group);
--      清理孤儿后才能加 FK.

-- ============================================================
-- H3: t_host.group 长度 20 -> 25 + FK -> t_group.name
-- ============================================================
ALTER TABLE `t_host`
  MODIFY `group` VARCHAR(25) DEFAULT NULL;

-- FK 加之前先 DROP 已存在的同名 FK (幂等)
SET @fk_exists = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
                  WHERE CONSTRAINT_SCHEMA = DATABASE()
                    AND TABLE_NAME = 't_host'
                    AND CONSTRAINT_NAME = 'fk_host_group');
SET @sql = IF(@fk_exists > 0,
              'ALTER TABLE t_host DROP FOREIGN KEY fk_host_group',
              'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

ALTER TABLE `t_host`
  ADD CONSTRAINT `fk_host_group` FOREIGN KEY (`group`) REFERENCES `t_group` (`name`) ON DELETE SET NULL;

-- ============================================================
-- H5: t_auth_host_user.user_name 长度 100 -> 24
-- ============================================================
ALTER TABLE `t_auth_host_user`
  MODIFY `user_name` VARCHAR(24) NOT NULL;

-- ============================================================
-- H4/H5: t_auth_host_user_group.group_name 长度 100 -> 25 + FK -> t_acc_group.name
-- ============================================================
ALTER TABLE `t_auth_host_user_group`
  MODIFY `group_name` VARCHAR(25) NOT NULL;

SET @fk_exists = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
                  WHERE CONSTRAINT_SCHEMA = DATABASE()
                    AND TABLE_NAME = 't_auth_host_user_group'
                    AND CONSTRAINT_NAME = 'fk_ahug_group_name');
SET @sql = IF(@fk_exists > 0,
              'ALTER TABLE t_auth_host_user_group DROP FOREIGN KEY fk_ahug_group_name',
              'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

ALTER TABLE `t_auth_host_user_group`
  ADD CONSTRAINT `fk_ahug_group_name` FOREIGN KEY (`group_name`) REFERENCES `t_acc_group` (`name`) ON DELETE CASCADE;

-- ============================================================
-- H4/H5: t_auth_host_host_group.group_name 长度 100 -> 25 + FK -> t_group.name
-- ============================================================
ALTER TABLE `t_auth_host_host_group`
  MODIFY `group_name` VARCHAR(25) NOT NULL;

SET @fk_exists = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
                  WHERE CONSTRAINT_SCHEMA = DATABASE()
                    AND TABLE_NAME = 't_auth_host_host_group'
                    AND CONSTRAINT_NAME = 'fk_ahhg_group_name');
SET @sql = IF(@fk_exists > 0,
              'ALTER TABLE t_auth_host_host_group DROP FOREIGN KEY fk_ahhg_group_name',
              'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

ALTER TABLE `t_auth_host_host_group`
  ADD CONSTRAINT `fk_ahhg_group_name` FOREIGN KEY (`group_name`) REFERENCES `t_group` (`name`) ON DELETE CASCADE;

-- ============================================================
-- H5: t_auth_host_sys_user.sys_user_alias 长度 100 -> 30
-- REV47-M5: 30 -> 24 (与 t_acc_user.alias 统一, 关联表 PK 严格一致)
-- ============================================================
ALTER TABLE `t_auth_host_sys_user`
  MODIFY `sys_user_alias` VARCHAR(24) NOT NULL;