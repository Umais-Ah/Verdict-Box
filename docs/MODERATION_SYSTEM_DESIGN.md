# VerdictBox Tiered Moderation System Design

## Overview

VerdictBox implements a **two-tier moderation architecture** that treats public and private disputes as fundamentally different environments:

- **Public Disputes**: Full community engagement with standard moderation (votes, comments, reports, appeals)
- **Private Disputes**: Controlled, invite-only environments with centralized, stricter moderation rules

This design balances community safety with the integrity of private interactions.

---

## System Architecture

### Database Schema Extensions

#### `Disputes` Table

Added fields to support tiered moderation:

- `moderation_mode` (ENUM: 'public' | 'private'): Determines which moderation rules apply
- `toxicity_flag` (BOOLEAN): Marks disputes with AI-detected toxicity issues
- `flagged_by_system` (BOOLEAN): Indicates admin/system-level flags (not participant reports)
- `system_flag_reason` (VARCHAR): Reason for system-level flagging (e.g., "High toxicity detected")

#### `DisputeReports` Table

Added field:

- `is_system_flag` (BOOLEAN): Distinguishes between participant reports and admin system flags
  - `FALSE` = Community report (public disputes only)
  - `TRUE` = Admin/system flag (can be used on any dispute)

### Models

Added validation methods to the `Dispute` model:

```python
def is_private(self) -> bool
    """Check if dispute is in private mode."""

def is_participant(self, user_id: int) -> bool
    """Check if a user is a participant in this dispute."""

def can_report(self, user_id: int) -> bool
    """Determines if a user can file a report."""

def can_appeal(self, user_id: int) -> bool
    """Determines if a user can appeal."""
```

---

## Moderation Rules by Dispute Type

### PUBLIC DISPUTES

**Visibility**: Open to all authenticated users

#### Engagement Features

| Feature                 | Status     | Rules                                       |
| ----------------------- | ---------- | ------------------------------------------- |
| **Voting**              | ✅ Enabled | Spectators vote after resolution            |
| **Comments**            | ✅ Enabled | Any authenticated user can comment          |
| **Participant Reports** | ✅ Enabled | Community can report for violations         |
| **Appeals**             | ✅ Enabled | Losing participant can appeal after verdict |

#### Reporting Mechanism

- **Who can report**: Any spectator (non-participants)
- **Escalation**: Auto-escalates to `flagged` status after 3 reports
- **Moderation**: Admin reviews and decides: clear, investigate, hide, or restrict user
- **Outcome**: Can affect reputation scores, user restrictions, dispute visibility

#### Appeal Mechanism

- **Who can appeal**: Losing participant only
- **Timing**: After verdict is finalized
- **Admin action**: Can approve (reruns ML) or reject
- **Outcome**: If approved, dispute returns to active status for re-analysis

---

### PRIVATE DISPUTES

**Visibility**: Invite-only environment between two specific participants

#### Engagement Features

| Feature                 | Status               | Rules                                |
| ----------------------- | -------------------- | ------------------------------------ |
| **Voting**              | ❌ Disabled          | Only participants see discussion     |
| **Comments**            | ⚠️ Participants only | Limited to the two participants      |
| **Participant Reports** | ❌ Blocked           | Reporting maintains dispute privacy  |
| **Appeals**             | ✅ Enabled           | Participants can appeal for fairness |

#### Moderation Mechanism: System Flags Only

Private disputes use **centralized, admin-initiated system flags** instead of community reports:

1. **System Flag Creation** (Admin-only)
   - Triggered by: AI toxicity detection, manual admin review, automated scanners
   - Reason examples: "High toxicity detected (>0.75)", "Profanity violation", "Internal review"
   - Direct action: No escalation threshold; single flag immediately marks dispute for review

2. **Flag Processing** (Admin dashboard)
   - Access: Admin-only private dispute queue
   - Information provided:
     - System flag reason and toxicity scores
     - Participant information
     - Dispute content summary
   - Action options: clear, investigate, restrict participant, terminate

3. **Outcomes**
   - **Clear**: Dismiss flag, restore dispute to active/resolved state
   - **Investigate**: Keep under review without immediate action
   - **Restrict**: Deactivate participant account for violations
   - **Terminate**: Hide dispute, end private session

#### Appeal Mechanism for Private Disputes

- **Who can appeal**: Any participant (winner or loser)
- **Condition**: Only after a verdict is finalized
- **Admin decision**: Approve or reject
- **Effect**: If approved, dispute re-analysis only (no community re-voting)
- **Scope**: Limited to the two participants and admin

---

## Implementation Details

### Routing & Endpoints

