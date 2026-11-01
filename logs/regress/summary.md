# Regression summary

- base seed: 517299
- jobs: 44, passed: 44, failed: 0
- wall clock: 10.0 min (cap 15.0 min, 4 parallel jobs)
- transactions checked: 5108
- faulted flits injected: 3604

| config | test | seed | status | time (s) | txns | faults | A: crc/nak/replay/tmo/retrain | B: crc/nak/replay/tmo/retrain |
|---|---|---|---|---|---|---|---|---|
| default | backpressure_random | 517304 | PASS | 46.5 | 150 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | backpressure_random | 518318 | PASS | 44.9 | 150 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | clock_ratio_sweep | 517311 | PASS | 45.3 | 200 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | clock_ratio_sweep | 518325 | PASS | 43.0 | 200 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | crc_error_retry | 517305 | PASS | 32.8 | 200 | 23 | 13/13/7/0/0 | 10/9/11/0/0 |
| default | crc_error_retry | 518319 | PASS | 38.6 | 200 | 38 | 21/19/14/1/0 | 17/16/15/0/0 |
| default | credit_starvation | 517303 | PASS | 73.3 | 120 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | credit_starvation | 518317 | PASS | 75.3 | 120 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | csr_access | 517309 | PASS | 14.6 | 20 | 0 | 0/0/0/0/2 | 0/0/0/0/2 |
| default | csr_access | 518323 | PASS | 12.7 | 20 | 0 | 0/0/0/0/2 | 0/0/0/0/2 |
| default | error_storm_retrain | 517307 | PASS | 26.6 | 150 | 100 | 0/0/2/0/1 | 79/1/1/0/1 |
| default | error_storm_retrain | 518321 | PASS | 33.6 | 150 | 100 | 0/0/1/0/1 | 78/1/1/0/1 |
| default | flit_drop_timeout | 517306 | PASS | 38.4 | 140 | 524 | 0/27/30/10/0 | 0/23/32/10/0 |
| default | flit_drop_timeout | 518320 | PASS | 39.5 | 140 | 413 | 0/23/22/3/0 | 0/21/26/3/0 |
| default | link_fail_and_recover | 517308 | PASS | 42.3 | 120 | 553 | 214/1/1/0/1 | 218/1/1/0/1 |
| default | link_fail_and_recover | 518322 | PASS | 49.6 | 120 | 552 | 215/1/1/0/1 | 225/1/1/0/1 |
| default | ltssm_arcs | 517310 | PASS | 23.9 | 40 | 0 | 0/0/0/0/1 | 0/0/0/0/2 |
| default | ltssm_arcs | 518324 | PASS | 19.5 | 40 | 0 | 0/0/0/0/1 | 0/0/0/0/2 |
| default | max_burst | 517301 | PASS | 16.4 | 40 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | max_burst | 518315 | PASS | 19.9 | 40 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | outstanding_stress | 517302 | PASS | 40.3 | 120 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | outstanding_stress | 518316 | PASS | 44.2 | 120 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | random_rw | 517300 | PASS | 30.1 | 200 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | random_rw | 518314 | PASS | 30.7 | 200 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | reset_during_traffic | 517312 | PASS | 35.2 | 100 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | reset_during_traffic | 518326 | PASS | 28.3 | 100 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | smoke | 517299 | PASS | 10.0 | 2 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| default | smoke | 518313 | PASS | 12.6 | 2 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| small | crc_error_retry | 517331 | PASS | 50.0 | 200 | 60 | 33/31/22/0/0 | 27/27/20/0/0 |
| small | crc_error_retry | 518339 | PASS | 60.2 | 200 | 52 | 31/29/16/0/0 | 21/20/14/0/0 |
| small | credit_starvation | 517330 | PASS | 86.8 | 120 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| small | credit_starvation | 518338 | PASS | 88.9 | 120 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| small | error_storm_retrain | 517333 | PASS | 41.0 | 150 | 100 | 0/0/2/0/1 | 80/1/1/0/1 |
| small | error_storm_retrain | 518341 | PASS | 46.6 | 150 | 100 | 0/0/1/0/1 | 79/1/1/0/1 |
| small | flit_drop_timeout | 517332 | PASS | 46.9 | 140 | 530 | 0/12/31/7/0 | 0/28/24/13/0 |
| small | flit_drop_timeout | 518340 | PASS | 48.2 | 140 | 459 | 0/24/24/5/0 | 0/20/31/10/0 |
| small | max_burst | 517329 | PASS | 24.9 | 40 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| small | max_burst | 518337 | PASS | 27.4 | 40 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| small | random_rw | 517328 | PASS | 54.5 | 200 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| small | random_rw | 518336 | PASS | 57.6 | 200 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| small | reset_during_traffic | 517334 | PASS | 33.8 | 100 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| small | reset_during_traffic | 518342 | PASS | 31.3 | 100 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| small | smoke | 517327 | PASS | 11.2 | 2 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
| small | smoke | 518335 | PASS | 10.6 | 2 | 0 | 0/0/0/0/0 | 0/0/0/0/0 |
