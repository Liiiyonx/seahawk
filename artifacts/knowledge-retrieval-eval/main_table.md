# Main results (306-question benchmark, frozen snapshot eval_306_snapshot.json)

| Config | single hit@5 | single MRR | single2 hit@5 | single2 MRR | multihop hit@5 | multihop MRR |
| --- | --- | --- | --- |
| baseline | 0.432 | 0.254 | 0.310 | 0.229 | 0.475 ** | 0.469 |
| bm25 | 0.457 ** | 0.302 | 0.180 | 0.164 | 0.075 | 0.135 |
| hybrid_rrf | 0.432 | 0.284 | 0.380 | 0.186 | 0.458 | 0.198 |
| hybrid_v3_titleboost | 0.444 | 0.278 | 0.410 ** | 0.186 | 0.458 | 0.198 |
| routed_oracle | 0.444 | 0.278 | 0.410 ** | 0.186 | 0.475 ** | 0.469 |
| twostage | 0.222 | 0.138 | 0.190 | 0.091 | 0.458 | 0.267 |

Pairwise Wilcoxon p-values (per-question reciprocal rank):

**single**

| | baseline | bm25 | hybrid_rrf | hybrid_v3_titleboost | routed_oracle | twostage |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | — | 1.48e-02 | 3.81e-02 | 2.63e-02 | 2.63e-02 | 1.59e-03 |
| bm25 | 1.48e-02 | — | 3.08e-01 | 2.70e-01 | 2.70e-01 | 1.63e-04 |
| hybrid_rrf | 3.81e-02 | 3.08e-01 | — | 9.52e-01 | 9.52e-01 | 9.40e-04 |
| hybrid_v3_titleboost | 2.63e-02 | 2.70e-01 | 9.52e-01 | — | n/a | 5.96e-04 |
| routed_oracle | 2.63e-02 | 2.70e-01 | 9.52e-01 | n/a | — | 5.96e-04 |
| twostage | 1.59e-03 | 1.63e-04 | 9.40e-04 | 5.96e-04 | 5.96e-04 | — |

**single2**

| | baseline | bm25 | hybrid_rrf | hybrid_v3_titleboost | routed_oracle | twostage |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | — | 3.78e-02 | 6.34e-02 | 2.99e-01 | 2.99e-01 | 1.23e-06 |
| bm25 | 3.78e-02 | — | 6.27e-02 | 6.78e-02 | 6.78e-02 | 9.13e-01 |
| hybrid_rrf | 6.34e-02 | 6.27e-02 | — | 8.40e-01 | 8.40e-01 | 2.69e-07 |
| hybrid_v3_titleboost | 2.99e-01 | 6.78e-02 | 8.40e-01 | — | n/a | 2.53e-06 |
| routed_oracle | 2.99e-01 | 6.78e-02 | 8.40e-01 | n/a | — | 2.53e-06 |
| twostage | 1.23e-06 | 9.13e-01 | 2.69e-07 | 2.53e-06 | 2.53e-06 | — |

**multihop**

| | baseline | bm25 | hybrid_rrf | hybrid_v3_titleboost | routed_oracle | twostage |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | — | 3.26e-06 | 2.32e-10 | 2.32e-10 | n/a | 3.21e-12 |
| bm25 | 3.26e-06 | — | 1.01e-04 | 1.01e-04 | 3.26e-06 | 4.81e-06 |
| hybrid_rrf | 2.32e-10 | 1.01e-04 | — | n/a | 2.32e-10 | 4.81e-09 |
| hybrid_v3_titleboost | 2.32e-10 | 1.01e-04 | n/a | — | 2.32e-10 | 4.81e-09 |
| routed_oracle | n/a | 3.26e-06 | 2.32e-10 | 2.32e-10 | — | 3.21e-12 |
| twostage | 3.21e-12 | 4.81e-06 | 4.81e-09 | 4.81e-09 | 3.21e-12 | — |
