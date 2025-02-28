"""Benchmark the scaling of alphacsc algorithm with multiple channels.

This script needs the following packages:
    conda install pandas
    conda install -c conda-forge pyfftw

This script performs the computations and save the results in a pickled file
`figures/methods_scaling_reg*.pkl` which can be plotted using
`scaling_channels_plot.py`.
"""
from pathlib import Path
import time
import itertools

import numpy as np
import pandas as pd
import scipy.sparse as sp
from joblib import Parallel, delayed, Memory

from alphacsc.utils.profile_this import profile_this  # noqa
from alphacsc.utils import check_random_state, get_D
from alphacsc.learn_d_z_multi import learn_d_z_multi
from alphacsc.utils.dictionary import get_lambda_max


START = time.time()
VERBOSE = 1


#####################################
# Dictionary initialization function
#####################################

def generate_D_init(n_atoms, n_channels, n_times_atom, random_state):
    rng = check_random_state(random_state)
    return rng.randn(n_atoms, n_channels + n_times_atom)


######################################
# Functions compared in the benchmark
######################################

def run_multichannel(X, D_init, reg, n_iter, random_state,
                     label, n_channels):
    n_atoms, n_channels_n_times_atom = D_init.shape
    n_times_atom = n_channels_n_times_atom - n_channels

    solver_z_kwargs = dict(max_iter=500, tol=1e-1)
    return learn_d_z_multi(
        X, n_atoms, n_times_atom, reg=reg, n_iter=n_iter,
        uv_constraint='separate', rank1=True, D_init=D_init,
        solver_d='alternate_adaptive', solver_d_kwargs=dict(max_iter=50),
        solver_z="lgcd", solver_z_kwargs=solver_z_kwargs,
        name="rank1-{}-{}".format(n_channels, random_state),
        random_state=random_state, n_jobs=1, verbose=VERBOSE)


def run_multivariate(X, D_init, reg, n_iter, random_state,
                     label, n_channels):
    n_atoms, n_channels_n_times_atom = D_init.shape
    n_times_atom = n_channels_n_times_atom - n_channels
    D_init = get_D(D_init, n_channels)

    solver_z_kwargs = dict(max_iter=500, tol=1e-1)
    return learn_d_z_multi(
        X, n_atoms, n_times_atom, reg=reg, n_iter=n_iter,
        uv_constraint='auto', rank1=False, D_init=D_init,
        solver_d='fista', solver_d_kwargs=dict(max_iter=50),
        solver_z="lgcd", solver_z_kwargs=solver_z_kwargs,
        name="dense-{}-{}".format(n_channels, random_state),
        random_state=random_state, n_jobs=1, verbose=VERBOSE,
        raise_on_increase=False)


def run_multivariate_dicodile(X, D_init, reg, n_iter, random_state,
                              label, n_channels):
    n_atoms, n_channels_n_times_atom = D_init.shape
    n_times_atom = n_channels_n_times_atom - n_channels
    D_init = get_D(D_init, n_channels)

    solver_z_kwargs = dict(max_iter=500, tol=1e-1)
    return learn_d_z_multi(
        X, n_atoms, n_times_atom, reg=reg, n_iter=n_iter,
        uv_constraint='auto', rank1=False, D_init=D_init,
        solver_d='auto', solver_d_kwargs=dict(max_iter=50),
        solver_z="dicodile", solver_z_kwargs=solver_z_kwargs,
        name="dicodile-{}-{}".format(n_channels, random_state),
        random_state=random_state, n_jobs=10, verbose=VERBOSE,
        raise_on_increase=False)


####################################
# Calling function of the benchmark
####################################

