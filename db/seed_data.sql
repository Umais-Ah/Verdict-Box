-- VerdictBox seed data for demo and viva.

INSERT INTO Users (username, email, password_hash, role, reputation_score, is_active)
VALUES
    ('admin', 'admin@verdictbox.edu', 'pbkdf2:sha256:600000$Ehgl3CcYxcw94WrM$9c768701c5ccb174e62002900fa4989c0486b90a4a795bbe22943929de83a40c', 'admin', 120, TRUE),
    ('alice', 'alice@verdictbox.edu', 'pbkdf2:sha256:600000$Ehgl3CcYxcw94WrM$9c768701c5ccb174e62002900fa4989c0486b90a4a795bbe22943929de83a40c', 'disputant', 35, TRUE),
    ('bob', 'bob@verdictbox.edu', 'pbkdf2:sha256:600000$Ehgl3CcYxcw94WrM$9c768701c5ccb174e62002900fa4989c0486b90a4a795bbe22943929de83a40c', 'disputant', 28, TRUE),
    ('sara', 'sara@verdictbox.edu', 'pbkdf2:sha256:600000$Ehgl3CcYxcw94WrM$9c768701c5ccb174e62002900fa4989c0486b90a4a795bbe22943929de83a40c', 'disputant', 22, TRUE),
    ('david', 'david@verdictbox.edu', 'pbkdf2:sha256:600000$Ehgl3CcYxcw94WrM$9c768701c5ccb174e62002900fa4989c0486b90a4a795bbe22943929de83a40c', 'disputant', 31, TRUE),
    ('maya', 'maya@verdictbox.edu', 'pbkdf2:sha256:600000$Ehgl3CcYxcw94WrM$9c768701c5ccb174e62002900fa4989c0486b90a4a795bbe22943929de83a40c', 'disputant', 26, TRUE),
    ('oscar', 'oscar@verdictbox.edu', 'pbkdf2:sha256:600000$Ehgl3CcYxcw94WrM$9c768701c5ccb174e62002900fa4989c0486b90a4a795bbe22943929de83a40c', 'disputant', 18, TRUE),
    ('nina', 'nina@verdictbox.edu', 'pbkdf2:sha256:600000$Ehgl3CcYxcw94WrM$9c768701c5ccb174e62002900fa4989c0486b90a4a795bbe22943929de83a40c', 'spectator', 8, TRUE);

INSERT INTO Badges (name, description)
VALUES
    ('First Victory', 'Win your first dispute.'),
    ('First Argument', 'Submit your first argument.'),
    ('Logic Master', 'Consistently strong reasoning with low fallacies.'),
    ('People Choice', 'Win with strong spectator support.');

INSERT INTO Disputes (title, description, created_by, invited_user, status, is_public, created_at, resolved_at)
VALUES
    ('Attendance policy enforcement', 'Should attendance be mandatory for core lectures?', 2, 3, 'resolved', TRUE, NOW() - INTERVAL 10 DAY, NOW() - INTERVAL 9 DAY),
    ('AI tools during exams', 'Are supervised AI tools acceptable in final exams?', 3, 6, 'resolved', FALSE, NOW() - INTERVAL 8 DAY, NOW() - INTERVAL 7 DAY),
    ('Group projects grading', 'Should group projects use individual contribution weighting?', 5, 2, 'resolved', TRUE, NOW() - INTERVAL 6 DAY, NOW() - INTERVAL 5 DAY),
    ('Late submission penalties', 'Are strict late penalties fair for all students?', 6, 4, 'active', TRUE, NOW() - INTERVAL 3 DAY, NULL),
    ('Open-book finals', 'Do open-book finals improve learning outcomes?', 2, 7, 'active', FALSE, NOW() - INTERVAL 2 DAY, NULL),
    ('Mandatory internships', 'Should internships be mandatory for graduation?', 3, 4, 'waiting', TRUE, NOW() - INTERVAL 1 DAY, NULL);

