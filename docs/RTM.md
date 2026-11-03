# Requirements Traceability Matrix (RTM)

Change Management Software, Team 4. Links every SRS requirement to its Jira story, its Test Plan
test cases (section 13) and the automated tests that check it.

**Status key**
- **Pass**: implemented, and the automated tests pass in GitHub Actions on Ubuntu, Windows and macOS.
- **Pass (engine)**: the business rule is implemented and tested. The web page for it is a Sprint 2
  story, and `tests/test_integration.py` switches to that page automatically once it is merged.
- **Sprint 2**: story in progress; tests come with the story's pull request.
- **Not in scope**: no story in Sprint 1 or 2. To be recorded as a deviation in the final SRS/Test Plan.

*Last updated: 3 Nov 2026 (Sprint 2, day 2). Update the status column as each Sprint 2 PR merges.*

## Functional requirements

| Req ID | Requirement (short) | Story | Test Plan cases | Automated tests | Status |
|---|---|---|---|---|---|
| CMS-F-001 | Sign in and sign out | CMS-2 | TC-AUTH-01 | `test_auth.py`: `test_valid_login_redirects_home_and_shows_user`, `test_invalid_login_is_rejected_with_same_message`, `test_logout_signs_the_user_out`, `test_inactive_user_cannot_sign_in` | Pass |
| CMS-F-002 | Role-based permissions | CMS-2, CMS-5, CMS-7 | TC-AUTH-02 | `test_auth.py`: `test_wrong_role_gets_403`, `test_admin_passes_every_role_check`. `test_integration.py`: `test_only_the_right_people_can_move_a_request`, `test_non_reviewers_get_403_when_assigning` | Pass |
| CMS-F-003 | Create a CR | CMS-3 | TC-CR-01, TC-CR-02 | `test_change_requests.py`: `test_create_sets_number_status_requester_and_trimmed_values`, `test_new_form_valid_post_creates_request_and_redirects`. `test_integration.py`: `test_full_lifecycle_from_submission_to_closure` | Pass |
| CMS-F-004 | Validate CR fields | CMS-3 | TC-VAL-01, TC-CR-02 | `test_change_requests.py`: `test_create_rejects_invalid_fields_without_saving`, `test_new_form_invalid_post_keeps_values_and_creates_nothing`. `test_integration.py`: `test_invalid_form_creates_nothing` | Pass |
| CMS-F-005 | View, search, sort, filter | CMS-4 | (TC-CR-01 "visible in search") | `test_change_request_search.py`: all `test_search_*`, `test_filter_*`, `test_list_*`, `test_detail_*` | Pass |
| CMS-F-006 | Edit CR until Closed | CMS-11 (Dhanush) | TC-CLOSE-01 (edits blocked) | to come with CMS-11 | Sprint 2 |
| CMS-F-007 | Enforce the workflow | CMS-5 | TC-WF-01, TC-WF-02 | `test_workflow.py`: `test_every_pair_of_statuses_outside_the_table_is_rejected`, `test_a_change_request_can_go_from_submitted_to_closed_with_a_full_history`. `test_integration.py`: `test_full_lifecycle_from_submission_to_closure`, `test_steps_cannot_be_skipped` | Pass |
| CMS-F-008 | Approve / reject with reason | CMS-6 (Gayathri) | TC-WF-03 | `test_workflow.py`: `test_missing_input_is_refused_and_nothing_changes`. `test_integration.py`: `test_rejected_request_stops_and_cannot_be_assigned` | Pass (engine) |
| CMS-F-009 | Assign / reassign to active engineer | CMS-7 | TC-ASSIGN-01, TC-ASSIGN-02 | `test_assignment.py` (all). `test_integration.py`: `test_reassign_moves_work_to_the_new_engineer` | Pass |
| CMS-F-010 | Start work; work notes and comments | CMS-8 (Gayathri), CMS-10 (Hema) | — | start work: `test_workflow.py`, `test_integration.py`. Comments: to come with CMS-10 | Pass (engine) for start; Sprint 2 for comments |
| CMS-F-011 | Resolve with summary | CMS-8 (Gayathri) | TC-RES-01 | `test_workflow.py`: `test_resolving_saves_the_trimmed_summary_on_the_change_request`. `test_integration.py`: `test_only_the_right_people_can_move_a_request` | Pass (engine) |
| CMS-F-012 | Close, or reopen with reason | CMS-9 (Hema) | TC-CLOSE-01, TC-REOPEN-01 | `test_workflow.py`: `test_closing_sets_closed_at_and_other_moves_do_not`. `test_integration.py`: `test_reopen_then_resolve_and_close_again`, `test_reviewer_can_also_close_a_resolved_request` | Pass (engine) |
| CMS-F-013 | History of status and assignment changes | CMS-5, CMS-7 (timeline view: CMS-10) | TC-HIST-01 | `test_integration.py`: `test_full_lifecycle_with_reassignment_has_complete_history`. `test_assignment.py`: `test_assign_approved_cr_sets_assignee_status_and_history` | Pass (timeline page: Sprint 2) |
| CMS-F-014 | Due dates from priority; overdue flag | CMS-13 (Dhanush), CMS-12 | TC-SLA-01, TC-SLA-02 | overdue: `test_dashboard.py`: `test_overdue_boundaries`, `test_seeded_overdue_items`. Due-date calculation: to come with CMS-13 | Overdue: Pass. Due-date calculation: Sprint 2 |
| CMS-F-015 | In-app notifications | CMS-14 (Hema) | TC-ASSIGN-01, TC-REOPEN-01 (notified) | to come with CMS-14 | Sprint 2 |
| CMS-F-016 | Dashboard counts, my work, overdue | CMS-12 | TC-REP-01 | `test_dashboard.py` (all). `test_integration.py`: `test_dashboard_numbers_follow_the_lifecycle` | Pass |
| CMS-F-017 | Open-CR snapshot reports | — | TC-REP-01 | — | Not in scope (the dashboard covers counts by status and priority) |
| CMS-F-018 | Ageing / resolution-time reports | — | TC-REP-02 | — | Not in scope |
| CMS-F-019 | Audit events | CMS-5, CMS-7 (partial) | TC-AUDIT-01 | Status and assignment history tests above | Partial: workflow and assignment changes are recorded; user and settings changes are not |
| CMS-F-020 | Admin configures components, priorities, SLAs | — | — | — | Not in scope (fixed in `cms/constants.py`) |
| CMS-F-021 | Friendly errors, no stack traces | CMS-1, CMS-3 | TC-CR-02 | `test_project_setup.py`: `test_unknown_page_returns_404`. `test_workflow.py`: `test_all_errors_are_workflow_errors_with_a_message` | Pass |

