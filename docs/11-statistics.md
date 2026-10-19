# Evaluation statistics

## What it does

Each evaluation runs a stated seed interval and records every terminal outcome. Success rate is a binomial estimate, not a guarantee. A Wilson interval provides uncertainty even when all sampled flights succeed or none do. Speed, tilt, offset and fuel are reported with mean and median.

## Why this approach

Development seeds are for checkpoint selection; the default full qualification pool is separate. Pilot samples are labeled and cannot close the 10,000-seed gate. Touchdown_speed is total terminal speed; for takeoff it is separation speed and must not be misread as impact speed.

## Key formulas

```text
p_hat = k/n
center = (p_hat + z^2/(2n))/(1+z^2/n)
halfwidth = z*sqrt(p_hat*(1-p_hat)/n + z^2/(4n^2))/(1+z^2/n)
z = 1.95996398454
```

## Five interview questions

1. **Why a confidence interval?** Finite samples leave uncertainty about the true probability under the modeled distribution.

2. **Why Wilson rather than a simple normal interval?** Wilson behaves better near zero or all-success counts and avoids a zero-width certainty claim.

3. **Does 10,000 successes prove no failures?** No. It gives a strong but finite sample result with a nonzero uncertainty bound and says nothing about unmodeled scenarios.

4. **Why use disjoint development/test seeds?** Selecting the best checkpoint on the same seeds later reported as independent evidence introduces selection bias.

5. **What does same-seed comparison buy?** Pairing starts and disturbances reduces variation unrelated to controller choice; it does not remove model bias.

## Evidence and further reading

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the actual validation record in [VALIDATION.md](VALIDATION.md).
