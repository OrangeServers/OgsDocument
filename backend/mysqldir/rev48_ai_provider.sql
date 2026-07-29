-- =============================================================================
-- REV48: AI Provider 配置表
-- =============================================================================
-- 幂等迁移:
--   1) CREATE TABLE IF NOT EXISTS 可安全重复执行
--   2) INSERT IGNORE 以 provider_code 唯一键去重，不覆盖管理员已有配置

CREATE TABLE IF NOT EXISTS `t_ai_provider` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `provider_code` varchar(32) NOT NULL,
  `base_url` varchar(255) NOT NULL,
  `model` varchar(128) NOT NULL DEFAULT '',
  `api_key_ciphertext` varchar(1024) DEFAULT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '0',
  `is_default` tinyint(1) NOT NULL DEFAULT '0',
  `extra_body_json` text,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_t_ai_provider_code` (`provider_code`),
  KEY `idx_t_ai_provider_code` (`provider_code`),
  KEY `idx_t_ai_provider_enabled` (`enabled`),
  KEY `idx_t_ai_provider_is_default` (`is_default`),
  KEY `idx_t_ai_provider_created_at` (`created_at`),
  KEY `idx_t_ai_provider_updated_at` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO `t_ai_provider`
  (`provider_code`, `base_url`, `model`, `enabled`, `is_default`)
VALUES
  ('openai', 'https://api.openai.com/v1', '', 0, 0),
  ('deepseek', 'https://api.deepseek.com', '', 0, 0),
  ('minimax', 'https://api.minimaxi.com/v1', '', 0, 0),
  ('kimi', 'https://api.moonshot.cn/v1', '', 0, 0),
  ('qwen', 'https://dashscope.aliyuncs.com/compatible-mode/v1', '', 0, 0),
  ('glm', 'https://open.bigmodel.cn/api/paas/v4/', '', 0, 0),
  ('siliconflow', 'https://api.siliconflow.cn/v1', '', 0, 0);
