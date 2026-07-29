-- =============================================================================
-- REV45-H9 (R2-6): t_acc_user.password_version 显式版本号
-- =============================================================================
-- 问题: 密码存储只用 hash 形态推断算法版本 (base64 vs bcrypt), 无显式版本号:
--   - 无法审计: "多少账号还是旧 base64 格式? 多少账号是 bcrypt 但 rounds 偏低?"
--   - 升级到 scrypt/argon2 时无法平滑迁移
-- 修复:
--   - 加 password_version INT NOT NULL DEFAULT 2
--   - 已有账号全部填 1 (保守: 默认视为旧 base64, 登录时 verify_pwd 推断正确版本)
--   - 登录成功后, 业务层可用 needs_rehash() 检测并更新到 2
--
-- 版本号定义 (与 basesec.py 常量保持一致):
--   1 = PWD_VERSION_LEGACY_BASE64 (旧 base64)
--   2 = PWD_VERSION_BCRYPT_1 (bcrypt rounds ≥ 10)

-- 1) 加列 (若不存在)
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 't_acc_user'
      AND COLUMN_NAME = 'password_version'
);
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE `t_acc_user` ADD COLUMN `password_version` INT NOT NULL DEFAULT 2',
    'SELECT "password_version 列已存在, 跳过" AS info');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 2) 加索引 (用于统计和按版本查询)
SET @idx_exists := (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 't_acc_user'
      AND INDEX_NAME = 'idx_acc_user_password_version'
);
SET @sql := IF(@idx_exists = 0,
    'ALTER TABLE `t_acc_user` ADD INDEX `idx_acc_user_password_version` (`password_version`)',
    'SELECT "password_version 索引已存在, 跳过" AS info');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 3) 已有账号: 老 hash 的标记为 1 (旧 base64), 让 needs_rehash 自动升级
--    bcrypt 的不动 (默认 2 已对)
--    检测: 存储值以 $2a$/$2b$/$2y$ 开头 = bcrypt, 其余 = base64
-- 注意: 已用 DEFAULT 2, 这里只对 base64 行重置为 1
UPDATE `t_acc_user`
SET `password_version` = 1
WHERE `password_version` = 2
  AND `password` NOT REGEXP '^\\$2[aby]\\$';

-- 4) 验证
SELECT
    `password_version`,
    COUNT(*) AS user_count,
    CASE `password_version`
        WHEN 1 THEN 'LEGACY_BASE64 (旧 base64, 待升级)'
        WHEN 2 THEN 'BCRYPT_1 (当前 bcrypt)'
        ELSE CONCAT('未知版本: ', `password_version`)
    END AS version_desc
FROM `t_acc_user`
GROUP BY `password_version`
ORDER BY `password_version`;

-- 期望: 看到 1 (旧) 和 2 (新) 两行的统计
-- R2-6 ALTER 完成