def one_run(X, n_channels, method, n_atoms, n_times_atom, random_state, reg):
    func, label, n_iter = method
    current_time = time.time() - START
    print('{}-{}-{}: started at {:.0f} sec'.format(
          label, n_channels, random_state, current_time))

    # use the same init for all methods
    D_init = generate_D_init(n_atoms, n_channels, n_times_atom, random_state)
    X = X[:, :n_channels]

    lmbd_max = get_lambda_max(X, D_init).mean()
    reg_ = reg * lmbd_max

    # run the selected algorithm with one iter to remove compilation overhead
    _, _, _, _, _ = func(X, D_init, reg_, 1, random_state, label, n_channels)

    # run the selected algorithm
    pobj, times, d_hat, z_hat, reg = func(
        X, D_init, reg_, n_iter, random_state, label, n_channels
    )

    # store z_hat in a sparse matrix to reduce size
    for z in z_hat:
        z[z < 1e-3] = 0
    z_hat = [sp.csr_matrix(z) for z in z_hat]

    current_time = time.time() - START
    print('{}-{}-{}: done at {:.0f} sec'.format(
          label, n_channels, random_state, current_time))
    assert len(times) > 5
    return (n_channels, random_state, label, np.asarray(pobj),
            np.asarray(times), np.asarray(d_hat), np.asarray(z_hat), n_atoms,
            n_times_atom, reg)


###############################
# Main script of the benchmark
###############################

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser('Programme to launch experiemnt')
    parser.add_argument('--njobs', type=int, default=1,
                        help='number of cores used to run the experiment')
    parser.add_argument('--dense', action="store_true",
                        help='run the experiment for multivariate')
    parser.add_argument('--dicodile', action="store_true",
                        help='run the experiment for multivariate dicodile')

    args = parser.parse_args()

    figures_dir = Path('figures')
    figures_dir.mkdir(exist_ok=True)

    # Use the caching utilities from joblib to same intermediate results and
    # avoid loosing computations when the interpreter crashes.
    mem = Memory(location='.', verbose=0)
    cached_one_run = mem.cache(func=one_run)
    delayed_one_run = delayed(cached_one_run)

    # load somato data
    from alphacsc.datasets.mne_data import load_data
    X, info = load_data(dataset='somato', epoch=False, n_jobs=args.njobs,
                        n_splits=1)

    # Set dictionary learning parameters
    n_atoms = 2  # K
    n_times_atom = 128  # L

    # Set the benchmarking parameters.
    reg = .005
    n_iter = 50
    n_states = 5

    # Select the method to run and the range of n_channels
    n_channels = X.shape[1]
    methods = [(run_multichannel, 'rank1', n_iter)]
    span_channels = np.unique(np.floor(
        np.logspace(0, np.log10(n_channels), 10)).astype(int))

    if args.dense:
        methods = [[run_multivariate, 'dense', n_iter]]
        span_channels = np.unique(np.floor(
            np.logspace(0, np.log10(n_channels), 10)).astype(int))[:5]

    if args.dicodile:
        methods = [[run_multivariate_dicodile, 'dicodile', n_iter]]
        span_channels = np.unique(np.floor(
            np.logspace(0, np.log10(n_channels), 10)).astype(int))[:5]

    # Create a grid a parameter for which we which to run the benchmark.
    iterator = itertools.product(range(n_states), methods, span_channels)

    # Run the experiment in parallel with joblib
    all_results = Parallel(n_jobs=args.njobs)(
        delayed_one_run(X, n_channels, method, n_atoms,
                        n_times_atom, rst, reg)
        for rst, method, n_channels in iterator)

    # save all results for plotting with scaling_channels_plot.py script.
    suffix = ""
    if args.dense:
        suffix = "_dense"
    if args.dicodile:
        suffix = "_dicodile"

    file_name = f'methods_scaling_reg{reg}{suffix}.pkl'
    save_path = figures_dir / file_name

    all_results_df = pd.DataFrame(
        all_results, columns='n_channels random_state label pobj times '
        'd_hat z_hat n_atoms n_times_atom reg'.split(' '))

    all_results_df.to_pickle(save_path)
    print('-- End of the script --')
