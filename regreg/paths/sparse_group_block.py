from __future__ import print_function, division, absolute_import

from warnings import warn
from copy import copy
import gc

import numpy as np
import numpy.linalg as npl

import scipy.sparse

from . import subsample_columns
from ..affine import power_L, normalize, astransform
from ..smooth import glm, affine_smooth, sum as smooth_sum
from ..smooth.quadratic import quadratic_loss
from ..problems.simple import simple_problem
from ..identity_quadratic import identity_quadratic as iq
from ..atoms.sparse_group_block import sparse_group_block
from ..atoms.sparse_group_lasso import (_gauge_function_dual_strong, 
                                        _inside_set_strong)
from .group_lasso import group_lasso_path, default_lagrange_sequence

class sparse_group_block_path(group_lasso_path):

    BIG = 1e12 # lagrange parameter for finding null solution

    def __init__(self, 
                 saturated_loss, # shape (n,q) -- multiresponse
                 X, 
                 l1_penalty,
                 l2_penalty,
                 weights={},
                 elastic_net_param=None,
                 alpha=1.,  # elastic net mixing -- 1 is LASSO
                 l1_weight=0.95):

        self.saturated_loss = saturated_loss
        self.X = astransform(X)

        # the penalty parameters

        self.alpha = alpha
        self.penalty = sparse_group_block(self.X.input_shape + saturated_loss.shape[1:],
                                          l1_weight * l1_penalty, 
                                          (1 - l1_weight) * l2_penalty, 
                                          lagrange=1)
        self.group_shape = (self.penalty.shape[0],)
        self.shape = self.penalty.shape

        # elastic net part
        if elastic_net_param is None:
            elastic_net_param = np.ones(self.shape)
        self.elastic_net_param = elastic_net_param

        # find lagrange_max

        unpenalized_groups, unpenalized_idx = self.unpenalized # [], []
        self.solution = np.zeros(self.penalty.shape)

        self._unpenalized_vars = []
        self._unpenalized_idx = unpenalized_idx
        self._penalized_vars = np.ones(self.shape, np.bool)

        if np.any(unpenalized_idx):
            (self.final_step, 
             null_grad, 
             null_soln,
             null_linpred,
             _) = self.solve_subproblem(unpenalized_groups,
                                        self.BIG,
                                        tol=1.e-8)
            self.linear_predictor = null_linpred
            self.solution[self._unpenalized_vars] = null_soln
        else:
            self.linear_predictor = np.zeros(self.saturated_loss.shape)

        if np.any(self.elastic_net_param[self._unpenalized_vars]):
            warn('convention is that unpenalized parameters with have no Lagrange parameter in front '
                 'of their ridge term so that lambda_max is easily computed')

        self.grad_solution = (self.full_gradient(self.saturated_loss, 
                                                 self.linear_predictor) + self.enet_grad(self.solution, 
                                                                                         self._penalized_vars,
                                                                                         1))

    # methods potentially overwritten in subclasses for I/O considerations

    def check_KKT(self,
                  grad_solution,
                  solution,
                  lagrange_new,
                  penalty=None):

        if penalty is None:
            penalty = self.penalty

        results = _check_KKT(grad_solution, 
                             solution, 
                             self.penalty.l1_weight,
                             self.penalty.l2_weight,
                             lagrange_new)
        return results > 0

    def strong_set(self,
                   lagrange_cur,
                   lagrange_new,
                   grad_solution):

        _strong_bool = _strong_set(self.penalty.l1_weight,
                                   self.penalty.l2_weight,
                                   lagrange_cur,
                                   lagrange_new,
                                   grad_solution)
        _strong = np.nonzero(_strong_bool)[0]
        return (_strong, 
                _strong_bool,
                _strong)
                                             
    def solve_subproblem(self, candidate_groups, lagrange_new, **solve_args):
    
        # solve a problem with a candidate set

        sub_loss, sub_penalty, sub_X, candidate_bool = _restricted_problem(self.X, 
                                                                           self.saturated_loss, 
                                                                           self.alpha * lagrange_new, 
                                                                           self.penalty.l1_weight,
                                                                           self.penalty.l2_weight,
                                                                           candidate_groups,
                                                                           self.subsample_columns)
        if self.alpha < 1:
            sub_elastic_net = _restricted_elastic_net(self.elastic_net_param, 
                                                      self._penalized_vars,
                                                      lagrange_new,
                                                      self.alpha,
                                                      candidate_groups)

            sub_loss = smooth_sum([sub_loss, sub_elastic_net])
            sub_loss.shape = sub_elastic_net.shape

        sub_problem = simple_problem(sub_loss, sub_penalty)
        sub_problem.coefs[:] = self.solution[candidate_bool] # warm start
        sub_soln = sub_problem.solve(**solve_args)
        sub_grad = sub_loss.smooth_objective(sub_soln, mode='grad') 
        sub_linear_pred = sub_X.dot(sub_soln)
        return sub_problem.final_step, sub_grad, sub_soln, sub_linear_pred, candidate_bool

    def updated_ever_active(self,
                            index_obj):
        if not hasattr(self, '_ever_active'):
            self._ever_active = np.zeros(self.group_shape, np.bool)
        _ever_active = self._ever_active.copy()
        _ever_active[index_obj] = True
        return list(np.nonzero(_ever_active)[0])

    @property
    def unpenalized(self):
        """
        Unpenalized groups and variables.

        Returns
        -------

        groups : sequence
            Groups with weights equal to 0.

        variables : ndarray
            Boolean indicator that is True if no penalty on that variable.

        """
        return [], []

    def restricted_penalty(self, subset):
        vars = np.zeros(self.penalty.shape[0], np.bool)
        vars[subset] = True
        return sparse_group_block((vars.sum(), self.shape[1]),
                                  self.penalty.l1_weight,
                                  self.penalty.l2_weight,
                                  lagrange=1)
    # Some common loss factories

    @classmethod
    def logistic(cls, X, Y, *args, **keyword_args):
        Y = np.asarray(Y)
        return cls(glm.logistic_loglike(Y.shape, Y), X, *args, **keyword_args)

    @classmethod
    def gaussian(cls, X, Y, *args, **keyword_args):
        Y = np.asarray(Y)
        loss = quadratic_loss(Y.shape, offset=Y)
        return cls(loss, X, *args, **keyword_args)

