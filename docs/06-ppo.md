# Proximal policy optimization

## What it does

PPO alternates policy rollouts and several minibatch optimization epochs. A probability ratio compares the new policy with the policy that collected the rollout. Clipping discourages excessively large updates. A learned value baseline reduces policy-gradient variance.

## Why this approach

SB3 supplies the tested algorithm. This project uses a small MLP, normalized observations/rewards and a fixed seed. MLP PPO defaults to CPU because the environment loop and small batch transfers often dominate. Its final step count can exceed the budget by a rollout.

## Key formulas

```text
ratio = pi_new(a|s) / pi_old(a|s)
L_clip = E[min(ratio*A, clip(ratio,1-eps,1+eps)*A)]
delta_t = r_t + gamma*V(s_next) - V(s)
A_GAE = sum_l (gamma*lambda)^l * delta_(t+l)
```

## Five interview questions

1. **What does clipping accomplish?** It removes the incentive to keep increasing the surrogate objective after a ratio exceeds the configured interval in the advantageous direction; it is not a hard KL constraint.

2. **What is GAE?** A discounted sum of temporal-difference residuals controlled by lambda, trading bias against variance.

3. **Why entropy regularization?** It rewards policy spread and can prevent premature collapse, but too much exploration harms precise control.

4. **Why save VecNormalize?** Network inputs depend on running statistics. Replaying weights with different statistics changes behavior.

5. **Why does CPU sometimes beat CUDA?** A tiny MLP may spend more time transferring data and waiting on CPU simulation than doing matrix arithmetic.

## Evidence and further reading

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the actual validation record in [VALIDATION.md](VALIDATION.md).