INSERT INTO Submissions (dispute_id, user_id, argument_text)
VALUES
    (1, 2, 'Mandatory attendance improves engagement and creates consistent learning routines for foundational courses.'),
    (1, 3, 'Flexibility matters; outcomes should be prioritized over seat-time requirements.'),
    (2, 3, 'AI access creates inequity and may reduce genuine assessment of student understanding.'),
    (2, 6, 'Supervised AI can be a learning aid when restrictions and transparency are enforced.'),
    (3, 5, 'Weighting individual effort improves fairness and accountability in group work.'),
    (3, 2, 'Over-weighting individual work can damage collaboration and team learning.'),
    (4, 6, 'Strict penalties maintain academic discipline and respect for deadlines.'),
    (4, 4, 'Context-based extensions avoid unfair punishment in genuine hardship cases.'),
    (5, 2, 'Open-book finals test applied reasoning rather than memorization.'),
    (5, 7, 'Open-book exams can reduce study effort and lower mastery of fundamentals.'),
    (6, 3, 'Internships build employability and practical skills that classroom work cannot replicate.'),
    (6, 4, 'Mandatory internships can exclude students with caregiving or financial constraints.');

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
)
VALUES
    (1, 0.0700, 0.1100, 'positive', 'neutral', 0.0900, 0.0700, 2,
     'Argument A grounded the policy in consistent learning behavior while acknowledging accountability.',
     0.8100,
     JSON_ARRAY(),
     JSON_ARRAY('False Dichotomy')),
    (2, 0.0600, 0.0800, 'neutral', 'positive', 0.0600, 0.0500, 6,
     'Argument B proposed clear safeguards and framed AI as a supervised support tool.',
     0.7600,
     JSON_ARRAY('Hasty Generalization'),
     JSON_ARRAY()),
    (3, 0.0500, 0.0700, 'positive', 'neutral', 0.0400, 0.0600, 5,
     'Argument A emphasized measurable contribution without undermining teamwork incentives.',
     0.7900,
     JSON_ARRAY(),
     JSON_ARRAY());

INSERT INTO Votes (dispute_id, voter_user_id, voted_for_user_id)
VALUES
    (1, 1, 2),
    (1, 8, 2),
    (1, 7, 3),
    (2, 1, 6),
    (2, 8, 6),
    (2, 7, 3),
    (3, 1, 5),
    (3, 8, 5),
    (3, 7, 2),
    (4, 1, 4),
    (5, 8, 2),
    (6, 7, 3);

INSERT INTO Comments (dispute_id, user_id, body, created_at)
VALUES
    (1, 8, 'Attendance helps with structure, but flexibility needs to exist.', NOW() - INTERVAL 9 DAY),
    (1, 1, 'Both sides should address accessibility accommodations.', NOW() - INTERVAL 9 DAY),
    (2, 8, 'Supervised tools could help, but rules must be clear.', NOW() - INTERVAL 7 DAY),
    (2, 1, 'Equity concerns need more concrete guardrails.', NOW() - INTERVAL 7 DAY),
    (3, 7, 'Contribution tracking is important in group assessments.', NOW() - INTERVAL 5 DAY),
    (3, 8, 'Collaboration skills should remain central.', NOW() - INTERVAL 5 DAY),
    (4, 2, 'Late policies should distinguish emergencies from negligence.', NOW() - INTERVAL 2 DAY),
    (4, 5, 'Consistency prevents perceived favoritism.', NOW() - INTERVAL 2 DAY),
    (5, 6, 'Open-book exams can still be rigorous with applied tasks.', NOW() - INTERVAL 1 DAY),
    (5, 4, 'Fundamentals still matter; open-book can reduce prep.', NOW() - INTERVAL 1 DAY),
    (6, 8, 'Internships should not be a barrier to graduation.', NOW() - INTERVAL 1 DAY),
    (6, 1, 'Industry experience adds value but needs flexibility.', NOW() - INTERVAL 1 DAY);

INSERT INTO UserBadges (user_id, badge_id, awarded_at)
VALUES
    (2, 1, NOW() - INTERVAL 9 DAY),
    (6, 1, NOW() - INTERVAL 7 DAY),
    (5, 1, NOW() - INTERVAL 5 DAY),
    (2, 2, NOW() - INTERVAL 9 DAY);

INSERT INTO Notifications (user_id, title, body, link_url, is_read, created_at)
VALUES
    (2, 'Dispute resolved', 'Your dispute on attendance policy has been resolved.', '/disputes/1', TRUE, NOW() - INTERVAL 9 DAY),
    (3, 'New dispute invite', 'You were invited to the AI tools during exams dispute.', '/disputes/2', TRUE, NOW() - INTERVAL 8 DAY),
    (6, 'Verdict ready', 'AI verdict is available for the AI tools dispute.', '/disputes/2', TRUE, NOW() - INTERVAL 7 DAY),
    (5, 'Dispute resolved', 'Group projects grading verdict is available.', '/disputes/3', TRUE, NOW() - INTERVAL 5 DAY),
    (4, 'New argument submitted', 'Your opponent submitted their argument.', '/disputes/4', FALSE, NOW() - INTERVAL 2 DAY),
    (7, 'New dispute invite', 'You were invited to open-book finals.', '/disputes/5', FALSE, NOW() - INTERVAL 2 DAY),
    (8, 'Voting open', 'You can now vote on active disputes.', '/dashboard', FALSE, NOW() - INTERVAL 2 DAY),
    (1, 'Moderation queue', 'One dispute requires admin review.', '/admin', FALSE, NOW() - INTERVAL 1 DAY),
    (2, 'Appeal update', 'No appeals have been filed for your dispute.', '/disputes/1', TRUE, NOW() - INTERVAL 1 DAY);
