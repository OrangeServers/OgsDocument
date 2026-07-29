-- REV48-H1: group rename support after authorization junction-table migration.
-- Existing installations must replace the three group-name foreign keys so
-- edits made in the UI cascade to hosts and authorization relations.

ALTER TABLE `t_auth_host_user_group`
  DROP FOREIGN KEY `fk_ahug_group_name`;
ALTER TABLE `t_auth_host_user_group`
  ADD CONSTRAINT `fk_ahug_group_name`
    FOREIGN KEY (`group_name`) REFERENCES `t_acc_group` (`name`)
    ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE `t_auth_host_host_group`
  DROP FOREIGN KEY `fk_ahhg_group_name`;
ALTER TABLE `t_auth_host_host_group`
  ADD CONSTRAINT `fk_ahhg_group_name`
    FOREIGN KEY (`group_name`) REFERENCES `t_group` (`name`)
    ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE `t_host`
  DROP FOREIGN KEY `fk_host_group`;
ALTER TABLE `t_host`
  ADD CONSTRAINT `fk_host_group`
    FOREIGN KEY (`group`) REFERENCES `t_group` (`name`)
    ON DELETE SET NULL ON UPDATE CASCADE;
