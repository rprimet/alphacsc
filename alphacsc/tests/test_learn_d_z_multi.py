import pytest
import numpy as np

from alphacsc.utils import check_random_state
from alphacsc.learn_d_z_multi import learn_d_z_multi


@pytest.mark.parametrize('window', [False, True])
@pytest.mark.parametrize('loss', ['l2', 'dtw', 'whitening'])
@pytest.mark.parametrize('solver_d, uv_constraint', [
    ('joint', 'joint'), ('joint', 'separate'),
    # ('alternate', 'separate'),
    ('alternate_adaptive', 'separate')
])
def test_learn_d_z_multi(loss, solver_d, uv_constraint, window):
    # smoke test for learn_d_z_multi
    n_trials, n_channels, n_times = 2, 3, 100
    n_times_atom, n_atoms = 10, 4

    loss_params = dict(gamma=1, sakoe_chiba_band=10, ordar=10)

    rng = check_random_state(42)
    X = rng.randn(n_trials, n_channels, n_times)
    pobj, times, uv_hat, z_hat, reg = learn_d_z_multi(
        X, n_atoms, n_times_atom, uv_constraint=uv_constraint,
        solver_d=solver_d, random_state=0, n_iter=30,
        solver_z='l-bfgs', window=window,
        loss=loss, loss_params=loss_params)

    msg = "Cost function does not go down for uv_constraint {}".format(
        uv_constraint)

    try:
        assert np.sum(np.diff(pobj) > 0) == 0, msg
    except AssertionError:
        import matplotlib.pyplot as plt
        plt.semilogy(pobj - np.min(pobj) + 1e-6)
        plt.title(msg)
        plt.show()
        raise


@pytest.mark.parametrize('solver_d, uv_constraint',
                         [('joint', 'joint'), ('joint', 'separate'),
                          ('alternate_adaptive', 'separate')])
def test_window(solver_d, uv_constraint):
    # Smoke test that the parameter window does something
    n_trials, n_channels, n_times = 2, 3, 100
    n_times_atom, n_atoms = 10, 4

    rng = check_random_state(42)
    X = rng.randn(n_trials, n_channels, n_times)

    kwargs = dict(X=X, n_atoms=n_atoms, n_times_atom=n_times_atom,
                  uv_constraint=uv_constraint, solver_d=solver_d,
                  random_state=0, n_iter=1, solver_z='l-bfgs')
    res_False = learn_d_z_multi(window=False, **kwargs)
    res_True = learn_d_z_multi(window=True, **kwargs)

    assert not np.allclose(res_False[2], res_True[2])


def test_online_learning():
    # smoke test for learn_d_z_multi
    n_trials, n_channels, n_times = 2, 3, 100
    n_times_atom, n_atoms = 10, 4

    rng = check_random_state(42)
    X = rng.randn(n_trials, n_channels, n_times)
    pobj_0, _, _, _, _ = learn_d_z_multi(
        X, n_atoms, n_times_atom, uv_constraint="separate",
        solver_d="joint", random_state=0, n_iter=30,
        solver_z='l-bfgs', algorithm="batch",
        loss='l2')

    pobj_1, _, _, _, _ = learn_d_z_multi(
        X, n_atoms, n_times_atom, uv_constraint="separate",
        solver_d="joint", random_state=0, n_iter=30,
        solver_z='l-bfgs', algorithm="online",
        algorithm_params=dict(batch_size=n_trials, alpha=0),
        loss='l2')

    assert np.allclose(pobj_0, pobj_1)
