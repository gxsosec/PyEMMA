# This file is part of PyEMMA.
#
# Copyright (c) 2016 Computational Molecular Biology Group, Freie Universitaet Berlin (GER)
#
# PyEMMA is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import numpy as _np

__all__ = [
    'get_averaged_bias_matrix',
    'get_umbrella_sampling_data',
    'get_multi_temperature_data']

# ==================================================================================================
# helpers for discrete estimations
# ==================================================================================================

def get_averaged_bias_matrix(bias_sequences, dtrajs, nstates=None):
    from thermotools.util import logsumexp as _logsumexp
    from thermotools.util import logsumexp_pair as _logsumexp_pair
    from thermotools.util import kahan_summation as _kahan_summation
    nmax = int(_np.max([dtraj.max() for dtraj in dtrajs]))
    if nstates is None:
        nstates = nmax + 1
    elif nstates < nmax + 1:
        raise ValueError("nstates is smaller than the number of observed microstates")
    nthermo = bias_sequences[0].shape[1]
    bias_matrix = -_np.ones(shape=(nthermo, nstates), dtype=_np.float64) * _np.inf
    counts = _np.zeros(shape=(nstates,), dtype=_np.intc)
    for s in range(len(bias_sequences)):
        for i in range(nstates):
            idx = (dtrajs[s] == i)
            nidx = idx.sum()
            if nidx == 0:
                continue
            counts[i] += nidx
            selected_bias_sequence = bias_sequences[s][idx, :]
            for k in range(nthermo):
                bias_matrix[k, i] = _logsumexp_pair(
                    bias_matrix[k, i],
                    _logsumexp(
                        _np.ascontiguousarray(-selected_bias_sequence[:, k]),
                        inplace=False))
    return _np.log(counts)[_np.newaxis, :] - bias_matrix

# ==================================================================================================
# helpers for umbrella sampling simulations
# ==================================================================================================

def _ensure_umbrella_center(candidate, dimension):
    if isinstance(candidate, (_np.ndarray)):
        assert candidate.ndim == 1
        assert candidate.shape[0] == dimension
        return candidate.astype(_np.float64)
    elif isinstance(candidate, (int, long, float)):
        return candidate * _np.ones(shape=(dimension,), dtype=_np.float64)
    else:
        raise TypeError("unsupported type")

def _ensure_force_constant(candidate, dimension):
    if isinstance(candidate, (_np.ndarray)):
        assert candidate.shape[0] == dimension
        if candidate.ndim == 2:
            assert candidate.shape[1] == dimension
            return candidate.astype(_np.float64)
        elif candidate.ndim == 1:
            return _np.diag(candidate).astype(dtype=_np.float64)
        else:
            raise TypeError("usupported shape")
    elif isinstance(candidate, (int, long, float)):
        return candidate * _np.ones(shape=(dimension, dimension), dtype=_np.float64)
    else:
        raise TypeError("unsupported type")

def _get_umbrella_sampling_parameters(
    us_trajs, us_centers, us_force_constants, md_trajs=None, kT=None):
    umbrella_centers = []
    force_constants = []
    ttrajs = []
    nthermo = 0
    for i in range(len(us_trajs)):
        state = None
        this_center = _ensure_umbrella_center(
            us_centers[i], us_trajs[i].shape[1])
        this_force_constant = _ensure_force_constant(
            us_force_constants[i], us_trajs[i].shape[1])
        for j in range(nthermo):
            if _np.all(umbrella_centers[j] == this_center) and \
                _np.all(force_constants[j] == this_force_constant):
                state = j
                break
        if state is None:
            umbrella_centers.append(this_center.copy())
            force_constants.append(this_force_constant.copy())
            ttrajs.append(nthermo * _np.ones(shape=(us_trajs[i].shape[0],), dtype=_np.intc))
            nthermo += 1
        else:
            ttrajs.append(state * _np.ones(shape=(us_trajs[i].shape[0],), dtype=_np.intc))
    if md_trajs is not None:
        umbrella_centers.append(
            _np.zeros(shape=umbrella_centers[-1].shape, dtype=umbrella_centers[-1].dtype))
        force_constants.append(
            _np.zeros(shape=force_constants[-1].shape, dtype=force_constants[-1].dtype))
        for md_traj in md_trajs:
            ttrajs.append(nthermo * _np.ones(shape=(md_traj.shape[0],), dtype=_np.intc))
        nthermo += 1
    umbrella_centers = _np.array(umbrella_centers, dtype=_np.float64)
    force_constants = _np.array(force_constants, dtype=_np.float64)
    if kT is not None:
        assert isinstance(kT, (int, long, float))
        assert kT > 0.0
        force_constants /= kT
    return ttrajs, umbrella_centers, force_constants

def _get_umbrella_bias_sequences(trajs, umbrella_centers, force_constants):
    from thermotools.util import get_umbrella_bias as _get_umbrella_bias
    bias_sequences = []
    for traj in trajs:
        bias_sequences.append(
            _get_umbrella_bias(traj, umbrella_centers, force_constants))
    return bias_sequences

