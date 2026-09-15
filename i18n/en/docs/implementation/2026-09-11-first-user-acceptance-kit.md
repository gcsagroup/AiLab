<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-11-first-user-acceptance-kit.md) · [繁體中文](../../../zh-TW/docs/implementation/2026-09-11-first-user-acceptance-kit.md) · [English](2026-09-11-first-user-acceptance-kit.md)
<!-- translation-navigation:end -->

<a id="首次用户验收材料与记录表"></a>

# First-Time User Acceptance Materials and Record Sheet

Status: pending execution. Based on the [original AC-25 criteria](../11-testing-and-acceptance.md). These materials do not replace five real users, prefill success, or count developer rehearsals toward the participant total.

<a id="执行前由负责人核实"></a>

## Lead’s Pre-Execution Checks

- Use the same candidate package that passed final verification. Record its version, build number, App digest, and organization signature for each participant; do not mix rebuilds during testing into the same batch.
- Use an applicable Apple Silicon/macOS environment and confirm clean installation with no models, projects, data, or history. Merely switching to an empty working directory is not a clean installation. Do not delete an existing working library to manufacture an empty state.
- Give each person an independent acceptance environment. Do not preload the previous participant’s downloads, cache, or projects for the next. Built-in App executors may be supplied with the package, but the participant must explicitly prepare models through the product.
- Participants must be target users of the product. Record only anonymous IDs U01—U05, relevant experience, and necessary device information; real names and account credentials are unnecessary.
- The observer first records the environment and start time. In-product help is allowed. Development documents or a developer clicking/entering values on behalf of the participant must be recorded as human assistance. Do not hide blockers and then judge completion as independent.

<a id="给参与者的任务说明"></a>

## Participant Task Instructions

In the application, choose a language-model trial, prepare a supported model, obtain your first real text result, and save it. Then exit normally and reopen the application, find the task and work you just created, and continue editing the input. You may use the application’s help. If a step is unclear, describe the difficulty so the observer can record it.

<a id="观察记录"></a>

## Observation Record

This table is for observers, not a click-by-click tutorial for participants.

| Checkpoint | Actual time/result | Blockers, human assistance, and evidence |
| --- | --- | --- |
| Zero models/projects/data/history before starting | To be recorded | To be recorded |
| Find the trial entry within the category | To be recorded | To be recorded |
| Create a project and select a first-phase model | To be recorded | To be recorded |
| Understand source, license, and preparation scope, then explicitly start | To be recorded | To be recorded |
| Complete dependency/device checks and model preparation | To be recorded | To be recorded |
| Enter a sample and understand pre-run checks | To be recorded | To be recorded |
| Obtain a real result after explicitly starting execution | To be recorded | Record run ID and result digest |
| Save the work | To be recorded | Record work ID and file digest |
| Find the original task/work after normal exit and reopening | To be recorded | Verify original run ID and preserved content |
| Continue editing input and save the draft | To be recorded | Automatic recomputation is not required |
| Total duration, computation wait, and download wait | To be recorded | List separately; do not report only clicking time |

On interruption, insufficient resources, or preparation failure, record the original message, whether a recovery entry was found, whether retry retained the same download/task ID, and whether entered content was lost. Fault observation must not damage the participant’s other data. Separately controlled fault tests and naturally encountered problems in this round are recorded separately.

<a id="五人结果汇总"></a>

## Five-Participant Results

| Anonymous ID | Candidate version/digest | Clean environment established | Result and continuation after restart | Human assistance/blockers | Total duration | Conclusion |
| --- | --- | --- | --- | --- | --- | --- |
| U01 | To be recorded | Untested | Untested | Untested | Untested | Untested |
| U02 | To be recorded | Untested | Untested | Untested | Untested | Untested |
| U03 | To be recorded | Untested | Untested | Untested | Untested | Untested |
| U04 | To be recorded | Untested | Untested | Untested | Untested | Untested |
| U05 | To be recorded | Untested | Untested | Untested | Untested | Untested |

Only when all five complete the task without blocking issues may a pass be signed off under the original criteria. In-product help and observed difficulties are still retained. Fixes after failure require a new candidate number and an explicit reverification scope; original records are not overwritten. This small sample does not represent all users. Actual conclusions are consolidated in the [delivery matrix](2026-09-10-current-delivery-matrix.md).
