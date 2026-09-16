# Automation System Architecture & Design: ProcMine AutoReconcile

## 1. Executive Summary & Target Process

- **Target Business Process:** Finance & Payroll Reconciliation (給与備考・控除整備および請求照合処理, Dataset B Process P6 / P4 / P10)
- **Business Domain:** Financial Operations & HR Shared Services
- **Primary Systems Involved:**
  - Internal Web Portal (Finance Accounting System `http://127.0.0.1:5133/` and HR System `http://127.0.0.1:5132/`)
  - Calculation Workbooks (`expense_calc.xlsx`, `budget_analysis.xlsx`)
  - Policy & Fixed Rate Master Documents (`getsujitsu_teigaku_torihikisaki_ichiran.docx`, `gyomu_itaku_kyuuyo_kitei.docx`)

---

## 2. Current Manual Workflow (Evidence from Telemetry)

Analysis of Dataset B operation logs reveals that staff manually perform the following repetitive steps for every transaction:

1. **Case Selection:** In Microsoft Edge, the operator opens the active batch list (`/payroll-items` or `/resident-tax`), scrolls through the table, and clicks a specific case row (e.g., `P6-07010448-012`).
2. **Context Switching to Spreadsheets:** The operator switches focus (`app_switch`) to Microsoft Excel (`expense_calc - Excel`).
3. **Manual Recalculation:** The operator manually types formulas (e.g., `=1218687...`) into Excel cells to compute gross pay, statutory deductions, tax allowances, or billing totals.
4. **Context Switching to Policy Documents:** The operator switches focus to Word (`getsujitsu_teigaku_torihikisaki_ichiran - Word`) to look up contracted monthly rates or vendor terms.
5. **Data Transfer via Clipboard:** The operator copies verified figures or standard comments to the clipboard (`clipboard_change`).
6. **Form Population:** The operator switches back to Edge, clicks the input field (`処理内容・確認コメントを入力してください…`), pastes the comment (`Ctrl+V`), and clicks `承認` (Approve) or `保留` (Hold).
7. **Repetition:** This cycle repeats 8 to 11 times per session, consuming an average of 88.1 seconds per case.

---

## 3. Key Operational Pain Points

1. **High Friction & Cognitive Overhead:** Frequent application switching (Edge ↔ Excel ↔ Word) leads to visual fatigue and increased error rates. Over 35% of session time is spent on window transitions and clipboard handoffs.
2. **Manual Calculation Errors:** Operators manually re-type monetary values into Excel formulas, introducing potential transposition typos.
3. **Latency & Scalability Bottlenecks:** Manual reconciliation limits throughput to approximately 35–45 cases per employee per day.
4. **Audit Trail Inconsistency:** Manual verification notes are unstructured, varying by operator wording and detail level.

---

## 4. Proposed Automated Workflow

The **ProcMine AutoReconcile Engine** eliminates manual data entry and calculation loops:

```
[System Batch Ingestion]
        ↓
[Schema & Field Validation]
        ↓
[Master Policy & Rate Lookup]  ←  (Automated JSON/Excel Master Tables)
        ↓
[Deterministic Rule Calculation]
  - Base vs Overtime Calculation
  - Statutory Deductions & Allowances
  - Discrepancy Margin Checking (Threshold: ±1.0%)
        ↓
     ┌────────────────────────────────┐
     │ Discrepancy or Variance > 1%?  │
     └────────────────────────────────┘
          /                      \
      [ NO ]                   [ YES ]
        ↓                         ↓
[Auto-Approval & Audit Log]   [Human-in-the-Loop Review Queue]
        ↓                         ↓
[Direct System Output]        [Operator Approval / Rejection Gate]
```

---

## 5. System Inputs and Outputs

### Inputs

- **Batch Transaction Feed:** JSON / CSV records representing pending portal claims (Case ID, Employee/Vendor Name, Department, Base Amount, Overtime Hours, Reported Deduction, Claimed Total).
- **Master Contract & Policy Registry:** Structured rate tables defining contracted partner tariffs, standard deduction codes, and tolerance thresholds.

### Outputs

- **Reconciliation Audit Journal (`reconciliation_journal.json` / `.csv`):** Complete execution log with calculated values, variance delta, approval status, and timestamp.
- **System Action Payload:** Simulated API payload ready for automated submission to the internal portal.
- **Exception Notification Queue:** Filtered list of outlier records requiring human review.

---

## 6. Business & Calculation Rules

1. **Gross Calculation:**
   $$\text{Computed Total} = \text{Base Amount} + (\text{Overtime Hours} \times \text{Contract Rate}) - \text{Statutory Deductions}$$
2. **Variance Threshold:**
   $$\text{Variance \%} = \frac{|\text{Claimed Total} - \text{Computed Total}|}{\text{Computed Total}} \times 100$$
3. **Approval Decision Rules:**
   - If $\text{Variance \%} \le 0.5\%$: **AUTO-APPROVE**.
   - If $0.5\% < \text{Variance \%} \le 2.0\%$: **FLAG_WARNING** (Auto-approve with warning comment).
   - If $\text{Variance \%} > 2.0\%$ or negative values or unknown partner: **REQUIRE_HUMAN_APPROVAL** (Route to Human Review Queue).

---

## 7. Human-in-the-Loop (HITL) Controls

- **Standard Cases (Estimated 75-80%):** Processed entirely deterministically without human intervention.
- **Discrepancy Cases (Estimated 15-20%):** Presented in a dedicated interactive CLI / UI where the operator inspects the claimed vs calculated variance, sees the exact discrepancy reason, and chooses `Approve (Override)` or `Reject / Return for Revision` with an audit comment.
- **Unrecognized Entities (Estimated <5%):** Flagged immediately for master data update.

---

## 8. Failure Modes & Error Handling

| Failure Scenario                                  | Automated Safeguard                                                               |
| ------------------------------------------------- | --------------------------------------------------------------------------------- |
| Malformed input records (missing required fields) | Transaction rejected to dead-letter queue; session continues without aborting.    |
| Negative amount or division by zero               | Strict schema validation catches invalid numbers prior to math execution.         |
| Duplicate Case ID submitted                       | De-duplication check based on transaction hash; skips duplicate with audit alert. |
| Master policy rate missing for entity             | Marked as `UNREGISTERED_ENTITY` and routed to human operator.                     |
| Network / System timeout during submission        | Exponential backoff retry with transactional rollback.                            |

---

## 9. Security & Compliance Considerations

- **Data Minimization:** No personal phone numbers, bank account numbers, or plain passwords processed.
- **Role-Based Access Control:** Separate roles for automated pipeline execution vs operator human override.
- **Immutable Audit Trail:** Every automated decision records timestamp (UTC), rule ID, computed difference, and decision signature.

---

## 10. Scope & Assumptions

- **In Scope:** Full parsing, validation, automated reconciliation, discrepancy calculation, interactive human review workflow, audit log generation, and unit testing.
- **Out of Scope:** Direct live database writing to the client's proprietary Oracle/SQL backend (simulated via high-fidelity mock adapter as required by the case).
