-- VerdictBox Database Triggers

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

    SELECT moderation_mode INTO dispute_moderation_mode
    FROM Disputes
    WHERE id = NEW.dispute_id;

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

    SELECT moderation_mode INTO dispute_moderation_mode
    FROM Disputes
    WHERE id = NEW.dispute_id;

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

DELIMITER ;
