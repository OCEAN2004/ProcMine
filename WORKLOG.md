# Operation Logs → Automation Proposal: Engineering Work Log

This document chronicles the 7-day technical investigation, engineering decisions, failed experiments, algorithmic iterations, and business case justification.

---

# Day 1: Initial Repository Setup, Environment Config, and Worklog

## Objective

Establish a clean development environment, review data specifications, verify privacy constraints, and conduct initial reconnaissance of Dataset A and Dataset B without data leakage.

## What I Investigated

- Inspected repository structure: 63 sessions in `dataset_a/` (~162k events with ground truth) and 15 sessions in `dataset_b/` (~20k events without ground truth).
- Analyzed folder sizes: discovered over 10.4 GB of screen captures in `dataset_a/`. Evaluated whether raw images should be committed to Git.
- Inspected event schemas across `SYSTEM`, `L1`, `L2`, and `L3` layers.
- Investigated application shifts: noted Chrome (`chrome.exe`) and local ports 5122–5124 in Dataset A, vs Microsoft Edge (`msedge.exe`) and local ports 5132–5134 in Dataset B.

## What I Learned

- **Strict Data Minimization:** Raw screenshots contain sensitive employee desktop views and would inflate Git history beyond reasonable limits. Telemetry must be read dynamically from disk; binary images must remain in `.gitignore`.
- **Chunk vs Process Boundaries:** A single session contains multiple chunk folders (e.g. `chunk_1200` vs full timestamps). Chunks are recording buffer slices, not business units. Timelines must be stitched and sorted by UTC timestamp.
- **Unreliable Text Events:** `text_input_complete` is sparse and inconsistent. Semantic actions must be inferred from keystrokes, clipboard flows, and UIA control names.

## What I Built

- Configured Python 3.13 environment with `pandas`, `numpy`, `scikit-learn`, `matplotlib`, `seaborn`, `tqdm`, and `pytest`.
- Created project directory layout: `src/`, `notebooks/`, `automation/`, `outputs/`, `tests/`, `report/`.
- Configured `.gitignore` and `requirements.txt`.
- Initialized local Git repository and created root commit.

## Problems & Failed Approaches

- _Problem:_ Running subshell PowerShell commands with `$_` threw syntax errors due to string formatting.
- _Resolution:_ Switched to direct PowerShell pipeline commands and Python automation scripts.

## Decisions

- Frozen rule: Never hardcode port numbers (5122) or browser executables (`chrome.exe`) in segmentation logic, because Dataset B uses different infrastructure.

## Next Step

Implement unified data loader, event normalizer, and ground truth cataloging script.

### Generative AI Usage Log (Day 1)

- **Role / Task:** Project scoping and implementation plan structure.
- **Prompts / Actions:** Drafted architectural plan aligning with Master Development Instructions.
- **Accepted / Modified:** Adopted multi-signal boundary detection strategy; rejected deep-learning sequence models as unnecessary and non-generalizable.

---

# Day 2: Session Reconstruction, Preprocessing, and Ground-Truth Profiling

## Objective

Thoroughly understand Dataset A ground truth (`gt.jsonl`, `gt_manifest.json`), catalog all business processes, durations, and handling variants, and identify ground truth quirks.

## What I Investigated

- Parsed `gt_manifest.json` across all 63 sessions.
- Cataloged all 15 business processes (Codes A through O across HR, Finance, and Ops).
- Inspected event streams inside process executions vs inter-process idle gaps.
- Inspected ground truth quirks: duplicate `process_started` emissions and missing `end_ts` in truncated sessions.

## What I Learned

- In `gt_manifest.json`, some executions have `end_ts: null` when the recording terminated mid-task (`continues_to_next: true`). Data loader must handle null timestamps gracefully.
- Process executions in Dataset A have a median duration of 24 to 45 seconds (with complex budget variance tasks reaching 77 seconds).
- In 100% of analyzed sessions, every single business execution corresponds to the processing of ONE discrete case transaction (e.g. `BR-175009-001`, `RT-175009-001`).

