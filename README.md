# Operation Logs → Automation Proposal

## Submission Information

- **Name:** Sagar Gupta
- **University:** IIT (ISM) Dhanbad
- **Department:** Mechanical Engineering
- **Major / Branch:** Mining Machinery Engineering
- **Email:** 24je0522@iitism.ac.in

An autonomous process mining, segmentation, and high-ROI automation solution developed for enterprise back-office operations (HR, Finance, Operations).

This repository converts low-level employee computer telemetry (keystrokes, application focus switches, accessibility tree selections, and temporal bursts) into discrete business process executions, discovers operational bottlenecks in unseen production logs, and implements a working automation prototype with human-in-the-loop controls.

---

## 1. Project Highlights & Results

- **Validated Segmentation Engine:** Evaluated across all 63 sessions (162,768 events) of Dataset A:
  - **Precision:** 93.26%
  - **Recall:** 92.33%
  - **F1 Score:** 92.80%
  - **Median IoU Overlap:** 69.84%
  - **Median Boundary Error:** 4.79s (Start) / 5.26s (End)
  - **Boundary Accuracy ($\le 10\text{s}$):** 72.13%
- **Dataset B Production Discovery:** Unsupervised segmentation of 15 production sessions (20,477 events) yielding:
  - **`outputs/segments.jsonl`:** 95 validated, non-overlapping business executions.
  - **13 Discovered Business Processes** and **86 Handling Variants**.
- **Working Automation Prototype (`ProcMine AutoReconcile`):**
  - Targets **Finance & HR Payroll/Invoice Reconciliation (Process P6 & P4)**, representing **>32% of total operational time**.
  - 100% deterministic mathematical calculations, master policy lookups, tiered tolerance auto-approval ($\le 0.5\%$), and an interactive Human-in-the-Loop review queue.
  - **71.4% reduction in manual effort** on benchmark batches.
- **Automated Test Suite:** 13 unit tests covering data loading, multi-chunk stitching, boundary monotonicity, schema compliance, and automation exception handling (**100% passing**).

---

## 2. Repository Structure

```text
.
├── dataset_a/                       <- Validation data (63 sessions, ~162k events, ground truth)
├── dataset_b/                       <- Challenge data (15 sessions, ~20k events, unlabeled)
│
├── src/                             <- Core pipeline implementation
│   ├── __init__.py
│   ├── data_loader.py               <- Multi-chunk session reconstruction & UTC timestamp parsing
│   ├── preprocessing.py             <- Noise filtering & context normalization
│   ├── features.py                  <- Temporal, UIA case token & interaction features
│   ├── segmentation.py              <- Case-anchored segmentation with snapback alignment
│   ├── evaluation.py                <- Dataset A evaluation against ground truth
│   ├── process_discovery.py         <- Dataset B segmentation runner & summary generator
│   └── scoring.py                   <- Multi-factor automation priority scoring matrix
│
├── automation/                      <- Automation prototype
│   ├── __init__.py
│   ├── DESIGN.md                    <- System architecture & business rules specification
│   ├── models.py                    <- Data contracts & result representations
│   ├── reconcile_engine.py          <- Core deterministic calculation engine & policy registry
│   ├── mock_adapter.py              <- High-fidelity portal simulation & representative test cases
│   └── prototype.py                 <- Executable CLI entrypoint (demo & interactive modes)
│
├── notebooks/                       <- Jupyter exploration notebooks
│   ├── 01_dataset_exploration.ipynb
│   ├── 02_ground_truth_analysis.ipynb
│   ├── 03_segmentation_validation.ipynb
│   └── 04_dataset_b_analysis.ipynb
│
├── outputs/                         <- Generated artifacts and deliverables
│   ├── segments.jsonl               <- Official Step 1 deliverable for Dataset B
│   ├── process_summary.csv          <- Discovered process inventory
│   ├── process_variants.csv         <- Discovered execution variants
│   ├── automation_priority_matrix.csv <- Ranked decision matrix
│   ├── reconciliation_journal.csv   <- Prototype execution audit journal
│   └── charts/                      <- Visual analytics charts
│
├── tests/                           <- Unit test suite (pytest)
│   ├── test_data_loader.py
│   ├── test_segmentation.py
│   └── test_automation.py
│
├── report/
│   └── FINAL_REPORT.md              <- Comprehensive 19-section executive final report
│
├── WORKLOG.md                       <- 7-Day chronological development log & AI disclosures
├── requirements.txt                 <- Pinned Python dependencies
├── DATA_SCHEMA.md                   <- Data specification
└── README.md                        <- Reproduction & developer guide
```

