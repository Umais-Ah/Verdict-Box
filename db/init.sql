-- VerdictBox Database Initialization
-- Simple import of all database modules

-- Drop cleanup (if restarting)
DROP VIEW IF EXISTS DisputeReportView;
DROP VIEW IF EXISTS DisputeAppealView;
DROP VIEW IF EXISTS DisputeCommentView;
DROP VIEW IF EXISTS DisputeSummaryView;
DROP VIEW IF EXISTS PublicDisputeView;
DROP PROCEDURE IF EXISTS GetModerationQueueSummary;
DROP PROCEDURE IF EXISTS GetLeaderboardSummary;
DROP PROCEDURE IF EXISTS ListResolvedDisputes;
DROP PROCEDURE IF EXISTS SaveAIResultTransaction;
DROP PROCEDURE IF EXISTS GetDisputeSummary;
DROP TRIGGER IF EXISTS trg_appeals_after_update;
DROP TRIGGER IF EXISTS trg_disputereports_after_insert;
DROP TRIGGER IF EXISTS trg_votes_after_insert;
DROP TRIGGER IF EXISTS trg_airesults_after_insert;
DROP TRIGGER IF EXISTS trg_force_privacy_mode;
DROP TABLE IF EXISTS AdminLogs;
DROP TABLE IF EXISTS Notifications;
DROP TABLE IF EXISTS UserBadges;
DROP TABLE IF EXISTS Badges;
DROP TABLE IF EXISTS Appeals;
DROP TABLE IF EXISTS Comments;
DROP TABLE IF EXISTS Votes;
DROP TABLE IF EXISTS AIResults;
DROP TABLE IF EXISTS Submissions;
DROP TABLE IF EXISTS Disputes;
DROP TABLE IF EXISTS Users;

SET FOREIGN_KEY_CHECKS = 0;

-- Import modules
SOURCE db/schema.sql;
SOURCE db/triggers.sql;
SOURCE db/procedures.sql;
SOURCE db/views.sql;
SOURCE db/seed.sql;

SET FOREIGN_KEY_CHECKS = 1;
