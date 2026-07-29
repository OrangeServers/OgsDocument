-- REV45-H1/H2: t_acc_user.name 加 UNIQUE 索引, 与 mail 字段一致
--   背景:
--     - REV41 H2: AccUserUpdate 改名时可改成已存在的 name (业务校验绕过即可)
--     - 根因: ORM/DB 都缺 unique 约束 (mail 有, name 无)
--     - 修复: ORM 加 unique=True + index=True, DB 同步 UNIQUE INDEX
--   适用场景: 已部署的 orange.sql 若 t_acc_user.name 无 UNIQUE 索引, 执行本脚本
--   幂等: 不可重复执行 (MySQL ALTER ADD UNIQUE INDEX 重复会报 1061 错)
--   备份: 执行前请先 mysqldump 备份
--   验证: SHOW CREATE TABLE t_acc_user\G 应见 UNIQUE KEY `uq_t_acc_user_name` (`name`)
--
-- 注意:
--   1. 如果 t_acc_user 当前数据已存在重复 name, ALTER 会失败 (Error 1062: Duplicate entry).
--      需先执行清理: SELECT name, COUNT(*) FROM t_acc_user GROUP BY name HAVING COUNT(*) > 1;
--      然后人工合并/删除重复账号后再执行本脚本.
--   2. 应用层 REV41-H2 业务校验 (AccUserUpdate.name 不与他人重复) 不变, 仍然是第一道防线.
--      本迁移是第二道防线 (DB 层), 即使业务校验被绕过也无法写入重复.

ALTER TABLE `t_acc_user`
  ADD UNIQUE INDEX `uq_t_acc_user_name` (`name`);