---

## 3. Installation & Setup

### Prerequisites

- Python 3.11+ (Tested on Python 3.13.5)
- Git

### Installation

```bash
# Clone the repository
git clone <repository_url>
cd <repository_directory>

# Install core dependencies
pip install -r requirements.txt
```

---

## 4. How to Run the Pipeline (Exact Commands)

All commands are verified and executable directly from the repository root.

### 1. Run Data Reconnaissance & Ground Truth Profiling

Generates high-level telemetry distributions and outputs `outputs/gt_inventory_a.csv`:

```bash
python -m src.analysis
```

### 2. Reproduce Dataset A Segmentation Evaluation

Evaluates the segmentation engine against official ground truth across all 63 sessions of Dataset A:

```bash
python -m src.evaluation
```

### 3. Generate Dataset B Segments & Process Discovery

Applies the frozen segmentation pipeline to Dataset B, generating `outputs/segments.jsonl`, summary CSVs, and charts in `outputs/charts/`:

```bash
python -m src.process_discovery
```

### 4. Run Automation Opportunity Ranking Matrix

Evaluates all candidates and generates `outputs/automation_priority_matrix.csv`:

```bash
python -m src.scoring
```

### 5. Run the Working Automation Prototype

Run the end-to-end reconciliation demonstration:

```bash
# Demo mode (batch processing with audit logging and portal simulation)
python -m automation.prototype --mode demo

# Interactive mode (human-in-the-loop review queue for flagged exceptions)
python -m automation.prototype --mode interactive
```

### 6. Run the Automated Test Suite

Executes the full suite of unit tests:

```bash
pytest tests/ -v
```

---

## 5. Official Deliverable: `outputs/segments.jsonl`

The output format conforms strictly to the specification in `INSTRUCTION.md`:

```json
{
  "session_id": "ses_20260701-164424-CHAITANYA0BCF",
  "start": "2026-07-01T16:44:51.355Z",
  "end": "2026-07-01T16:45:20.506Z",
  "label": "finance_payroll_processing"
}
```

- **Timestamps:** ISO-8601 in UTC ending in `Z`.
- **Intervals:** Strictly non-overlapping within each session.
- **Consistency:** Discovered processes receive consistent canonical labels across all sessions.

---

## 6. Key Findings & Strategic Recommendations

1. **The Core Bottleneck is Cross-Department Payroll & Invoice Checking:**
   - In Dataset B, staff spend over **32% of total operational time** on `finance_payroll_processing`, `hr_payroll_processing`, and `ops_payroll_processing`.
   - Operators manually copy figures between Edge and Excel spreadsheets (`expense_calc.xlsx`) to perform basic mathematical adjustments, introducing high fatigue and typo risks.
2. **Deterministic Automation > Probabilistic LLMs:**
   - The selected reconciliation workflow relies on clear mathematical formulas and contract rate tables. Deterministic Python execution provides 100% precision, zero token costs, and instant execution.
3. **Human-in-the-Loop Governance:**
   - Standard claims ($\le 0.5\%$ variance) auto-approve instantly.
   - Material discrepancies ($> 2.0\%$) and unregistered entities automatically escalate to an interactive review queue, eliminating financial risk.

---

## 7. License & Compliance

Developed as part of the FDE Selection Internship Case Study. Telemetry logs and raw screenshots are governed by corporate privacy and data minimization policies.
