# Main results (306-question benchmark, frozen snapshot eval_306_snapshot.json)

| Config | single hit@5 | single MRR | single2 hit@5 | single2 MRR | multihop hit@5 | multihop MRR |
| --- | --- | --- | --- |
| baseline | 0.852 | 0.647 | 0.930 ** | 0.740 | 0.983 ** | 0.890 |
| bm25 | 1.000 ** | 0.943 | 0.840 | 0.642 | 0.950 | 0.791 |
| hybrid_rrf | 1.000 ** | 0.882 | 0.860 | 0.650 | 0.983 ** | 0.870 |
| hybrid_v3_titleboost | 1.000 ** | 0.859 | 0.870 | 0.668 | 0.983 ** | 0.880 |
| routed_oracle | 1.000 ** | 0.859 | 0.870 | 0.668 | 0.983 ** | 0.890 |
| twostage | 0.481 | 0.481 | 0.450 | 0.410 | 0.725 | 0.631 |

Pairwise Wilcoxon p-values (per-question reciprocal rank):

**single**

| | baseline | bm25 | hybrid_rrf | hybrid_v3_titleboost | routed_oracle | twostage |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | — | 4.84e-08 | 1.06e-07 | 5.10e-07 | 5.10e-07 | 1.44e-02 |
| bm25 | 4.84e-08 | — | 8.96e-04 | 1.75e-04 | 1.75e-04 | 1.48e-09 |
| hybrid_rrf | 1.06e-07 | 8.96e-04 | — | 7.60e-02 | 7.60e-02 | 2.70e-08 |
| hybrid_v3_titleboost | 5.10e-07 | 1.75e-04 | 7.60e-02 | — | n/a | 1.16e-07 |
| routed_oracle | 5.10e-07 | 1.75e-04 | 7.60e-02 | n/a | — | 1.16e-07 |
| twostage | 1.44e-02 | 1.48e-09 | 2.70e-08 | 1.16e-07 | 1.16e-07 | — |

**single2**

| | baseline | bm25 | hybrid_rrf | hybrid_v3_titleboost | routed_oracle | twostage |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | — | 1.32e-02 | 3.99e-03 | 1.58e-02 | 1.58e-02 | 1.46e-07 |
| bm25 | 1.32e-02 | — | 7.69e-01 | 3.48e-01 | 3.48e-01 | 6.09e-08 |
| hybrid_rrf | 3.99e-03 | 7.69e-01 | — | 2.63e-01 | 2.63e-01 | 2.39e-05 |
| hybrid_v3_titleboost | 1.58e-02 | 3.48e-01 | 2.63e-01 | — | n/a | 2.34e-06 |
| routed_oracle | 1.58e-02 | 3.48e-01 | 2.63e-01 | n/a | — | 2.34e-06 |
| twostage | 1.46e-07 | 6.09e-08 | 2.39e-05 | 2.34e-06 | 2.34e-06 | — |

**multihop**

| | baseline | bm25 | hybrid_rrf | hybrid_v3_titleboost | routed_oracle | twostage |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | — | 1.58e-03 | 1.63e-01 | 5.21e-01 | n/a | 7.66e-08 |
| bm25 | 1.58e-03 | — | 1.17e-02 | 5.40e-03 | 1.58e-03 | 4.68e-05 |
| hybrid_rrf | 1.63e-01 | 1.17e-02 | — | 2.02e-01 | 1.63e-01 | 1.26e-06 |
| hybrid_v3_titleboost | 5.21e-01 | 5.40e-03 | 2.02e-01 | — | 5.21e-01 | 4.88e-07 |
| routed_oracle | n/a | 1.58e-03 | 1.63e-01 | 5.21e-01 | — | 7.66e-08 |
| twostage | 7.66e-08 | 4.68e-05 | 1.26e-06 | 4.88e-07 | 7.66e-08 | — |