## What I Built

- `src/data_loader.py`: Reconstructs multi-chunk sessions, parses ISO UTC timestamps, and loads structured ground truth executions.
- `src/preprocessing.py`: Filters recording noise (`upload_started`, `upload_completed`) and standardizes app/browser context.
- `src/analysis.py`: Computes high-level dataset statistics and exports `outputs/gt_inventory_a.csv`.
- `notebooks/01_dataset_exploration.ipynb` and `notebooks/02_ground_truth_analysis.ipynb`.

## Problems & Failed Approaches

- _Problem 1:_ `parse_iso_utc` crashed with `AttributeError: 'NoneType' object has no attribute 'replace'` when encountering null `end_ts`. Fixed by adding `Optional[str]` validation.
- _Problem 2:_ `UnicodeEncodeError: 'charmap' codec can't encode characters` when printing Japanese process names (`住民税通知確認`) to Windows console with cp1252 encoding.
- _Resolution:_ Added `sys.stdout.reconfigure(encoding="utf-8")` and `$env:PYTHONUTF8=1`.

## Decisions

- Anchored ground truth validation on exact temporal IoU and boundary tolerance windows (±5s, ±10s, ±30s).

## Next Step

Design the feature extraction pipeline and implement baseline segmentation.

### Generative AI Usage Log (Day 2)

- **Role / Task:** Ground truth parsing logic review.
- **Accepted / Modified:** Accepted fallback timestamp assignment for unclosed executions.

---

# Day 3: Feature Extraction, Boundary Detection, and Baseline Segmentation

## Objective

Engineer behavioral features from raw interaction streams and implement a baseline segmentation algorithm to identify transaction boundaries.

## What I Investigated

- Examined how case identifiers manifest in low-level logs: discovered that Windows UIA accessibility trees embed case tokens in automation IDs (e.g. `la-row-BR-175009-001`) and target element names.
- Analyzed inter-event gaps: median gap at ground truth boundaries is 0.61 seconds; mean gap is 5.99 seconds.
- Analyzed app transitions: in 82% of transitions between cases, the operator remained inside the browser portal, meaning app switches alone capture less than 20% of true task boundaries!

## What I Learned

- Pure application switching is completely insufficient for office portal automation segmentation. Table row selections and case token transitions are the authoritative boundary anchors.
- Pre-boundary lag: When an operator begins a case, they focus the window 3 to 6 seconds before clicking on the specific row. The algorithm must look backward ("snapback") to capture the true start of the task.

## What I Built

- `src/features.py`: Extracts temporal gaps, UIA case tokens, URL routes, submission action buttons, and clipboard transfer events.
- Initial baseline segmenter relying on idle pauses and route transitions.

## Problems & Failed Approaches

- _Failed Baseline:_ An initial naive baseline that split on every application switch (`app_switch`) yielded severe over-segmentation (over 120 segments per session where ground truth had only 32), dropping Precision below 25%.
- _Decision:_ Abandoned app-switch-only splitting in favor of case-anchored clustering with snapback.

## Next Step

Implement case-anchored segmentation with inter-case activity tracking.

### Generative AI Usage Log (Day 3)

- **Role / Task:** Review of regex token extractors.
- **Accepted / Modified:** Refined regex from `\b[A-Za-z0-9_]{1,8}-...` to `(?:^|[^A-Za-z0-9])([A-Z]{1,4}-\d{6,8}-\d{3,4}|P\d{1,2}-\d{6,8}-\d{3,4})\b` to prevent capturing prefixes like `btn` or `row`.

---

# Day 4: Evaluation Framework, Dataset A Validation, and Error Analysis

## Objective

Evaluate the segmentation engine against all 63 sessions in Dataset A, iteratively tune parameters, and conduct error taxonomy analysis.

## What I Investigated

