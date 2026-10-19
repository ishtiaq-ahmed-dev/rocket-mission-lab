# Soft actor-critic

## What it does

SAC reuses experience from a replay buffer. Two critic networks estimate action values, and the actor optimizes expected value plus entropy. Target critics are softly updated to stabilize bootstrapping. The temperature controls the exploration-reward tradeoff.

## Why this approach

The candidate uses the same observations, actions and physics as PPO. CUDA is supported and was used on the verified RTX 5070 Ti. Evaluation loads only the policy/critics with a one-transition placeholder replay buffer, avoiding an unnecessary full training buffer allocation.

## Key formulas

```text
J_pi = E[alpha*log pi(a|s) - min(Q1(s,a),Q2(s,a))]
y = r + gamma*(min(Q1_target,Q2_target) - alpha*log pi(a_next|s_next))
Q_target <- tau*Q + (1-tau)*Q_target
```

## Five interview questions

1. **Why twin critics?** Using the minimum of two estimates mitigates optimistic value-estimation bias, though it can introduce pessimism.

2. **Why off-policy?** Replay allows several updates from earlier experience and improves sample reuse.

3. **What is the entropy temperature?** Alpha weighs stochasticity relative to reward; automatic tuning adjusts it toward a target entropy.

4. **Can this project exactly resume SAC?** Weights and normalization are saved, but replay-buffer persistence and exact resumed equivalence are not yet implemented.

5. **Is SAC automatically better than PPO?** No. Compare actual held-out success, robustness and compute cost at matching distributions and budgets.

## Evidence and further reading

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the actual validation record in [VALIDATION.md](VALIDATION.md).
