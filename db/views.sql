-- VerdictBox Database Views

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
