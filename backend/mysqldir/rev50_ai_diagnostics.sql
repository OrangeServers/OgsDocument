-- REV50: durable, evidence-backed AI diagnostics.
-- Safe to re-run: all objects are created with IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS `t_ai_diagnostic_run` (
  `id` varchar(32) NOT NULL,
  `owner` varchar(24) NOT NULL,
  `conversation_id` varchar(32) DEFAULT NULL,
  `profile_id` varchar(64) NOT NULL,
  `profile_name` varchar(128) NOT NULL,
  `status` varchar(16) NOT NULL,
  `target_count` int NOT NULL DEFAULT 0,
  `success_count` int NOT NULL DEFAULT 0,
  `failed_count` int NOT NULL DEFAULT 0,
  `system_user_id` int NOT NULL,
  `system_user_alias` varchar(24) NOT NULL,
  `parameters_json` text NOT NULL,
  `summary_json` text NOT NULL,
  `asset_progress_json` text NOT NULL,
  `latest_event_seq` int NOT NULL DEFAULT 0,
  `cancel_requested` tinyint(1) NOT NULL DEFAULT 0,
  `started_at` datetime DEFAULT NULL,
  `completed_at` datetime DEFAULT NULL,
  `evidence_expires_at` datetime NOT NULL,
  `audit_expires_at` datetime NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ai_diag_run_owner` (`owner`),
  KEY `idx_ai_diag_run_conversation` (`conversation_id`),
  KEY `idx_ai_diag_run_profile` (`profile_id`),
  KEY `idx_ai_diag_run_status` (`status`),
  KEY `idx_ai_diag_run_system_user` (`system_user_id`),
  KEY `idx_ai_diag_run_evidence_expiry` (`evidence_expires_at`),
  KEY `idx_ai_diag_run_audit_expiry` (`audit_expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `t_ai_diagnostic_event` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `run_id` varchar(32) NOT NULL,
  `sequence` int NOT NULL,
  `event_type` varchar(32) NOT NULL,
  `payload_json` text NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ai_diagnostic_event_sequence` (`run_id`, `sequence`),
  KEY `idx_ai_diag_event_run` (`run_id`),
  CONSTRAINT `fk_ai_diag_event_run` FOREIGN KEY (`run_id`)
    REFERENCES `t_ai_diagnostic_run` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `t_ai_diagnostic_evidence` (
  `id` varchar(32) NOT NULL,
  `run_id` varchar(32) NOT NULL,
  `target_id` int DEFAULT NULL,
  `asset_alias` varchar(25) NOT NULL,
  `probe_id` varchar(64) NOT NULL,
  `title` varchar(128) NOT NULL,
  `kind` varchar(32) NOT NULL,
  `status` varchar(16) NOT NULL,
  `content_ciphertext` longtext NOT NULL,
  `error_ciphertext` longtext NOT NULL,
  `truncated` tinyint(1) NOT NULL DEFAULT 0,
  `collected_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `expires_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_ai_diag_evidence_run` (`run_id`),
  KEY `idx_ai_diag_evidence_expiry` (`expires_at`),
  CONSTRAINT `fk_ai_diag_evidence_run` FOREIGN KEY (`run_id`)
    REFERENCES `t_ai_diagnostic_run` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `t_ai_diagnostic_report` (
  `run_id` varchar(32) NOT NULL,
  `status` varchar(16) NOT NULL,
  `severity` varchar(16) NOT NULL,
  `summary` text NOT NULL,
  `findings_json` text NOT NULL,
  `evidence_insufficient` tinyint(1) NOT NULL DEFAULT 0,
  `generated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `expires_at` datetime NOT NULL,
  PRIMARY KEY (`run_id`),
  KEY `idx_ai_diag_report_expiry` (`expires_at`),
  CONSTRAINT `fk_ai_diag_report_run` FOREIGN KEY (`run_id`)
    REFERENCES `t_ai_diagnostic_run` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 兼容已提前试跑过旧版 REV50 的测试环境：补齐审计过期字段。
SET @audit_col_exists := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 't_ai_diagnostic_run'
    AND COLUMN_NAME = 'audit_expires_at'
);
SET @sql := IF(
  @audit_col_exists = 0,
  'ALTER TABLE `t_ai_diagnostic_run` ADD COLUMN `audit_expires_at` DATETIME NULL',
  'SELECT "audit_expires_at 列已存在, 跳过" AS info'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 兼容旧版 REV50：诊断凭据改用不可变 ID，alias 仅保留为审计快照。
SET @system_user_id_col_exists := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 't_ai_diagnostic_run'
    AND COLUMN_NAME = 'system_user_id'
);
SET @sql := IF(
  @system_user_id_col_exists = 0,
  'ALTER TABLE `t_ai_diagnostic_run` ADD COLUMN `system_user_id` INT NULL AFTER `failed_count`',
  'SELECT "system_user_id 列已存在, 跳过" AS info'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `t_ai_diagnostic_run` AS run
JOIN (
  SELECT `alias`, MIN(`id`) AS `id`
  FROM `t_sys_user`
  GROUP BY `alias`
) AS credential ON credential.`alias` = run.`system_user_alias`
SET run.`system_user_id` = credential.`id`
WHERE run.`system_user_id` IS NULL;

ALTER TABLE `t_ai_diagnostic_run`
  MODIFY COLUMN `system_user_id` INT NOT NULL;

SET @system_user_id_index_exists := (
  SELECT COUNT(*) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 't_ai_diagnostic_run'
    AND INDEX_NAME = 'idx_ai_diag_run_system_user'
);
SET @sql := IF(
  @system_user_id_index_exists = 0,
  'ALTER TABLE `t_ai_diagnostic_run` ADD INDEX `idx_ai_diag_run_system_user` (`system_user_id`)',
  'SELECT "idx_ai_diag_run_system_user 索引已存在, 跳过" AS info'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `t_ai_diagnostic_run`
SET `audit_expires_at` = DATE_ADD(
  COALESCE(`completed_at`, `created_at`), INTERVAL 90 DAY
)
WHERE `audit_expires_at` IS NULL;

ALTER TABLE `t_ai_diagnostic_run`
  MODIFY COLUMN `audit_expires_at` DATETIME NOT NULL;

SET @audit_index_exists := (
  SELECT COUNT(*) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 't_ai_diagnostic_run'
    AND INDEX_NAME = 'idx_ai_diag_run_audit_expiry'
);
SET @sql := IF(
  @audit_index_exists = 0,
  'ALTER TABLE `t_ai_diagnostic_run` ADD INDEX `idx_ai_diag_run_audit_expiry` (`audit_expires_at`)',
  'SELECT "idx_ai_diag_run_audit_expiry 索引已存在, 跳过" AS info'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