- Evaluated session-level segmentation across Dataset A.
- Diagnosed why Precision was initially 34.9% despite 89.8% Recall.
- Discovered that when operators moved from the browser to Word or Excel, the case ID was not visible in the spreadsheet title. The algorithm prematurely terminated the segment after 3 seconds, assuming the case was finished!

## What I Learned

- **Continuous Activity Principle:** If an employee moves to Excel and types `=1218687...` with inter-event deltas < 15 seconds, they are actively working on the current case. An execution does not terminate until either a true idle gap (> 20s) occurs or the next case begins.
- Incorporating inter-case activity tracking caused Precision to surge from 34.9% to 93.26%, and F1 to 92.80%!

## What I Built

- `src/segmentation.py`: Implemented full case-anchored segmentation, pre-boundary snapback, and inter-case activity tracking.
- `src/evaluation.py`: Automated evaluation framework computing IoU, Precision, Recall, F1, and boundary errors.
- `notebooks/03_segmentation_validation.ipynb`.

## Benchmark Results (All 63 Sessions of Dataset A):

- Total Ground Truth Executions: 2,009
- Total Predicted Segments: 1,989
- Matched Executions: 1,855
- **Precision: 93.26% | Recall: 92.33% | F1 Score: 92.80%**
- **Median IoU Overlap: 69.84%**
- **Median Start Error: 4.79 seconds | Median End Error: 5.26 seconds**
- Over-segmentation: 3.83% | Under-segmentation: 5.23%

## Decisions

- Formally froze the segmentation methodology. Under no circumstances will Dataset B labels be manually doctored or reverse-engineered.

## Next Step

Apply the frozen segmentation pipeline to Dataset B and mine process inventories.

### Generative AI Usage Log (Day 4)

- **Role / Task:** Error taxonomy classification structure.
- **Accepted / Modified:** Structured error analysis into interruption splits, micro-rapid merges, and tail session dwell.

---

# Day 5: Dataset B Segmentation, Deliverable Generation, and Process Variants

## Objective

Run the frozen pipeline on unseen production data (Dataset B), generate `outputs/segments.jsonl`, analyze execution variants, and catalog processes.

## What I Investigated

- Processed all 15 sessions (20,477 events) of Dataset B.
- Discovered 13 distinct business processes (`P1` through `P13`) across Finance, HR, and Operations portals.
- Analyzed execution variants: identified 86 handling paths across the 95 recovered executions.
- Discovered high manual data transfer: operators frequently copy values between Edge and Excel spreadsheets (`expense_calc - Excel`).

## What I Learned

- The company's highest-volume manual operations center around **Payroll Items & Deductions Processing** (`finance_payroll_processing`, `hr_payroll_processing`, and `ops_payroll_processing`), consuming 57.64 recorded minutes across 31 executions.
- Process P6 (Finance Payroll) exhibits an average execution time of 88.1 seconds per case, with significant time spent manually typing formulas into Excel.

## What I Built

- `src/process_discovery.py`: Automated segmentation runner, summary aggregator, and chart visualizer.
- Deliverable 1: `outputs/segments.jsonl` (95 non-overlapping ISO-8601 UTC segments).
- `outputs/process_summary.csv` and `outputs/process_variants.csv`.
- Visual charts: `outputs/charts/process_frequency_duration.png`, `outputs/charts/process_duration_distributions.png`, `outputs/charts/process_app_breakdown.png`.
- `notebooks/04_dataset_b_analysis.ipynb`.

## Decisions

- Confirmed that `segments.jsonl` strictly follows the required format with UTC timestamps ending in `Z`.

## Next Step

Construct the ROI prioritization matrix and select the primary automation target.

### Generative AI Usage Log (Day 5)

- **Role / Task:** Aggregation script review and Matplotlib styling.
- **Accepted / Modified:** Generated dual-axis frequency/duration chart.

---

# Day 6: Automation Ranking Matrix, Design, and AutoReconcile Prototype

## Objective

Rank automation opportunities using a quantitative decision matrix, select the primary target process, author `automation/DESIGN.md`, and build an operational automation prototype.

## What I Investigated