#### Disputes Routes (`routes/disputes.py`)

**POST `/dispute/<int:dispute_id>/report`**

```python
# Report functionality updated
if dispute.is_private():
    return error("Reports are not allowed for private disputes")
# Only public disputes can be reported
```

**POST `/dispute/<int:dispute_id>/appeal`**

```python
# Appeal validation enhanced
if not dispute.is_participant(user_id):
    return error("Only participants can appeal")
# Appeals allowed on both public and private disputes
```

#### Voting Routes (`routes/voting.py`)

**POST `/dispute/<int:dispute_id>/vote`**

```python
# Vote validation added
if dispute.is_private():
    return error("Voting is not allowed for private disputes")
# Only public disputes allow spectator voting
```

#### Admin Routes (`routes/admin.py`)

**POST `/admin/dispute/<int:dispute_id>/flag-system`**

- Creates a system-level flag for any dispute (typically private)
- Requires: admin role, reason, optional toxicity_score
- Effect: Marks dispute as `flagged` and `flagged_by_system=true`
- Returns: 201 Created on success

**GET `/admin/private-disputes`**

- Lists all private disputes with system flag status
- Includes: count of flags, toxicity indicators, creation timestamp
- Returns: JSON array of private dispute summaries

**POST `/admin/dispute/<int:dispute_id>/private-moderation`**

- Private dispute specific moderation endpoint
- Decisions: `clear`, `investigate`, `restrict`, `terminate`
- Restrict: Can target specific participant for deactivation
- Returns: 200 OK on success

### Database Triggers

**`trg_disputereports_after_insert`** (Modified)

```sql
-- Only auto-escalates if:
-- 1. Dispute is in PUBLIC moderation mode
-- 2. Report is NOT a system flag (is_system_flag = FALSE)
-- If both conditions true and report count >= 3, mark as 'flagged'
```

---

## User Experience Flow

### Public Dispute Participant

1. Creates or joins public debate
2. Submits argument
3. Awaits verdict
4. Receives reputation for participation
5. **Can appeal** if lost (participants only)
6. **Can be reported** by spectators for violations
7. Votes still visible in public leaderboard

### Private Dispute Participant

1. Creates private debate with one specific opponent
2. Submits argument in controlled environment
3. Awaits verdict with no external voting
4. Comments only between participants
5. **Cannot be reported** by participants (protected privacy)
6. **Can appeal** for fairness if verdict seems unfair
7. No reputation impact from community voting (only verdict winner gets points)
8. Protected from public escalation mechanisms

### Admin (Moderation)

#### Public Disputes

- Reviews reports in escalation queue
- Makes decisions on community-flagged content
- Can restrict users for violations
- Handles appeals with option to re-run analysis

#### Private Disputes

- Proactively flags disputes with system rules (toxicity, profanity, etc.)
- Reviews system flags without participant involvement
- Can restrict participants for private dispute violations
- Can terminate sessions if needed
- Ensures private sessions remain safe and contained

---

## Trigger Behavior

### Report Escalation (Public Disputes Only)

```
Report 1 created on public dispute
  → Status: "reported"

Report 2 created on public dispute
  → Status: "reported"

Report 3 created on public dispute
  → Status: "flagged"
  → review_state: "escalated"
  → Admin queue populated
```

### System Flag on Private Dispute

```
System flag created on private dispute
  → Status: "flagged"
  → flagged_by_system: true
  → Immediate admin review (no threshold)
  → Participant reports cannot be filed
```

---

## Security & Privacy Considerations

### Private Dispute Isolation

- No spectators or external votes
- Reports blocked at application level
- Database constraints prevent accidental exposure
- Admin flags maintain participant anonymity until action taken

### Report Integrity

- System flags separate from participant reports
- Triggers distinguish between escalation types
- Audit trail via AdminLogs for all moderation actions
- Reputation only earned for participation, not for system management

### Appeal Fairness

- Participants can appeal regardless of dispute type
- Appeals only available post-verdict (prevents pre-emptive blocking)
- Admin response documented and notified
- Appeal approvals trigger re-analysis with context

---

## Configuration & Migration

### Database Migration Steps

1. Add new columns to `Disputes` table
2. Add `is_system_flag` to `DisputeReports` table
3. Update `trg_disputereports_after_insert` trigger
4. Set default `moderation_mode = 'public'` for all existing disputes
5. Update models.py with new fields and methods
6. Deploy updated routes

### Feature Flags

- All public disputes default to `moderation_mode = 'public'`
- Admins can set `moderation_mode = 'private'` on creation
- Invited-only disputes automatically restricted
- System flags can be created immediately upon deployment

