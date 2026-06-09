-- VerdictBox database schema (MySQL 8.x)
-- Primary focus: normalized 3NF design with constraints, trigger, stored procedure, and view.

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP VIEW IF EXISTS PublicDisputeView;
DROP VIEW IF EXISTS DisputeSummaryView;
DROP VIEW IF EXISTS DisputeCommentView;
DROP VIEW IF EXISTS DisputeAppealView;
DROP VIEW IF EXISTS DisputeReportView;
DROP PROCEDURE IF EXISTS GetDisputeSummary;
DROP PROCEDURE IF EXISTS SaveAIResultTransaction;
DROP PROCEDURE IF EXISTS ListResolvedDisputes;
DROP PROCEDURE IF EXISTS GetLeaderboardSummary;
DROP PROCEDURE IF EXISTS GetModerationQueueSummary;
DROP TRIGGER IF EXISTS trg_airesults_after_insert;
DROP TRIGGER IF EXISTS trg_votes_after_insert;
DROP TRIGGER IF EXISTS trg_disputereports_after_insert;
DROP TRIGGER IF EXISTS trg_appeals_after_update;

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

SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE Users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('disputant', 'spectator', 'admin') NOT NULL DEFAULT 'spectator',
    reputation_score INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Disputes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    created_by INT NOT NULL,
    invited_user INT NULL,
    status ENUM('waiting', 'active', 'resolved', 'reported', 'flagged') NOT NULL DEFAULT 'waiting',
    is_public BOOLEAN NOT NULL DEFAULT TRUE,
    moderation_mode ENUM('public', 'private') NOT NULL DEFAULT 'public',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME NULL,
    moderator_note TEXT NULL,
    review_state VARCHAR(32) NULL,
    CONSTRAINT fk_disputes_creator FOREIGN KEY (created_by) REFERENCES Users(id) ON DELETE CASCADE,
    CONSTRAINT fk_disputes_invited FOREIGN KEY (invited_user) REFERENCES Users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Submissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dispute_id INT NOT NULL,
    user_id INT NOT NULL,
    argument_text TEXT NOT NULL,
    submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_dispute_user_submission (dispute_id, user_id),
    CONSTRAINT fk_submissions_dispute FOREIGN KEY (dispute_id) REFERENCES Disputes(id) ON DELETE CASCADE,
    CONSTRAINT fk_submissions_user FOREIGN KEY (user_id) REFERENCES Users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE AIResults (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dispute_id INT NOT NULL UNIQUE,
    toxicity_score_a DECIMAL(5,4) NOT NULL,
    toxicity_score_b DECIMAL(5,4) NOT NULL,
    sentiment_a VARCHAR(20) NOT NULL,
    sentiment_b VARCHAR(20) NOT NULL,
    sarcasm_score_a DECIMAL(5,4) NOT NULL,
    sarcasm_score_b DECIMAL(5,4) NOT NULL,
    winner_user_id INT NOT NULL,
    reasoning TEXT NOT NULL,
    confidence_score DECIMAL(5,4) NOT NULL,
    fallacies_a JSON NULL,
    fallacies_b JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_airesults_dispute FOREIGN KEY (dispute_id) REFERENCES Disputes(id) ON DELETE CASCADE,
    CONSTRAINT fk_airesults_winner FOREIGN KEY (winner_user_id) REFERENCES Users(id) ON DELETE CASCADE,
    CONSTRAINT chk_confidence CHECK (confidence_score >= 0 AND confidence_score <= 1),
    CONSTRAINT chk_toxicity_a CHECK (toxicity_score_a >= 0 AND toxicity_score_a <= 1),
    CONSTRAINT chk_toxicity_b CHECK (toxicity_score_b >= 0 AND toxicity_score_b <= 1),
    CONSTRAINT chk_sarcasm_a CHECK (sarcasm_score_a >= 0 AND sarcasm_score_a <= 1),
    CONSTRAINT chk_sarcasm_b CHECK (sarcasm_score_b >= 0 AND sarcasm_score_b <= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Votes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dispute_id INT NOT NULL,
    voter_user_id INT NOT NULL,
    voted_for_user_id INT NOT NULL,
    voted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_vote_once (dispute_id, voter_user_id),
    CONSTRAINT fk_votes_dispute FOREIGN KEY (dispute_id) REFERENCES Disputes(id) ON DELETE CASCADE,
    CONSTRAINT fk_votes_voter FOREIGN KEY (voter_user_id) REFERENCES Users(id) ON DELETE CASCADE,
    CONSTRAINT fk_votes_voted_for FOREIGN KEY (voted_for_user_id) REFERENCES Users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Comments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dispute_id INT NOT NULL,
    user_id INT NOT NULL,
    body TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_comments_dispute FOREIGN KEY (dispute_id) REFERENCES Disputes(id) ON DELETE CASCADE,
    CONSTRAINT fk_comments_user FOREIGN KEY (user_id) REFERENCES Users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Appeals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dispute_id INT NOT NULL,
    appellant_user_id INT NOT NULL,
    reason_text TEXT NOT NULL,
    status ENUM('pending', 'approved', 'rejected') NOT NULL DEFAULT 'pending',
    admin_response TEXT NULL,
    submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME NULL,
    CONSTRAINT fk_appeals_dispute FOREIGN KEY (dispute_id) REFERENCES Disputes(id) ON DELETE CASCADE,
    CONSTRAINT fk_appeals_appellant FOREIGN KEY (appellant_user_id) REFERENCES Users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE DisputeReports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dispute_id INT NOT NULL,
    reporter_user_id INT NOT NULL,
    reason VARCHAR(64) NOT NULL,
    details TEXT NULL,
    is_system_flag BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed BOOLEAN NOT NULL DEFAULT FALSE,
    reviewed_at DATETIME NULL,
    reviewed_by_user_id INT NULL,
    UNIQUE KEY uq_dispute_report_once (dispute_id, reporter_user_id),
    CONSTRAINT fk_reports_dispute FOREIGN KEY (dispute_id) REFERENCES Disputes(id) ON DELETE CASCADE,
    CONSTRAINT fk_reports_reporter FOREIGN KEY (reporter_user_id) REFERENCES Users(id) ON DELETE CASCADE,
    CONSTRAINT fk_reports_reviewer FOREIGN KEY (reviewed_by_user_id) REFERENCES Users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Badges (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE UserBadges (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    badge_id INT NOT NULL,
    awarded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_user_badge (user_id, badge_id),
    CONSTRAINT fk_userbadges_user FOREIGN KEY (user_id) REFERENCES Users(id) ON DELETE CASCADE,
    CONSTRAINT fk_userbadges_badge FOREIGN KEY (badge_id) REFERENCES Badges(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE AdminLogs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dispute_id INT NULL,
    admin_user_id INT NULL,
    target_user_id INT NULL,
    action_type VARCHAR(50) NOT NULL,
    reason TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_adminlogs_dispute FOREIGN KEY (dispute_id) REFERENCES Disputes(id) ON DELETE SET NULL,
    CONSTRAINT fk_adminlogs_user FOREIGN KEY (admin_user_id) REFERENCES Users(id) ON DELETE SET NULL,
    CONSTRAINT fk_adminlogs_target_user FOREIGN KEY (target_user_id) REFERENCES Users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(120) NOT NULL,
    body TEXT NOT NULL,
    link_url VARCHAR(255) NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_notifications_user FOREIGN KEY (user_id) REFERENCES Users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DELIMITER $$

CREATE TRIGGER trg_force_privacy_mode
BEFORE INSERT ON Disputes
FOR EACH ROW
BEGIN
    IF NEW.moderation_mode = 'private' THEN
        SET NEW.is_public = 0;
        SET NEW.moderator_note = 'SYSTEM: Privacy enforced (Private Mode).';
    END IF;

    IF NEW.moderation_mode = 'public' THEN
        SET NEW.is_public = 1;
        SET NEW.moderator_note = 'SYSTEM: Visibility enforced (Public Mode).';
    END IF;
END$$

CREATE TRIGGER trg_airesults_after_insert
AFTER INSERT ON AIResults
FOR EACH ROW
BEGIN
    DECLARE winner_badge_id INT;
    DECLARE dispute_moderation_mode VARCHAR(32);

    UPDATE Disputes
    SET status = 'resolved',
        resolved_at = NOW()
    WHERE id = NEW.dispute_id;

    -- read the dispute's moderation mode so we can skip public-facing updates for private disputes
    SELECT moderation_mode INTO dispute_moderation_mode
    FROM Disputes
    WHERE id = NEW.dispute_id;

    -- Only award badges and reputation for PUBLIC disputes
    IF dispute_moderation_mode = 'public' THEN
        SELECT id INTO winner_badge_id
        FROM Badges
        WHERE name = 'First Victory'
        LIMIT 1;

        IF winner_badge_id IS NOT NULL THEN
            INSERT IGNORE INTO UserBadges (user_id, badge_id, awarded_at)
            VALUES (NEW.winner_user_id, winner_badge_id, NOW());
        END IF;

        UPDATE Users
        SET reputation_score = reputation_score + 10
        WHERE id = NEW.winner_user_id;
    END IF;
END$$

CREATE TRIGGER trg_votes_after_insert
AFTER INSERT ON Votes
FOR EACH ROW
BEGIN
    DECLARE dispute_moderation_mode VARCHAR(32);

    SELECT moderation_mode INTO dispute_moderation_mode
    FROM Disputes
    WHERE id = NEW.dispute_id;

    -- Only give reputation for votes on public disputes
    IF dispute_moderation_mode = 'public' THEN
        UPDATE Users
        SET reputation_score = reputation_score + 1
        WHERE id = NEW.voted_for_user_id;
    END IF;
END$$

CREATE TRIGGER trg_disputereports_after_insert
AFTER INSERT ON DisputeReports
FOR EACH ROW
BEGIN
    DECLARE report_count INT;
    DECLARE dispute_moderation_mode VARCHAR(32);

    -- Get the dispute's moderation mode
    SELECT moderation_mode INTO dispute_moderation_mode
    FROM Disputes
    WHERE id = NEW.dispute_id;

    -- Only auto-flag if it's a public dispute AND it's not a system flag
    -- Private disputes are never auto-flagged by reports
    IF dispute_moderation_mode = 'public' AND NEW.is_system_flag = FALSE THEN
        SELECT COUNT(*) INTO report_count
        FROM DisputeReports
        WHERE dispute_id = NEW.dispute_id
          AND is_system_flag = FALSE;

        UPDATE Disputes
        SET status = CASE
                WHEN report_count >= 3 THEN 'flagged'
                ELSE 'reported'
            END,
            review_state = CASE
                WHEN report_count >= 3 THEN 'escalated'
                ELSE 'reported'
            END
        WHERE id = NEW.dispute_id;
    END IF;

    -- Reward reporters only for PUBLIC disputes and non-system flags
    IF dispute_moderation_mode = 'public' AND NEW.is_system_flag = FALSE THEN
        UPDATE Users
        SET reputation_score = reputation_score + 1
        WHERE id = NEW.reporter_user_id;
    END IF;
END$$

CREATE TRIGGER trg_appeals_after_update
AFTER UPDATE ON Appeals
FOR EACH ROW
BEGIN
    IF NEW.status <> OLD.status THEN
        UPDATE Disputes
        SET status = CASE
                WHEN NEW.status = 'approved' THEN 'active'
                ELSE status
            END,
            review_state = CASE
                WHEN NEW.status = 'approved' THEN 'appeal_approved'
                WHEN NEW.status = 'rejected' THEN 'appeal_rejected'
                ELSE review_state
            END
        WHERE id = NEW.dispute_id;
    END IF;
END$$

CREATE PROCEDURE GetDisputeSummary(IN p_dispute_id INT)
BEGIN
    SELECT
        d.id AS dispute_id,
        d.title,
        d.status,
        ua.username AS user_a,
        sa.argument_text AS submission_a,
        ub.username AS user_b,
        sb.argument_text AS submission_b,
        ar.toxicity_score_a,
        ar.toxicity_score_b,
        ar.sentiment_a,
        ar.sentiment_b,
        ar.sarcasm_score_a,
        ar.sarcasm_score_b,
        winner.username AS winner_username,
        ar.reasoning,
        ar.confidence_score,
        COALESCE(votes_a.total_votes, 0) AS votes_for_a,
        COALESCE(votes_b.total_votes, 0) AS votes_for_b
    FROM Disputes d
    LEFT JOIN Submissions sa ON sa.dispute_id = d.id
        AND sa.id = (
            SELECT MIN(s1.id)
            FROM Submissions s1
            WHERE s1.dispute_id = d.id
        )
    LEFT JOIN Submissions sb ON sb.dispute_id = d.id
        AND sb.id = (
            SELECT MAX(s2.id)
            FROM Submissions s2
            WHERE s2.dispute_id = d.id
        )
    LEFT JOIN Users ua ON ua.id = sa.user_id
    LEFT JOIN Users ub ON ub.id = sb.user_id
    LEFT JOIN AIResults ar ON ar.dispute_id = d.id
    LEFT JOIN Users winner ON winner.id = ar.winner_user_id
    LEFT JOIN (
        SELECT v.dispute_id, v.voted_for_user_id, COUNT(*) AS total_votes
        FROM Votes v
        GROUP BY v.dispute_id, v.voted_for_user_id
    ) votes_a ON votes_a.dispute_id = d.id AND votes_a.voted_for_user_id = sa.user_id
    LEFT JOIN (
        SELECT v.dispute_id, v.voted_for_user_id, COUNT(*) AS total_votes
        FROM Votes v
        GROUP BY v.dispute_id, v.voted_for_user_id
    ) votes_b ON votes_b.dispute_id = d.id AND votes_b.voted_for_user_id = sb.user_id
    WHERE d.id = p_dispute_id;
END$$

CREATE PROCEDURE SaveAIResultTransaction(
    IN p_dispute_id INT,
    IN p_toxicity_score_a DECIMAL(5,4),
    IN p_toxicity_score_b DECIMAL(5,4),
    IN p_sentiment_a VARCHAR(20),
    IN p_sentiment_b VARCHAR(20),
    IN p_sarcasm_score_a DECIMAL(5,4),
    IN p_sarcasm_score_b DECIMAL(5,4),
    IN p_winner_user_id INT,
    IN p_reasoning TEXT,
    IN p_confidence_score DECIMAL(5,4),
    IN p_fallacies_a JSON,
    IN p_fallacies_b JSON
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    INSERT INTO AIResults (
        dispute_id,
        toxicity_score_a,
        toxicity_score_b,
        sentiment_a,
        sentiment_b,
        sarcasm_score_a,
        sarcasm_score_b,
        winner_user_id,
        reasoning,
        confidence_score,
        fallacies_a,
        fallacies_b
    ) VALUES (
        p_dispute_id,
        p_toxicity_score_a,
        p_toxicity_score_b,
        p_sentiment_a,
        p_sentiment_b,
        p_sarcasm_score_a,
        p_sarcasm_score_b,
        p_winner_user_id,
        p_reasoning,
        p_confidence_score,
        p_fallacies_a,
        p_fallacies_b
    );

    COMMIT;
END$$

CREATE PROCEDURE ListResolvedDisputes(IN p_limit INT, IN p_offset INT)
BEGIN
    SELECT
        d.id AS dispute_id,
        d.title,
        d.status,
        d.created_at,
        d.resolved_at,
        creator.username AS created_by_username,
        invited.username AS invited_username,
        winner.username AS winner_username,
        ar.confidence_score
    FROM Disputes d
    INNER JOIN AIResults ar ON ar.dispute_id = d.id
    INNER JOIN Users creator ON creator.id = d.created_by
    LEFT JOIN Users invited ON invited.id = d.invited_user
    INNER JOIN Users winner ON winner.id = ar.winner_user_id
    WHERE d.status = 'resolved'
    ORDER BY d.resolved_at DESC, d.id DESC
    LIMIT p_limit OFFSET p_offset;
END$$

CREATE PROCEDURE GetLeaderboardSummary(IN p_limit INT)
BEGIN
    SELECT
        u.id AS user_id,
        u.username,
        u.role,
        u.reputation_score,
        COUNT(DISTINCT CASE WHEN d2.id IS NOT NULL THEN ai.dispute_id END) AS victories,
        SUM(CASE WHEN dv.id IS NOT NULL THEN 1 ELSE 0 END) AS votes_cast,
        SUM(CASE WHEN da.id IS NOT NULL THEN 1 ELSE 0 END) AS appeals_filed,
        SUM(CASE WHEN dr.id IS NOT NULL THEN 1 ELSE 0 END) AS reports_filed
    FROM Users u
    LEFT JOIN AIResults ai ON ai.winner_user_id = u.id
    LEFT JOIN Disputes d2 ON d2.id = ai.dispute_id AND d2.moderation_mode = 'public'
    LEFT JOIN Votes v ON v.voter_user_id = u.id
    LEFT JOIN Disputes dv ON dv.id = v.dispute_id AND dv.moderation_mode = 'public'
    LEFT JOIN Appeals a ON a.appellant_user_id = u.id
    LEFT JOIN Disputes da ON da.id = a.dispute_id AND da.moderation_mode = 'public'
    LEFT JOIN DisputeReports r ON r.reporter_user_id = u.id
    LEFT JOIN Disputes dr ON dr.id = r.dispute_id AND dr.moderation_mode = 'public'
    WHERE u.is_active = TRUE
    GROUP BY u.id, u.username, u.role, u.reputation_score
    ORDER BY u.reputation_score DESC, victories DESC, votes_cast DESC, u.username ASC
    LIMIT p_limit;
END$$

CREATE PROCEDURE GetModerationQueueSummary()
BEGIN
    SELECT
        d.id AS dispute_id,
        d.title,
        d.status,
        d.review_state,
        d.created_at,
        COUNT(DISTINCT r.id) AS report_count,
        COUNT(DISTINCT a.id) AS appeal_count,
        MAX(r.created_at) AS latest_report_at,
        MAX(a.submitted_at) AS latest_appeal_at
    FROM Disputes d
    LEFT JOIN DisputeReports r ON r.dispute_id = d.id
    LEFT JOIN Appeals a ON a.dispute_id = d.id
     WHERE d.status IN ('reported', 'flagged')
         OR (d.review_state IS NOT NULL AND d.review_state <> 'cleared')
    GROUP BY d.id, d.title, d.status, d.review_state, d.created_at
    ORDER BY latest_report_at DESC, latest_appeal_at DESC, d.created_at DESC;
END$$

DELIMITER ;

CREATE VIEW PublicDisputeView AS
SELECT
    d.id AS dispute_id,
    d.title,
    creator.username AS created_by_username,
    invited.username AS invited_username,
    winner.username AS winner_username,
    ar.reasoning,
    ar.confidence_score,
    d.created_at,
    d.resolved_at
FROM Disputes d
INNER JOIN Users creator ON creator.id = d.created_by
LEFT JOIN Users invited ON invited.id = d.invited_user
INNER JOIN AIResults ar ON ar.dispute_id = d.id
INNER JOIN Users winner ON winner.id = ar.winner_user_id
WHERE d.status = 'resolved'
  AND d.is_public = TRUE;

CREATE VIEW DisputeSummaryView AS
SELECT
    d.id AS dispute_id,
    d.title,
    d.status,
    d.is_public,
    d.created_at,
    d.resolved_at,
    creator.username AS created_by_username,
    invited.username AS invited_username,
    winner.username AS winner_username,
    ar.confidence_score,
    ar.reasoning
FROM Disputes d
INNER JOIN Users creator ON creator.id = d.created_by
LEFT JOIN Users invited ON invited.id = d.invited_user
LEFT JOIN AIResults ar ON ar.dispute_id = d.id
LEFT JOIN Users winner ON winner.id = ar.winner_user_id;

CREATE VIEW DisputeCommentView AS
SELECT
    c.id AS comment_id,
    c.dispute_id,
    d.title AS dispute_title,
    c.user_id,
    u.username AS commenter_username,
    c.body,
    c.created_at
FROM Comments c
INNER JOIN Disputes d ON d.id = c.dispute_id
INNER JOIN Users u ON u.id = c.user_id;

CREATE VIEW DisputeAppealView AS
SELECT
    a.id AS appeal_id,
    a.dispute_id,
    d.title AS dispute_title,
    a.appellant_user_id,
    u.username AS appellant_username,
    a.reason_text,
    a.status,
    a.admin_response,
    a.submitted_at,
    a.reviewed_at
FROM Appeals a
INNER JOIN Disputes d ON d.id = a.dispute_id
INNER JOIN Users u ON u.id = a.appellant_user_id;

CREATE VIEW DisputeReportView AS
SELECT
    r.id AS report_id,
    r.dispute_id,
    d.title AS dispute_title,
    r.reporter_user_id,
    reporter.username AS reporter_username,
    r.reason,
    r.details,
    r.created_at,
    r.reviewed,
    r.reviewed_at,
    r.reviewed_by_user_id,
    reviewer.username AS reviewed_by_username
FROM DisputeReports r
INNER JOIN Disputes d ON d.id = r.dispute_id
INNER JOIN Users reporter ON reporter.id = r.reporter_user_id
LEFT JOIN Users reviewer ON reviewer.id = r.reviewed_by_user_id;