# private functions

def _candidate_bool(groups, candidate_groups):

    candidate_bool = np.zeros(groups.shape, np.bool)
    for g in candidate_groups:
        group = groups == g
        candidate_bool += group

    return candidate_bool

def _restricted_elastic_net(elastic_net_params, 
                            penalized,
                            lagrange, 
                            alpha,
                            candidate_groups):

    new_params = elastic_net_params * (1 - alpha)
    new_params[penalized] *= lagrange 
    new_params = new_params[candidate_groups]
    return quadratic_loss(new_params.shape,
                          new_params,
                          Qdiag=True)

def _restricted_problem(X, 
                        saturated_loss, 
                        alpha,
                        l1_weight,
                        l2_weight,
                        candidate_groups,
                        subsample_columns):

    X_candidate = subsample_columns(X, candidate_groups)
    candidate_bool = np.zeros(X.input_shape[0], np.bool)
    candidate_bool[candidate_groups] = True
    restricted_penalty = sparse_group_block((X_candidate.shape[1], saturated_loss.shape[1]),
                                            l1_weight,
                                            l2_weight,
                                            lagrange=alpha)

    restricted_loss = affine_smooth(saturated_loss, X_candidate)
    restricted_loss.shape = X_candidate.shape[1:] + saturated_loss.shape[1:]
    return restricted_loss, restricted_penalty, X_candidate, candidate_bool

# for paths

def _strong_set(l1_weight,
                l2_weight,
                lagrange_cur, 
                lagrange_new, 
                grad,
                slope_estimate=1):

    """
    Guess at active groups at 
    lagrange_new based on gradient
    at lagrange_cur.
    """

    thresh = (slope_estimate + 1) * lagrange_new - slope_estimate * lagrange_cur
    return np.nonzero(np.array([_inside_set_strong(grad[i],
                                                   thresh,
                                                   l1_weight,
                                                   l2_weight) for i in range(grad.shape[0])]) == 0)

