-- =============================================================================
-- REV45-H7 (R2-4): cron.job_owner 加 FK 约束
-- =============================================================================
-- 问题: t_cron.job_owner 是 VARCHAR(30), 无 FK 约束, 可写入任何字符串
--   (e.g. "'; DROP TABLE t_cron; --"), 历史 'system' 默认值也无关联
-- 修复: 加 FK -> t_acc_user.name ON DELETE SET DEFAULT
--   删除 acc_user 时, 他创建的 cron.job_owner 自动重置为 'system' (内置系统账号)
-- 迁移步骤 (逐条, 失败立即停):
--   1) 确保 t_acc_user 中存在 name='system' 行 (内置不可删除)
--   2) 现有 t_cron.job_owner='system' 的行保持 (FK 加后会指向 system 用户)
--   3) 若有 job_owner 指向已不存在的用户, 把它们重置为 'admin'
--   4) 给 t_cron.job_owner 加 FK 约束 + 索引

-- 1) 插入内置 system 用户 (若不存在)
--   password = base64('__________') 当作不可登录占位
--   usrole=member, mail=系统内部地址, 不会被前端看到
INSERT IGNORE INTO `t_acc_user`
  (`id`, `alias`, `name`, `group`, `password`, `usrole`, `mail`, `remarks`)
VALUES
  (99, 'system', 'system', 'admin',
   'J1FTX19fX19fX18=',
   'member',
   'system@orange.local',
   '[REV45-H7/R2-4] 内置系统账号, 作为 cron.job_owner FK 默认目标; 不可删除');

-- 2) 修复历史 dangling 引用:
--    把指向已不存在用户的 job_owner 重置为 'admin'
--    注意: 'system' 行保留 (因步骤 1 已加)
UPDATE `t_cron` c
SET `job_owner` = 'admin'
WHERE `job_owner` <> 'system'
  AND `job_owner` NOT IN (SELECT `name` FROM `t_acc_user`);

-- 3) 给 t_cron.job_owner 加索引 + FK 约束
--    若已有同名 FK / KEY, 加失败提示手动清理
SET @fk_exists := (
    SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 't_cron'
      AND CONSTRAINT_NAME = 'fk_cron_owner'
);
SET @sql := IF(@fk_exists = 0,
    'ALTER TABLE `t_cron` ADD CONSTRAINT `fk_cron_owner` FOREIGN KEY (`job_owner`) REFERENCES `t_acc_user` (`name`) ON DELETE SET DEFAULT',
    'SELECT "fk_cron_owner 已存在, 跳过" AS info');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 索引
SET @idx_exists := (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 't_cron'
      AND INDEX_NAME = 'fk_cron_owner'
);
SET @sql := IF(@idx_exists = 0,
    'ALTER TABLE `t_cron` ADD KEY `fk_cron_owner` (`job_owner`)',
    'SELECT "fk_cron_owner 索引已存在, 跳过" AS info');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 验证: FK 必须已加
SELECT IF(
    (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
     WHERE CONSTRAINT_SCHEMA = DATABASE()
       AND TABLE_NAME = 't_cron'
       AND CONSTRAINT_NAME = 'fk_cron_owner') = 1,
    'R2-4 ALTER 成功: fk_cron_owner 已生效',
    'R2-4 ALTER 失败'
) AS migration_status;
