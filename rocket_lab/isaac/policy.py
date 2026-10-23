"""Checkpoint inference without importing MuJoCo or constructing a legacy world."""
import numpy as np
from ..storage import checkpoint_path,read_json


class NativePolicy:
    def __init__(self,identifier,config):
        from stable_baselines3 import PPO,SAC
        from stable_baselines3.common.vec_env import DummyVecEnv,VecNormalize
        from gymnasium import Env,spaces
        path=checkpoint_path(identifier);self.meta=read_json(path/'checkpoint.json')
        if not self.meta:raise ValueError('Checkpoint metadata missing')
        class Contract(Env):
            observation_space=spaces.Box(-np.inf,np.inf,(21,),dtype=np.float32)
            action_space=spaces.Box(-1.,1.,(3,),dtype=np.float32)
        self.normalizer=VecNormalize.load(path/'normalize.pkl',DummyVecEnv([Contract]))
        self.normalizer.training=False;self.normalizer.norm_reward=False
        cls=PPO if self.meta['algorithm']=='PPO' else SAC
        self.model=cls.load(path/'model.zip',device='cpu',**({'buffer_size':1} if cls is SAC else {}))
        self.config=config;self.trained=self.meta.get('config',{})
        self.qualification='Experimental transfer from MuJoCo; no Isaac qualification'

    def action(self,observation):
        values=observation.copy();source=self.config['training'];target=self.trained.get('training',{})
        ratio=np.asarray(source.get('observation_position_scale',[400]*3))/np.asarray(target.get('observation_position_scale',[400]*3))
        values[:3]*=ratio;values[15:18]*=ratio
        values[3:6]*=np.asarray(source.get('observation_velocity_scale',[50]*3))/np.asarray(target.get('observation_velocity_scale',[50]*3))
        return self.model.predict(self.normalizer.normalize_obs(np.array([values])),deterministic=True)[0][0]