def _check_KKT(grad, 
               solution, 
               l1_weight,
               l2_weight,
               lagrange, 
               tol=1.e-2):

    """
    Check whether (grad, solution) satisfy
    KKT conditions at a given tolerance.

    Assumes lagrange form of penalty.

    """

    ACTIVE_L1 = 10
    ACTIVE_NORM = 11
    ACTIVE_L2 = 12
    INACTIVE = 2

    norm_soln = np.sqrt(np.sum(solution**2, 1))
    active = norm_soln > tol * max(norm_soln.sum(0), 1)
    results = np.zeros(grad.shape[0])

    for g in np.nonzero(active)[0]:
        subgrad_g = -grad[g]
        soln_g = solution[g]
        val_g, l1subgrad_g, l2subgrad_g = _gauge_function_dual_strong(subgrad_g,
                                                                      l1_weight,
                                                                      l2_weight)
        if val_g < lagrange * (1 - tol):
            results[g] = ACTIVE_NORM
        nonz = soln_g != 0

        # nonzero coordinates need the right sign and size
        if (np.linalg.norm((l1subgrad_g - l1_weight * np.sign(soln_g) * lagrange)[nonz]) > 
            tol * max(1, np.linalg.norm(soln_g))):
            results[g] = ACTIVE_L1

        # l2 subgrad should be parallel to soln_g
        if np.linalg.norm(l2subgrad_g / np.linalg.norm(l2subgrad_g) - 
                          soln_g / np.linalg.norm(soln_g)) > tol:
            results[g] = ACTIVE_L2

    for g in np.nonzero(~active)[0]:
        subgrad_g = -grad[g]
        if _gauge_function_dual_strong(subgrad_g, 
                                       l1_weight,
                                       l2_weight)[0] >= lagrange * (1 + tol):
            results[g] = INACTIVE
    return results

# # for paths

# def _check_KKT(sglasso, 
#                grad, 
#                solution, 
#                lagrange, 
#                tol=1.e-2):

#     """
#     Check whether (grad, solution) satisfy
#     KKT conditions at a given tolerance.

#     Assumes glasso is group_lasso in lagrange form
#     so that glasso.lagrange is not None
#     """

#     terms = sglasso.terms(solution)
#     norm_soln = np.linalg.norm(solution)

#     ACTIVE_L1 = 10
#     ACTIVE_NORM = 11
#     ACTIVE_L2 = 12
#     INACTIVE = 2
#     UNPENALIZED = 3

#     results = np.zeros(len(sglasso._sorted_groupids), np.int)
#     for i, g in enumerate(sglasso._sorted_groupids):
#         group = sglasso.groups == g
#         subgrad_g = -grad[group]
#         l1weight_g = sglasso.lasso_weights[group]
#         l2weight_g = sglasso.weights[g]
#         soln_g = solution[group]

#         if terms[i] > 1.e-6 * norm_soln: # active group
#             val_g, l1subgrad_g, l2subgrad_g = _gauge_function_dual_strong(subgrad_g, 
#                                                                           l1weight_g,
#                                                                           l2weight_g)
#             if val_g < lagrange * (1 - tol):
#                 results[i] = ACTIVE_NORM
#             nonz = soln_g != 0

#             # nonzero coordinates need the right sign and size
#             if (np.linalg.norm((l1subgrad_g - l1weight_g * np.sign(soln_g) * lagrange)[nonz]) > 
#                 tol * max(1, np.linalg.norm(soln_g))):
#                 results[i] = ACTIVE_L1

#             # l2 subgrad should be parallel to soln_g
#             if np.linalg.norm(l2subgrad_g / np.linalg.norm(l2subgrad_g) - 
#                               soln_g / np.linalg.norm(soln_g)) > tol:
#                 results[i] = ACTIVE_L2
#         elif l1weight_g.sum() + sglasso.weights[g] > 0: # inactive penalized
#             results[i] = (_gauge_function_dual_strong(subgrad_g, l1weight_g,
#                                                       l2weight_g)[0] >= lagrange * (1 + tol)) * INACTIVE
#         else:   # unpenalized
#             results[i] = (np.linalg.norm(subgrad_g) > tol * sqlasso.l1weight_g.mean()) * UNPENALIZED
#     return results