- Formulated multi-factor decision matrix: $\text{Priority} = (\text{Impact} \times \text{Repetition} \times \text{Feasibility}) / (\text{Risk} \times \text{Complexity})$.
- Evaluated trade-offs: `finance_resident_tax` scored highest in risk isolation (70.04), but `finance_payroll_processing` / `hr_payroll_processing` scored highest in aggregate impact and manual friction reduction.
- Inspected actual telemetry steps: operators manually open Excel, type `=1218687...`, check monthly partner rates in Word (`getsujitsu_teigaku_torihikisaki_ichiran`), paste comments into Edge, and approve.

## What I Learned

- Deterministic Python automation is vastly superior to LLM agent approaches for payroll math: it guarantees 100% numerical accuracy, executes in milliseconds, and requires zero inference cost.
- Human-in-the-Loop approval is essential: standard cases ($\le 0.5\%$ variance) can be auto-approved, while material variances ($> 2.0\%$) and unregistered entities must be routed to a human review queue.

## What I Built

- `src/scoring.py`: Automated decision matrix ranking all 12 candidate business workflows.
- `automation/DESIGN.md`: Complete architectural design and business rule specification.
- `automation/models.py`: Data contracts (`ClaimRecord`, `PolicyRate`, `ReconciliationResult`).
- `automation/reconcile_engine.py`: Core deterministic calculation and policy lookup engine.
- `automation/mock_adapter.py`: High-fidelity simulation adapter for portal interactions with representative test cases.
- `automation/prototype.py`: Executable automation tool supporting `--mode demo` and `--mode interactive`.

## Decisions

- Selected **Payroll & Vendor Invoice Reconciliation (`ProcMine AutoReconcile`)** as the primary automation target.
- Rejected pure autonomous lights-out processing in favor of Human-in-the-Loop gating to protect against financial payroll errors.

## Next Step

Implement automated unit tests, finalize final report, and document reproduction guide in README.

### Generative AI Usage Log (Day 6)

- **Role / Task:** Review of tolerance threshold boundaries.
- **Accepted / Modified:** Adopted tiered tolerance ($\le 0.5\%$ auto-approve, $0.5-2.0\%$ warning, $>2.0\%$ review).

---

# Day 7: Testing, Documentation, Packaging & Final Review

## Objective

Create automated test suites, verify end-to-end reproducibility, author the executive final report, and finalize Git history.

## What I Investigated

- Verified that all prototype edge cases (negative amounts, missing vendor rates, material variances) fail safely.
- Verified that `outputs/segments.jsonl` contains strictly valid JSON objects with zero overlapping intervals.
- Tested complete test suite with `pytest`.

## What I Learned

- Automated tests caught a threshold edge case in `test_warning_approve_minor_rounding` where 0.16% variance was classified as auto-approved instead of warning-approved. Adjusted test claim to 0.97% variance.

## What I Built

- `tests/test_data_loader.py` (4 tests)
- `tests/test_segmentation.py` (3 tests)
- `tests/test_automation.py` (6 tests)
- Total test suite: 13 tests passing in 2.08 seconds.
- `report/FINAL_REPORT.md`: Comprehensive 19-section executive report.
- `README.md`: Complete reproduction instructions with exact working CLI commands.

## Final Deliverables Checklist:

- [x] `outputs/segments.jsonl` (95 segments for Dataset B, strictly formatted)
- [x] Full source code in `src/` and `automation/`
- [x] 4 Jupyter notebooks in `notebooks/`
- [x] Comprehensive test suite in `tests/` (100% passing)
- [x] Final Report in `report/FINAL_REPORT.md`
- [x] 7-Day Work Log in `WORKLOG.md`
- [x] Developer guide in `README.md`
- [x] Meaningful, multi-day Git commit history

### Generative AI Usage Log (Day 7)

- **Role / Task:** Report formatting and editorial review.
- **Accepted / Modified:** Formatted mathematical formulas in LaTeX notation and verified empirical figure consistency.
