#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = "Qingqing Cao, https://awk.ai/, Twitter@sysnlp"

import argparse
import bisect
import json
from pathlib import Path

import numpy as np
import pandas as pd

from common import get_hw_energy
from common import sanitize

pd.set_option('display.float_format', '{:.6f}'.format)
res_names = ['cpu', 'mem', 'gpu', 'gpu_mem', 'gpu_clk', 'gpu_mem_clk']

feature_names = ['batch_size', 'seq_len', 'flops',
                 'mem_bytes'] + res_names + \
                ['times_mean',
                 'gpu_energy_mean',
                 'energy_mean',
                 'level_name', 'model_name']


def main(args):
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    runs = args.runs
    input_start = args.input_start
    input_length = args.input_length
    batch_start = args.batch_start
    batch_size = args.batch_size
    batch_step = args.batch_step
    seq_step = args.seq_step
    exp_type = args.exp_type
    exp_name = args.exp_name

    feature_file = out_dir / f'{exp_type}-{exp_name}_features.csv'

    res_file = args.res_file or out_dir / f'{exp_name}-res.csv'
    energy_file = args.energy_file or out_dir / f'{exp_name}-energy.csv'
    res = pd.read_csv(res_file)
    res = res.apply(pd.to_numeric)
    energy = get_hw_energy(energy_file)
    infos = []
    for model_name in args.models:
        feature_values = {k: [] for k in feature_names}
        for bs in range(batch_start, batch_size, batch_step):
            for seq_len in range(input_start, input_length, seq_step):
                name_s = sanitize(model_name)
                filename = f'{name_s}_{exp_type}_r{runs}_b{bs}_i{seq_len}.json'
                prof_file = Path(out_dir) / exp_name / filename
                if not prof_file.exists():
                    print(f'{prof_file} not exist!')
                    continue
                with open(prof_file) as f:
                    prof_info = json.load(f)
                process_record(energy, prof_info, res, feature_values,
                               model_name, bs, runs, seq_len)
        info = pd.DataFrame(data=feature_values)
        infos.append(info)
        print(f'{model_name} done.')
    pd.concat(infos).to_csv(feature_file, index=False)
    print('all done.')


def process_record(energy, prof_info, res, feature_values,
                   model_name, bs, runs, seq_len):
    res_np = res.to_numpy()
    res_t = res_np[:, 0]
    energy_np = energy.to_numpy()
    energy_t = energy_np[:, 0]
    for prof_item in prof_info:
        gpu_power_runs = []
        energy_runs = []
        times_runs = []
        res_runs = {k: [] for k in res_names}
        repeats = prof_item['repeats']
        for r in range(1, runs + 1):
            start_r = prof_item[f'start_{r}']
            end_r = prof_item[f'end_{r}']
            times_runs.append((end_r - start_r) / repeats)

            res_s = bisect.bisect_right(res_t, start_r)
            res_e = bisect.bisect_right(res_t, end_r)
            res_r = res[res_s:res_e]
            for rn in res_names:
                res_runs[rn].append(res_r[rn].mean())
            gpu_power_r = res_r['gpu_power'].div(repeats * 1e3).sum() * 0.17
            gpu_power_runs.append(gpu_power_r)

            # sampling rate is 170 ms
            e_s = bisect.bisect_right(energy_t, start_r)
            e_e = bisect.bisect_right(energy_t, end_r)
            energy_r = energy[e_s:e_e]['value'].div(repeats).sum() * 0.17
            energy_runs.append(energy_r)

        times_mean = np.mean(times_runs)
        # times_std = np.std(times_runs) / times_mean * 100
        gpu_power_mean = np.mean(gpu_power_runs)
        # gpu_power_std = np.std(gpu_power_runs) / gpu_power_mean * 100
        energy_mean = np.mean(energy_runs)
        # energy_std = np.std(energy_runs) / energy_mean * 100
        for rn in res_names:
            feature_values[rn].append(np.mean(res_runs[rn]))
            # rn_std = np.std(res_runs[rn]) / np.mean(res_runs[rn]) * 100
            # feature_values[f'{rn}_std'].append(rn_std)

        flops = prof_item['flops'] / 1e6
        mem_bytes = prof_item['mem_bytes'] / 1024 / 1024
        feature_values['batch_size'].append(bs)
        feature_values['seq_len'].append(seq_len)
        feature_values['energy_mean'].append(energy_mean)
        # feature_values['energy_std_percent'].append(energy_std)
        feature_values['gpu_energy_mean'].append(gpu_power_mean)
        # feature_values['gpu_energy_std_percent'].append(gpu_power_std)
        feature_values['flops'].append(flops)
        feature_values['mem_bytes'].append(mem_bytes)
        feature_values['times_mean'].append(times_mean)
        # feature_values['times_std_percent'].append(times_std)
        feature_values['level_name'].append(prof_item['name'])
        feature_values['model_name'].append(model_name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--out_dir", type=str, required=True,
                        help="output dir")
    parser.add_argument("-e", "--exp_name", type=str, required=True,
                        help="experiment name")
    parser.add_argument("-ef", "--energy_file", type=str, default=None)
    parser.add_argument("-rf", "--res_file", type=str, default=None)
    parser.add_argument("-bt", "--batch_start", type=int, default=8,
                        help="batch size start")
    parser.add_argument("-b", "--batch_size", type=int, default=33,
                        help="batch size")
    parser.add_argument("-bs", "--batch_step", type=int, default=8,
                        help="batch size step")
    parser.add_argument("-ss", "--seq_step", type=int, default=32,
                        help="input size step")
    parser.add_argument("-is", "--input_start", type=int, default=32,
                        help="input sequence length")
    parser.add_argument("-i", "--input_length", type=int, default=257,
                        help="input sequence length")
    parser.add_argument("-r", "--runs", type=int, default=1,
                        help="iterations to run the model")
    parser.add_argument("-m", "--models", type=str, nargs="+",
                        help="model name supported by the "
                             "HuggingFace Transformers library")
    parser.add_argument("-t", "--exp_type", type=str, required=True,
                        choices=('ml', 'ml-np', 'module', 'model'),
                        help="ml, module, model type")
    main(parser.parse_args())
