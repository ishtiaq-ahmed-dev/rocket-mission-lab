"""A compact, from-scratch REINFORCE lesson on CartPole (no SB3).

The policy is a trainable categorical distribution over two actions. We sample
actions, collect rewards, compute discounted returns, then ascend the log
probability of actions weighted by their normalized returns. This is an
unbiased score-function policy-gradient estimator with a batch baseline.
CartPole is deliberately simpler than 6-DOF rocket flight.
Run: python -m rocket_lab.reinforce --episodes 400
"""
import argparse
import json
import numpy as np
import torch
from torch import nn
from torch.distributions import Categorical
import gymnasium as gym
from .config import DATA
from .storage import atomic_json

def lesson(episodes=400,seed=42):
    torch.set_num_threads(1); torch.manual_seed(seed); np.random.seed(seed)
    env=gym.make("CartPole-v1")
    policy=nn.Sequential(nn.Linear(4,32),nn.Tanh(),nn.Linear(32,2))
    optimizer=torch.optim.Adam(policy.parameters(),lr=.01)
    def evaluate_policy(random=False):
        scores=[]
        for s in range(10000,10020):
            obs,_=env.reset(seed=s); total=0
            for _ in range(500):
                with torch.no_grad():
                    action=int(np.random.randint(2)) if random else int(policy(torch.tensor(obs)).argmax())
                obs,reward,term,trunc,_=env.step(action);total+=reward
                if term or trunc:break
            scores.append(total)
        return float(np.mean(scores))
    random_score=evaluate_policy(True);initial_score=evaluate_policy()
    history=[]
    for episode in range(episodes):
        obs,_=env.reset(seed=seed+episode);log_probs=[];rewards=[]
        while True:
            distribution=Categorical(logits=policy(torch.tensor(obs)))
            action=distribution.sample();log_probs.append(distribution.log_prob(action))
            obs,reward,term,trunc,_=env.step(int(action));rewards.append(reward)
            if term or trunc:break
        # Return-to-go assigns future consequences to each sampled action.
        future=0.;returns=[]
        for reward in reversed(rewards):future=reward+.99*future;returns.insert(0,future)
        returns=torch.tensor(returns);returns=(returns-returns.mean())/(returns.std()+1e-8)
        loss=-(torch.stack(log_probs)*returns).sum()
        optimizer.zero_grad();loss.backward();nn.utils.clip_grad_norm_(policy.parameters(),5);optimizer.step()
        history.append(sum(rewards))
    final_score=evaluate_policy();env.close()
    result=dict(task="CartPole-v1",algorithm="REINFORCE from scratch",seed=seed,episodes=episodes,random_mean=random_score,initial_mean=initial_score,final_mean=final_score,evaluation_episodes=20,learned_better_than_random=final_score>random_score,training_returns=history)
    atomic_json(DATA/"reinforce-lesson.json",result); print(json.dumps({k:v for k,v in result.items() if k!="training_returns"},indent=2))
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--episodes",type=int,default=400);p.add_argument("--seed",type=int,default=42);a=p.parse_args();lesson(a.episodes,a.seed)
