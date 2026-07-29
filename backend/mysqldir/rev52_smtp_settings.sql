-- =============================================================================
-- REV52: UI-managed SMTP configuration
-- =============================================================================
-- SMTP authorization codes are stored only as Fernet ciphertext.
-- Every ALTER is idempotent so operators may safely rerun this migration.

SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 't_settings'
      AND COLUMN_NAME = 'mail_smtp_host'
);
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE `t_settings` ADD COLUMN `mail_smtp_host` VARCHAR(253) NULL',
    'SELECT "mail_smtp_host exists" AS info');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 't_settings'
      AND COLUMN_NAME = 'mail_smtp_port'
);
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE `t_settings` ADD COLUMN `mail_smtp_port` INT NULL',
    'SELECT "mail_smtp_port exists" AS info');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 't_settings'
      AND COLUMN_NAME = 'mail_smtp_security'
);
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE `t_settings` ADD COLUMN `mail_smtp_security` VARCHAR(10) NULL',
    'SELECT "mail_smtp_security exists" AS info');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 't_settings'
      AND COLUMN_NAME = 'mail_from'
);
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE `t_settings` ADD COLUMN `mail_from` VARCHAR(254) NULL',
    'SELECT "mail_from exists" AS info');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 't_settings'
      AND COLUMN_NAME = 'mail_password_encrypted'
);
SET @sql := IF(@col_exists = 0,
    'ALTER TABLE `t_settings` ADD COLUMN `mail_password_encrypted` TEXT NULL',
    'SELECT "mail_password_encrypted exists" AS info');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