---

## Monitoring & Metrics

### Admin Dashboard Enhancements

- **Public disputes tab**: Community reports, escalations, appeals
- **Private disputes tab**: System flags, AI toxicity scores, participant restrictions
- **Reports by type**: Distinguish participant vs. system flags
- **Appeal approval rate**: Track admin decisions on appeals

### Logging

```sql
AdminLogs tracked for:
- dispute_reported (public)
- system_flag_created (private)
- dispute_cleared, dispute_hidden, dispute_restricted
- appeal_approved, appeal_rejected
- private_dispute_cleared, private_dispute_terminated
```

---

## API Contract Changes

### Request/Response Examples

#### Create System Flag (Private Dispute)

```json
POST /admin/dispute/42/flag-system
{
  "reason": "High toxicity detected",
  "toxicity_score": 0.82
}

Response (201):
{
  "message": "System flag created successfully"
}
```

#### List Private Disputes

```json
GET /admin/private-disputes

Response (200):
[
  {
    "id": 42,
    "title": "Privacy Debate",
    "created_by": "user_a",
    "status": "flagged",
    "flagged_by_system": true,
    "system_flag_reason": "High toxicity detected",
    "toxicity_flag": true,
    "system_flags_count": 1,
    "created_at": "2026-05-01T12:00:00"
  }
]
```

#### Report on Private Dispute (Blocked)

```json
POST /dispute/42/report
{
  "reason": "abuse"
}

Response (403):
{
  "error": "Reports are not allowed for private disputes. Contact admin for moderation concerns."
}
```

#### Vote on Private Dispute (Blocked)

```json
POST /dispute/42/vote
{
  "voted_for_user_id": 100
}

Response (403):
{
  "error": "Voting is not allowed for private disputes"
}
```

#### Appeal (Both Public & Private Allowed)

```json
POST /dispute/42/appeal
{
  "reason_text": "I believe the verdict was unfair..."
}

Response (201):
{
  "message": "Appeal submitted",
  "unlocked_badges": []
}
```

---

## Testing Checklist

### Unit Tests

- [ ] `Dispute.is_private()` returns correct moderation mode
- [ ] `Dispute.is_participant(user_id)` validates submission records
- [ ] `Dispute.can_report(user_id)` blocks private disputes
- [ ] `Dispute.can_appeal(user_id)` requires participant + resolved status

### Integration Tests

- [ ] Report endpoint rejects private disputes (403)
- [ ] Vote endpoint rejects private disputes (403)
- [ ] Appeal endpoint accepts both public and private (if participant)
- [ ] System flag creates `is_system_flag=true` record
- [ ] Trigger doesn't escalate private dispute reports

### Scenario Tests

1. **Public Dispute Flow**: Report → Escalate → Admin Action → Clear
2. **Private Dispute Flow**: System Flag → Admin Review → Restrict/Terminate
3. **Appeal on Public**: Appeal → Admin Approve → Re-analysis → New Verdict
4. **Appeal on Private**: Appeal → Admin Approve → Re-analysis → Only participants see
5. **Mixed Actions**: User reports public dispute, creates private with another user

---

## Future Enhancements

- **Tiered Privacy Levels**: Beyond binary public/private (e.g., "invite-10-friends")
- **Custom Moderation Policies**: Disputes governed by different rule sets
- **Participant Visibility Settings**: Control who sees appeal process
- **Automated Toxicity Scanning**: ML-driven system flags for all disputes
- **Moderation Workflows**: Multi-admin review for complex cases
- **Appeal Quorum**: Multiple admins approve appeals for high-stakes disputes

---

## PRIVATE DISPUTE IMPACT RULE (FINAL DEFINITION)

Private disputes do NOT affect any public-facing metrics or achievements. Enforce these rules server-side and reflect them in UI/analytics filters:

1. Leaderboard

- No change in ranking
- No win/loss points added
- Not counted in top users

2. Reputation Score

- `Users.reputation_score` is NOT updated from private disputes
- No +10 / -10 logic from private disputes
- No badges awarded from private disputes

3. Win / Loss Stats

- Private disputes are NOT included in win count, loss count, or win rate %
- Only PUBLIC disputes affect these statistics

4. Badges

- No badge unlocks from private disputes (e.g., “First Victory” does NOT trigger)

Implementation notes:

- Filter queries for leaderboard, reputation updates, badge checks, and win/loss aggregations must include `WHERE moderation_mode = 'public'` (or equivalent ORM filter).
- Add automated tests to assert that private disputes do not change any public metric.
- Display a short tooltip in analytics pages noting "Private disputes excluded from public metrics."
