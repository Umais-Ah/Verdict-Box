-- VerdictBox Database Stored Procedures

DELIMITER $$

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
