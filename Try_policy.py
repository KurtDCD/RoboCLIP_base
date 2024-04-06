from gym import Env, spaces
import numpy as np
from stable_baselines3 import PPO
import torch as th
from s3dg import S3D
from gym.wrappers.time_limit import TimeLimit
from stable_baselines3.common.vec_env.subproc_vec_env import SubprocVecEnv
from stable_baselines3.common.callbacks import CheckpointCallback
from PIL import Image, ImageSequence
import torch as th
from s3dg import S3D
import numpy as np
from PIL import Image, ImageSequence
import cv2
import gif2numpy
import PIL
import os
import seaborn as sns
import matplotlib.pylab as plt

from typing import Any, Dict

import gym
from gym.spaces import Box
import torch as th

from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.evaluation import evaluate_policy
from stable_baselines3.common.logger import Video
import os
from stable_baselines3.common.monitor import Monitor
import argparse
from stable_baselines3.common.callbacks import EvalCallback

import metaworld
from metaworld.envs import (ALL_V2_ENVIRONMENTS_GOAL_OBSERVABLE,
                            ALL_V2_ENVIRONMENTS_GOAL_HIDDEN)

from kitchen_env_wrappers import readGif
from matplotlib import animation
import matplotlib.pyplot as plt


class MetaworldSparse(Env):
    def __init__(self, env_id, text_string=None, time=False, video_path=None, rank=0, human=True):
        super(MetaworldSparse,self)
        door_open_goal_hidden_cls = ALL_V2_ENVIRONMENTS_GOAL_HIDDEN[env_id]
        env = door_open_goal_hidden_cls(seed=rank)
        self.env = TimeLimit(env, max_episode_steps=128)#steps=128
        self.time = time
        if not self.time:
            self.observation_space = self.env.observation_space
        else:
            self.observation_space = Box(low=-8.0, high=8.0, shape=(self.env.observation_space.shape[0]+1,), dtype=np.float32)
        self.action_space = self.env.action_space
        self.past_observations = []
        self.window_length = 16
        self.net = S3D('s3d_dict.npy', 512)

        # Load the model weights
        self.net.load_state_dict(th.load('s3d_howto100m.pth'))
        # Evaluation mode
        self.net = self.net.eval()
        self.target_embedding = None
        if text_string:
            text_output = self.net.text_module([text_string])
            self.target_embedding = text_output['text_embedding']
        if video_path:
            frames = readGif(video_path)
            
            if human:
                frames = self.preprocess_human_demo(frames)
            else:
                frames = self.preprocess_metaworld(frames)
            if frames.shape[1]>3:
                frames = frames[:,:3]
            video = th.from_numpy(frames)
            video_output = self.net(video.float())
            self.target_embedding = video_output['video_embedding']
        assert self.target_embedding is not None

        self.counter = 0

    def get_obs(self):
        return self.baseEnv._get_obs(self.baseEnv.prev_time_step)

    def preprocess_human_demo(self, frames):
        frames = np.array(frames)
        frames = frames[None, :,:,:,:]
        frames = frames.transpose(0, 4, 1, 2, 3)
        return frames

    def preprocess_metaworld(self, frames, shorten=True):
        center = 240, 320
        h, w = (250, 250)
        x = int(center[1] - w/2)
        y = int(center[0] - h/2)
        # frames = np.array([cv2.resize(frame, dsize=(250, 250), interpolation=cv2.INTER_CUBIC) for frame in frames])
        frames = np.array([frame[y:y+h, x:x+w] for frame in frames])
        a = frames
        frames = frames[None, :,:,:,:]
        frames = frames.transpose(0, 4, 1, 2, 3)
        if shorten:
            frames = frames[:, :,::4,:,:]
        # frames = frames/255
        return frames
        
    
    def render(self,mode='human'):
        frame = self.env.render(mode=mode)
        # center = 240, 320
        # h, w = (250, 250)
        # x = int(center[1] - w/2)
        # y = int(center[0] - h/2)
        # frame = frame[y:y+h, x:x+w]
        return frame


    def step(self, action):
        obs, _, done, info = self.env.step(action)
        self.past_observations.append(self.env.render())
        self.counter += 1
        t = self.counter/128
        if self.time:
            obs = np.concatenate([obs, np.array([t])])
        if done:
            #print("INSIDE")
            frames = self.preprocess_metaworld(self.past_observations)
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter('best_model_500kep_feedback.mp4', fourcc, 20, (640, 480))

            for frame in self.past_observations:
                # Convert frames to BGR format for OpenCV if necessary
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                out.write(frame)

            # Release everything when job is finished
            out.release()
        
            video = th.from_numpy(frames)

            video_output = self.net(video.float())

            video_embedding = video_output['video_embedding']
            similarity_matrix = th.matmul(self.target_embedding, video_embedding.t())

            reward = similarity_matrix.detach().numpy()[0][0]
            return obs, reward, done, info
        return obs, 0.0, done, info

    def reset(self):
        self.past_observations = []
        self.counter = 0
        if not self.time:
            return self.env.reset()
        return np.concatenate([self.env.reset(), np.array([0.0])])

def visualize_policy(env_id, model_path):
    #env = MetaworldSparse(env_id=env_id, video_path="./gifs/human_opening_door.gif", time=True, rank=0, human=True)
    env = MetaworldSparse(env_id=env_id, text_string="robot opening green drawer", time=True, rank=0, human=True)
    env = TimeLimit(env, max_episode_steps=128)
    model = PPO.load(model_path)
    obs = env.reset()
    count=0
    for _ in range(2500):  # Adjust the range for longer or shorter episodes
        action, _states = model.predict(obs, deterministic=True)
        obs, rewards, dones, info = env.step(action)
        count+=1
        if dones:
            #print("Count:",count)/home/kurt/IRL/RoboCLIP/metaworld/drawer-open-v2-goal-hidden_sparse_learntTest1
            count=0
            obs = env.reset()

if __name__ == "__main__":
    env_id = "drawer-open-v2-goal-hidden"  # Replace with your environment ID
    model_path = "/home/kurt/IRL/RoboCLIP/metaworld/drawer-open-v2-goal-hidden_interactiveFinetuned_interactive_test/best_model.zip"  # Update this path to your model
    visualize_policy(env_id, model_path)