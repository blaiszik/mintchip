# Mintchip Skill Trigger Evaluation Report

**Status:** `PASS` | **Mode:** `offline_rubric`

| Metric | Value | Gate |
|---|---:|---:|
| Recall (TP / Pos) | 100.0% (10/10) | >= 90% |
| False-trigger rate (FP / Neg) | 0.0% (0/10) | <= 0% |
| Precision (TP / (TP+FP)) | 100.0% | — |
| Accuracy | 100.0% (20/20) | — |

## Skill Spec Checks

- `PASS` covers_word_sized_chips
- `PASS` covers_tables
- `PASS` covers_benchmarks_and_tests
- `PASS` forbids_routine_code
- `PASS` forbids_bare_scalars
- `PASS` escalates_full_plots_to_mintfig

## Per-Prompt Outcomes

| ID | Expected | Predicted | Rule |
|---|---|---|---|
| `pos_01_loss_sparkline` | trigger | trigger | `trigger_word_sized_chip` |
| `pos_02_ci_lift` | trigger | trigger | `trigger_bench_or_table` |
| `pos_03_before_after_delta` | trigger | trigger | `trigger_bench_or_table` |
| `pos_04_junit_test_strip` | trigger | trigger | `trigger_word_sized_chip` |
| `pos_05_latency_distribution` | trigger | trigger | `trigger_word_sized_chip` |
| `pos_06_git_diff_share` | trigger | trigger | `trigger_word_sized_chip` |
| `pos_07_benchmark_table` | trigger | trigger | `trigger_bench_or_table` |
| `pos_08_hyperfine_diff` | trigger | trigger | `trigger_bench_or_table` |
| `pos_09_coverage_bar` | trigger | trigger | `trigger_word_sized_chip` |
| `pos_10_go_cargo_bench` | trigger | trigger | `trigger_bench_or_table` |
| `neg_01_fix_keyerror` | no | no | `suppress_routine_code` |
| `neg_02_refactor_class` | no | no | `suppress_routine_code` |
| `neg_03_explain_traceback` | no | no | `suppress_routine_code` |
| `neg_04_add_cli_flag` | no | no | `suppress_routine_code` |
| `neg_05_write_unit_tests` | no | no | `suppress_routine_code` |
| `neg_06_git_rebase_conflict` | no | no | `suppress_routine_code` |
| `neg_07_explain_architecture` | no | no | `suppress_routine_code` |
| `neg_08_single_bare_scalar` | no | no | `suppress_bare_scalars` |
| `neg_09_two_bare_counts` | no | no | `suppress_bare_scalars` |
| `neg_10_publication_multipanel_plate` | no | no | `escalate_to_mintfig` |