def get_umbrella_sampling_data(us_trajs, us_centers, us_force_constants, md_trajs=None, kT=None):
    r"""
    Wraps umbrella sampling data or a mix of umbrella sampling and and direct molecular dynamics

    Parameters
    ----------
    us_trajs : list of N arrays, each of shape (T_i, d)
        List of arrays, each having T_i rows, one for each time step, and d columns where d is the
        dimension in which umbrella sampling was applied. Often d=1, and thus us_trajs will
        be a list of 1d-arrays.
    us_centers : array-like of size N
        List or array of N center positions. Each position must be a d-dimensional vector. For 1d
        umbrella sampling, one can simply pass a list of centers, e.g. [-5.0, -4.0, -3.0, ... ].
    us_force_constants : float or array-like of float
        The force constants used in the umbrellas, unit-less (e.g. kT per length unit). If different
        force constants were used for different umbrellas, a list or array of N force constants
        can be given. For multidimensional umbrella sampling, the force matrix must be used.
    md_trajs : list of M arrays, each of shape (T_i, d), optional, default=None
        Unbiased molecular dynamics simulations. Format like umbrella_trajs.
    kT : float (optinal)
        Use this attribute if the supplied force constants are NOT unit-less.

    Returns
    -------
    ttrajs : list of N+M int arrays, each of shape (T_i,)
        The integers are indexes in 0,...,K-1 enumerating the thermodynamic states the trajectories
        are in at any time.
    btrajs : list of N+M float arrays, each of shape (T_i, K)
        The floats are the reduced bias energies for each thermodynamic states and configuration.
    umbrella_centers : float array of shape (K, d)
        The individual umbrella centers labelled accordingly to ttrajs.
    force_constants : float array of shape (K, d, d)
        The individual force matrices labelled accordingly to ttrajs.
    """
    ttrajs, umbrella_centers, force_constants = _get_umbrella_sampling_parameters(
        us_trajs, us_centers, us_force_constants, md_trajs=md_trajs, kT=kT)
    if md_trajs is None:
        md_trajs = []
    btrajs = _get_umbrella_bias_sequences(us_trajs + md_trajs, umbrella_centers, force_constants)
    return ttrajs, btrajs, umbrella_centers, force_constants

# ==================================================================================================
# helpers for multi-temperature simulations
# ==================================================================================================

def _get_multi_temperature_parameters(temptrajs):
    temperatures = []
    for temptraj in temptrajs:
        temperatures += _np.unique(temptraj).tolist()
    temperatures = _np.array(_np.unique(temperatures), dtype=_np.float64)
    nthermo = temperatures.shape[0]
    ttrajs = []
    for temptraj in temptrajs:
        ttraj = _np.zeros(shape=temptraj.shape, dtype=_np.intc)
        for k in range(nthermo):
            ttraj[(temptraj == temperatures[k])] = k
        ttrajs.append(ttraj.copy())
    return ttrajs, temperatures

boltzmann_constant_in_kcal_per_mol = 0.0019872041
conversion_factor_J_per_cal = 4.184
conversion_shift_Celsius_to_Kelvin = 273.15

def _get_multi_temperature_bias_sequences(
    energy_trajs, temp_trajs, temperatures, ref_temp,
    energy_unit, temp_unit):
    assert isinstance(energy_unit, str), 'energy_unit must be type str'
    assert isinstance(temp_unit, str), 'temp_unit must be type str'
    assert energy_unit.lower() in ('kcal/mol', 'kj/mol', 'kt'), \
        'energy_unit must be \'kcal/mol\', \'kJ/mol\' or \'kT\''
    assert temp_unit.lower() in ('kt', 'k', 'c'), \
        'temp_unit must be \'K\', \'C\' or \'kT\''
    btrajs = []
    if energy_unit.lower() == 'kt':
        # reduced case: energy_trajs in kT, temp_trajs unit does not matter as it cancels
        for energy_traj, temp_traj in zip(energy_trajs, temp_trajs):
            btrajs.append(
                (1.0 / temperatures[_np.newaxis, :] - 1.0 / ref_temp) * \
                (temp_traj * energy_traj)[:, _np.newaxis])
    elif temp_unit.lower() == 'kt':
        # non-reduced case with kT values instead of temperatures
        # this implicitly assumes the users' unit of k_B equals unit of energy_trajs
        for energy_traj, temp_traj in zip(energy_trajs, temp_trajs):
            btrajs.append(
                (1.0 / temperatures[_np.newaxis, :] - 1.0 / ref_temp) * energy_traj[:, _np.newaxis])
    else:
        # non-reduced case and temperatures given
        kT = temperatures
        rT = ref_temp
        if temp_unit.lower() == 'c':
            kT += conversion_shift_Celsius_to_Kelvin
            rT += conversion_shift_Celsius_to_Kelvin
        kT *= boltzmann_constant_in_kcal_per_mol
        rT *= boltzmann_constant_in_kcal_per_mol
        if energy_unit.lower() == 'kj/mol':
            kT *= conversion_factor_J_per_cal
            rT *= conversion_factor_J_per_cal
        for energy_traj, temp_traj in zip(energy_trajs, temp_trajs):
            btrajs.append((1.0 / kT[_np.newaxis, :] - 1.0 / rT) * energy_traj[:, _np.newaxis])
    return btrajs

def get_multi_temperature_data(
    energy_trajs, temp_trajs, energy_unit, temp_unit, ref_temp=None):
    ttrajs, temperatures = _get_multi_temperature_parameters(temp_trajs)
    if ref_temp is None:
        ref_temp = temperatures[0]
    btrajs = _get_multi_temperature_bias_sequences(
        energy_trajs, temp_trajs, temperatures, ref_temp, energy_unit, temp_unit)
    return ttrajs, btrajs, temperatures