## Non-functional and security requirements

| Req ID | Requirement (short) | Story | Test Plan cases | Automated tests | Status |
|---|---|---|---|---|---|
| CMS-NF-001 | 2 s for 90% of requests on 10,000 CRs | — | TC-PERF-01 | — | Not in scope (manual timing could be added if time allows) |
| CMS-NF-002 | Data survives restarts | CMS-1 | TC-RESTART-01 | `test_integration.py`: `test_data_survives_an_application_restart` | Pass |
| CMS-NF-003 | No plaintext passwords; auth required | CMS-2 | TC-SEC-01 | `test_project_setup.py`: `test_password_is_hashed`. `test_auth.py`: `test_password_is_not_stored_or_put_in_session` | Pass |
| CMS-NF-004 | Consistent UI, labels, validation feedback | all UI stories | — | `test_dashboard.py`: `test_statuses_and_priorities_have_text_labels`; manual UI check in the system test run | Pass (manual check pending) |
| CMS-NF-005 | Routes / services / models separated | CMS-1, CMS-5 | — | Service-level tests run without HTTP (`test_workflow.py`, `test_assignment.py`, `test_dashboard.py`) | Pass |
| CMS-NF-006 | Documented setup; runs on team machines | CMS-1 | — | GitHub Actions matrix on Ubuntu, Windows, macOS; README setup steps | Pass (clean-clone check pending) |
| CMS-NF-007 | No silent overwrite on concurrent edits | CMS-11 (if included) | TC-CONC-01 | — | Not in scope unless added to CMS-11 |
| CMS-SR-001 | Login before creating or changing CRs | CMS-2 | TC-AUTH-02 | `test_integration.py`: `test_pages_require_sign_in`. `test_auth.py`: `test_anonymous_user_is_sent_to_login_with_next` | Pass |
| CMS-SR-002 | Authorization enforced on the server | CMS-2, CMS-5, CMS-7 | TC-AUTH-02 | `test_assignment.py`: `test_other_roles_get_403_on_assign`, `test_service_refuses_non_reviewers`. `test_workflow.py`: `test_wrong_role_or_wrong_person_cannot_make_a_move_and_nothing_changes` | Pass |
| CMS-SR-003 | Salted password hashing; never logged | CMS-2 | TC-SEC-01 | `test_project_setup.py`: `test_password_is_hashed` | Pass |
| CMS-SR-004 | Server-side validation; escaped output | CMS-3 | TC-VAL-01, TC-VAL-02 | `test_integration.py`: `test_script_text_is_shown_as_plain_text`, `test_invalid_form_creates_nothing` | Pass |
| CMS-SR-005 | Record-level access | CMS-4, CMS-5 | TC-ASSIGN-03 | `test_change_request_search.py`: `test_detail_requester_role_isolation`. `test_workflow.py`: `test_only_the_assigned_engineer_may_start_or_resolve`. `test_integration.py`: `test_requesters_only_see_their_own_requests` | Pass |
| CMS-SR-006 | Audit without secrets | CMS-5, CMS-7 | TC-AUDIT-01 | History tests above (history rows store no passwords) | Partial (see CMS-F-019) |

## Test Plan cases not yet covered

| Test case | Waiting on |
|---|---|
| TC-CLOSE-01 ("further edits blocked") | CMS-11 edit |
| TC-ASSIGN-01, TC-REOPEN-01 ("engineer/assignee notified") | CMS-14 notifications |
| TC-REP-01, TC-REP-02, TC-PERF-01, TC-CONC-01 | Not in scope. Record as deviations or remove from the final Test Plan |
