"""Optional policy architecture experiments; no guidance or expert actions."""
import torch
from stable_baselines3.common.distributions import DiagGaussianDistribution
from stable_baselines3.common.policies import ActorCriticPolicy

class BoundedMeanPolicy(ActorCriticPolicy):
    """Keep Gaussian means inside actuator bounds before sampling.

    This transforms the mean, not the sampled action. PPO's Gaussian log
    likelihood remains unchanged; SB3 still clips stochastic tail samples.
    It is deliberately distinct from SAC's fully squashed distribution.
    """
    def _get_action_dist_from_latent(self,latent_pi):
        if not isinstance(self.action_dist,DiagGaussianDistribution):
            raise TypeError("BoundedMeanPolicy requires continuous diagonal-Gaussian actions")
        mean_actions=torch.tanh(self.action_net(latent_pi))
        return self.action_dist.proba_distribution(mean_actions,self.log_std)
