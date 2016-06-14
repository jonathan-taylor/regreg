import numpy as np
import warnings
from scipy import sparse

from . import smooth_atom, affine_smooth
from ..affine import (astransform, 
                      linear_transform, 
                      affine_transform)
from ..identity_quadratic import identity_quadratic
from ..atoms.seminorms import l1norm

class glm(smooth_atom):

    """
    A general linear model, usually a log-likelihood
    for response $Y$ whose mean is modelled through
    $X\beta$. 

    Usual examples are Gaussian (least squares regression),
    logistic regression and Poisson log-linear regression.
    
    Huber loss is also implemented as an example.

    """

    def __init__(self, 
                 X, 
                 Y, 
                 loss, 
                 quadratic=None, 
                 initial=None,
                 offset=None):

        """

        Parameters
        ----------

        X : ndarray
            The design matrix.

        Y : ndarray
            The response.

        loss : `regreg.smooth.smooth_atom`
            The loss function that takes arguments the same
            size as `Y`. So, for Gaussian regression 
            the loss is just the map $\mu \mapsto \|\mu - Y\|^2_2/2$.

        quadratic : `regreg.identity_quadratic.identity_quadratic`
            Optional quadratic part added to objective.

        initial : ndarray
            An initial guess at the minimizer.

        """

        self.loss = loss
        self.data = X, Y
        self.affine_atom = affine_smooth(loss, X)
        smooth_atom.__init__(self,
                             X.shape[1],
                             coef=1.,
                             offset=offset,
                             quadratic=quadratic,
                             initial=initial)

    def smooth_objective(self, beta, mode='func', check_feasibility=False):
        """

        Parameters
        ----------

        beta : ndarray
            The current parameter values.

        mode : str
            One of ['func', 'grad', 'both']. 

        check_feasibility : bool
            If True, return `np.inf` when
            point is not feasible, i.e. when `beta` is not
            in the domain.

        Returns
        -------

        If `mode` is 'func' returns just the objective value 
        at `beta`, else if `mode` is 'grad' returns the gradient
        else returns both.
        """
        beta = self.apply_offset(beta)
        return self.affine_atom.smooth_objective(beta, mode=mode, check_feasibility=check_feasibility)

    def get_data(self):
        return self._X, self._Y

    def set_data(self, data):
        X, Y = data
        self._transform = astransform(X)
        self._X = X
        self._is_transform = id(self._X) == id(self._transform) # i.e. astransform was a nullop
        self._Y = Y
        self.loss.data = Y

    data = property(get_data, set_data, doc="Data for the general linear model.")

    def linear_predictor(self, beta):
        """

        Compute $X\beta$.

        Parameters
        ----------

        beta : ndarray
            Parameters.

        Returns
        -------

        linpred : ndarray

        """
        # can have an `R`-type offset by using affine_map here
        return self._transform.linear_map(beta)

    def objective(self, beta):
        """
        Compute the loss $\ell(X\beta)$.

        Parameters
        ----------

        beta : ndarray
            Parameters.

        Returns
        -------

        objective : float
            Value of the loss at $\beta$.

        """
        return self.smooth_objective(beta, 'func')

    def gradient(self, beta):
        """

        Compute the gradient of the loss $ \nabla \ell(X\beta)$.

        Parameters
        ----------

        beta : ndarray
            Parameters.

        Returns
        -------

        grad : ndarray
            Gradient of the loss at $\beta$.
        """

        return self.smooth_objective(beta, 'grad')

    def hessian(self, beta):
        """

        Compute the Hessian of the loss $ \nabla^2 \ell(X\beta)$.


        Parameters
        ----------

        beta : ndarray
            Parameters.

        Returns
        -------

        hess : ndarray
            Hessian of the loss at $\beta$, if defined.

        """

        linpred = self.linear_predictor(beta)
        if self._is_transform:
            raise ValueError('refusing to form Hessian for arbitrary affine_transform, use an ndarray or scipy.sparse')
        if not hasattr(self.loss, 'hessian'):
            raise ValueError('loss has no hessian method')
        W = self.loss.hessian(linpred)
        X = self.data[0]
        if not sparse.issparse(X): # assuming it is an ndarray
            return X.T.dot(W[:,None] * X)
        else:
            return X.T * np.diag(W) * X

    def latexify(self, var=None, idx=''):
        return self.affine_atom.latexify(var=var, idx=idx)

    @staticmethod
    def gaussian(X, response,
                 coef=1., 
                 offset=None,
                 quadratic=None, 
                 initial=None):
        """
        Create a loss for a Gaussian regression model.

        Parameters
        ----------

        X : [ndarray, `regreg.affine.affine_transform`]
            Design matrix

        Y : ndarray
            Response vector.

        offset : ndarray (optional)
            Offset to be applied in parameter space before 
            evaluating loss.

        quadratic : `regreg.identity_quadratic.identity_quadratic` (optional)
            Optional quadratic to be added to objective.

        initial : ndarray
            Initial guess at coefficients.
           
        Returns
        -------

        glm_obj : `regreg.glm.glm`
            General linear model loss.

        """
        loss = gaussian_loglike(response.shape,
                                response,
                                coef=coef)
        return glm(X, 
                   response, 
                   loss,
                   offset=offset,
                   quadratic=quadratic,
                   initial=initial)

    @staticmethod
    def logistic(X, successes, 
                 trials=None,
                 coef=1., 
                 offset=None,
                 quadratic=None, 
                 initial=None):
        """
        Create a loss for a logistic regression model.

        Parameters
        ----------

        X : [ndarray, `regreg.affine.affine_transform`]
            Design matrix

        successes : ndarray
            Responses (should be non-negative integers).

        trials : ndarray (optional)
            Number of trials for each success. If `None`,
            defaults to `np.ones_like(successes)`.

        offset : ndarray (optional)
            Offset to be applied in parameter space before 
            evaluating loss.

        quadratic : `regreg.identity_quadratic.identity_quadratic` (optional)
            Optional quadratic to be added to objective.

        initial : ndarray
            Initial guess at coefficients.
           
        Returns
        -------

        glm_obj : `regreg.glm.glm`
            General linear model loss.

        """

        loss = logistic_loglike(successes.shape,
                                     successes,
                                     coef=coef,
                                     trials=trials)
        return glm(X, 
                   (successes, loss.trials),
                   loss,
                   offset=offset,
                   quadratic=quadratic,
                   initial=initial)

    @staticmethod
    def poisson(X, counts,
                coef=1., 
                offset=None,
                quadratic=None, 
                initial=None):
        """
        Create a loss for a Poisson regression model.

        Parameters
        ----------

        X : [ndarray, `regreg.affine.affine_transform`]
            Design matrix

        counts : ndarray
            Response vector. Should be non-negative integers.

        offset : ndarray (optional)
            Offset to be applied in parameter space before 
            evaluating loss.

        quadratic : `regreg.identity_quadratic.identity_quadratic` (optional)
            Optional quadratic to be added to objective.

        initial : ndarray
            Initial guess at coefficients.
           
        Returns
        -------

        glm_obj : `regreg.glm.glm`
            General linear model loss.

        """
        loss = poisson_loglike(counts.shape,
                                    counts,
                                    coef=coef)
        return glm(X, counts, loss,
                   offset=offset,
                   quadratic=quadratic,
                   initial=initial)

    @staticmethod
    def huber(X, 
              response,
              smoothing_parameter,
              coef=1., 
              offset=None,
              quadratic=None, 
              initial=None):
        """
        Create a loss for a regression model using
        Huber loss.

        Parameters
        ----------

        X : [ndarray, `regreg.affine.affine_transform`]
            Design matrix

        response : ndarray
            Response vector. 

        smoothing_parameter : float
            Smoothing parameter for Huber loss.

        offset : ndarray (optional)
            Offset to be applied in parameter space before 
            evaluating loss.

        quadratic : `regreg.identity_quadratic.identity_quadratic` (optional)
            Optional quadratic to be added to objective.

        initial : ndarray
            Initial guess at coefficients.
           
        Returns
        -------

        glm_obj : `regreg.glm.glm`
            General linear model loss.

        """

        loss = huber_loss(response.shape,
                              response,
                              smoothing_parameter,
                              coef=coef)
        return glm(X, response, loss,
                   offset=offset,
                   quadratic=quadratic,
                   initial=initial)


class gaussian_loglike(smooth_atom):

    """
    The Gaussian loss for observations $y$:

    .. math::
    
       \mu \mapsto \frac{1}{2} \|y-\mu\|^2_2

    """

    objective_template = r"""\ell^{\text{Gauss}}\left(%(var)s\right)"""

    def __init__(self, 
                 shape,
                 response, 
                 coef=1., 
                 offset=None,
                 quadratic=None,
                 initial=None):

        smooth_atom.__init__(self,
                             shape,
                             offset=offset,
                             quadratic=quadratic,
                             initial=initial,
                             coef=coef)

        if sparse.issparse(response):
            self.response = response.toarray().flatten()
        else:
            self.response = np.asarray(response)

    def smooth_objective(self, natural_param, mode='both', check_feasibility=False):
        """

        Evaluate the smooth objective, computing its value, gradient or both.

        Parameters
        ----------

        natural_param : ndarray
            The current parameter values.

        mode : str
            One of ['func', 'grad', 'both']. 

        check_feasibility : bool
            If True, return `np.inf` when
            point is not feasible, i.e. when `natural_param` is not
            in the domain.

        Returns
        -------

        If `mode` is 'func' returns just the objective value 
        at `natural_param`, else if `mode` is 'grad' returns the gradient
        else returns both.
        """
        
        natural_param = self.apply_offset(natural_param)
        resid = natural_param - self.response 
        if mode == 'both':
            f, g = self.scale(np.sum(resid**2)) / 2., self.scale(resid)
            return f, g
        elif mode == 'grad':
            return self.scale(resid) 
        elif mode == 'func':
            return self.scale(np.sum(resid**2)) / 2.
        else:
            raise ValueError("mode incorrectly specified")

    # Begin loss API

    def hessian(self, natural_param):
        """
        Hessian of the loss.

        Parameters
        ----------

        natural_param : ndarray
            Parameters where Hessian will be evaluated.

        Returns
        -------

        hess : ndarray
            A 1D-array representing the diagonal of the Hessian
            evaluated at `natural_param`.
        """
        return self.scale(np.ones_like(natural_param))

    def get_data(self):
        return self.response

    def set_data(self, data):
        self.response = data

    data = property(get_data, set_data)

    # End loss API

class logistic_loglike(smooth_atom):

    """
    A class for combining the logistic log-likelihood with a general seminorm
    """

    objective_template = r"""\ell^{\text{logit}}\left(%(var)s\right)"""
    #TODO: Make init more standard, replace np.dot with shape friendly alternatives in case successes.shape is (n,1)

    def __init__(self, shape, successes, 
                 trials=None, coef=1., offset=None,
                 quadratic=None,
                 initial=None):

        smooth_atom.__init__(self,
                             shape,
                             offset=offset,
                             quadratic=quadratic,
                             initial=initial,
                             coef=coef)

        self.data = (successes, trials)

        saturated = self.successes / self.trials
        loss_terms = np.log(saturated) * self.successes + np.log(1-saturated) * (self.trials - self.successes)
        loss_constant = -coef * loss_terms[~np.isnan(loss_terms)].sum()

        devq = identity_quadratic(0,0,0,-loss_constant)
        self.quadratic += devq

    def smooth_objective(self, natural_param, mode='both', check_feasibility=False):
        """

        Evaluate the smooth objective, computing its value, gradient or both.

        Parameters
        ----------

        natural_param : ndarray
            The current parameter values.

        mode : str
            One of ['func', 'grad', 'both']. 

        check_feasibility : bool
            If True, return `np.inf` when
            point is not feasible, i.e. when `natural_param` is not
            in the domain.

        Returns
        -------

        If `mode` is 'func' returns just the objective value 
        at `natural_param`, else if `mode` is 'grad' returns the gradient
        else returns both.
        """
        
        x = natural_param # shorthand

        #Check for overflow in np.exp (can occur during initial backtracking steps)
        x = self.apply_offset(x)
        if np.max(x) > 1e2:
            overflow = True
            not_overflow_ind = np.where(x <= 1e2)[0]
            exp_x = np.exp(x[not_overflow_ind])
        else:
            overflow = False
            exp_x = np.exp(x)
            
        if mode == 'both':
            ratio = self.trials * 1.
            if overflow:
                log_exp_x = x * 1.
                log_exp_x[not_overflow_ind] = np.log(1.+exp_x)
                ratio[not_overflow_ind] *= exp_x/(1.+exp_x)
            else:
                log_exp_x = np.log(1.+exp_x)
                ratio *= exp_x/(1.+exp_x)
                
            f, g = -self.scale((np.dot(self.successes,x) - np.sum(self.trials * log_exp_x))), - self.scale(self.successes-ratio)
            return f, g
        elif mode == 'grad':
            ratio = self.trials * 1.
            if overflow:
                ratio[not_overflow_ind] *= exp_x/(1.+exp_x)
            else:
                ratio *= exp_x/(1.+exp_x)
            f, g = None, - self.scale(self.successes-ratio)
            return g
        elif mode == 'func':
            if overflow:
                log_exp_x = x * 1.
                log_exp_x[not_overflow_ind] = np.log(1.+exp_x)
            else:
                log_exp_x = np.log(1.+exp_x)
            f, g = - self.scale(np.dot(self.successes,x) - np.sum(self.trials * log_exp_x)), None
            return f
        else:
            raise ValueError("mode incorrectly specified")

    # Begin loss API

    def hessian(self, natural_param):
        """
        Hessian of the loss.

        Parameters
        ----------

        natural_param : ndarray
            Parameters where Hessian will be evaluated.

        Returns
        -------

        hess : ndarray
            A 1D-array representing the diagonal of the Hessian
            evaluated at `natural_param`.
        """

        x = natural_param # shorthand

        if np.max(x) > 1e2:
            overflow = True
            not_overflow_ind = np.where(x <= 1e2)[0]
            exp_x = np.zeros_like(x)
            exp_x[not_overflow_ind] = np.exp(x[not_overflow_ind])
            exp_x[~not_overflow_ind] = np.exp(100)
        else:
            overflow = False
            exp_x = np.exp(x)

        return self.scale(exp_x / (1 + exp_x)**2 * self.trials)

    def get_data(self):
        return self.successes, self.trials

    def set_data(self, data):
        if type(data) == type((3,)):
            successes, trials = data
        else:
            successes = data
            trials = None

        if sparse.issparse(successes):
            #Convert sparse success vector to an array
            self.successes = successes.toarray().flatten()
        else:
            self.successes = np.asarray(successes)

        if trials is None:
            if not set([0,1]).issuperset(np.unique(self.successes)):
                raise ValueError("Number of successes is not binary - must specify number of trials")
            self.trials = np.ones_like(self.successes)
        else:
            if np.min(trials-self.successes) < 0:
                raise ValueError("Number of successes greater than number of trials")
            if np.min(self.successes) < 0:
                raise ValueError("Response coded as negative number - should be non-negative number of successes")
            self.trials = trials * 1.

    data = property(get_data, set_data)

    # End loss API

class poisson_loglike(smooth_atom):

    """
    A class for combining the Poisson log-likelihood with a general seminorm
    """

    objective_template = r"""\ell^{\text{Pois}}\left(%(var)s\right)"""

    def __init__(self, shape, 
                 counts, 
                 coef=1., 
                 offset=None,
                 quadratic=None,
                 initial=None):

        smooth_atom.__init__(self,
                             shape,
                             offset=offset,
                             quadratic=quadratic,
                             initial=initial,
                             coef=coef)

        if sparse.issparse(counts):
            #Convert sparse success vector to an array
            self.counts = counts.toarray().flatten()
        else:
            self.counts = counts

        if not np.allclose(np.round(self.counts),self.counts):
            raise ValueError("Counts vector is not integer valued")
        if np.min(self.counts) < 0:
            raise ValueError("Counts vector is not non-negative")

        saturated = counts
        loss_terms = - coef * ((counts - 1) * np.log(counts))
        loss_terms[counts == 0] = 0

        loss_constant = - coef * loss_terms.sum()

        devq = identity_quadratic(0,0,0,-loss_constant)
        self.quadratic += devq

    def smooth_objective(self, natural_param, mode='both', check_feasibility=False):
        """

        Evaluate the smooth objective, computing its value, gradient or both.

        Parameters
        ----------

        natural_param : ndarray
            The current parameter values.

        mode : str
            One of ['func', 'grad', 'both']. 

        check_feasibility : bool
            If True, return `np.inf` when
            point is not feasible, i.e. when `natural_param` is not
            in the domain.

        Returns
        -------

        If `mode` is 'func' returns just the objective value 
        at `natural_param`, else if `mode` is 'grad' returns the gradient
        else returns both.
        """

        x = natural_param # shorthand

        x = self.apply_offset(x)
        exp_x = np.exp(x)
        
        if mode == 'both':
            f, g = - self.scale(-np.sum(exp_x) + np.dot(self.counts,x)), - self.scale(self.counts - exp_x)
            return f, g
        elif mode == 'grad':
            f, g = None, - self.scale(self.counts - exp_x)
            return g
        elif mode == 'func':
            f, g =  - self.scale(-np.sum(exp_x) + np.dot(self.counts,x)), None
            return f
        else:
            raise ValueError("mode incorrectly specified")

    # Begin loss API

    def hessian(self, natural_param):
        """
        Hessian of the loss.

        Parameters
        ----------

        natural_param : ndarray
            Parameters where Hessian will be evaluated.

        Returns
        -------

        hess : ndarray
            A 1D-array representing the diagonal of the Hessian
            evaluated at `natural_param`.
        """
        x = natural_param # shorthand
        return self.scale(np.exp(x))

    def get_data(self):
        return self.counts

    def set_data(self, data):
        self.counts = data

    data = property(get_data, set_data)

    # End loss API

class huber_loss(smooth_atom):

    objective_template = r"""\ell^{\text{Huber}}\left(%(var)s\right)"""

    def __init__(self, 
                 shape, 
                 response, 
                 smoothing_parameter,
                 coef=1., 
                 offset=None,
                 quadratic=None,
                 initial=None):

        smooth_atom.__init__(self,
                             shape,
                             offset=offset,
                             quadratic=quadratic,
                             initial=initial,
                             coef=coef)

        atom = l1norm(shape, lagrange=1.)
        Q = identity_quadratic(smoothing_parameter, 0, 0, 0)
        self.smoothed_atom = atom.smoothed(Q)
                                         
        if sparse.issparse(response):
            self.response = response.toarray().flatten()
        else:
            self.response = np.asarray(response)

    def smooth_objective(self, param, mode='both', check_feasibility=False):
        """

        Evaluate the smooth objective, computing its value, gradient or both.

        Parameters
        ----------

        param : ndarray
            The current parameter values.

        mode : str
            One of ['func', 'grad', 'both']. 

        check_feasibility : bool
            If True, return `np.inf` when
            point is not feasible, i.e. when `param` is not
            in the domain.

        Returns
        -------

        If `mode` is 'func' returns just the objective value 
        at `param`, else if `mode` is 'grad' returns the gradient
        else returns both.
        """
        
        x = param # shorthand

        x = self.apply_offset(x)
        resid = x - self.response 
        return self.smoothed_atom.smooth_objective(resid,
                                                   mode=mode,
                                                   check_feasibility=check_feasibility)
    # Begin loss API

    def hessian(self, param):
        """
        Hessian of the loss.

        Parameters
        ----------

        param : ndarray
            Parameters where Hessian will be evaluated.

        Returns
        -------

        hess : ndarray
            A 1D-array representing the diagonal of the Hessian
            evaluated at `natural_param`.
        """

        # it is piecwise C^2 though... maybe use this?
        raise NotImplementedError('Huber loss is not twice differentiable')

    def get_data(self):
        return self.response

    def set_data(self, data):
        self.response = data

    data = property(get_data, set_data)

    # End loss API

class multinomial_loglike(smooth_atom):

    """
    A class for baseline-category logistic regression for nominal responses (e.g. Agresti, pg 267)
    """

    objective_template = r"""\ell^{M}\left(%(var)s\right)"""

    def __init__(self, shape, counts, coef=1., offset=None,
                 initial=None,
                 quadratic=None):

        smooth_atom.__init__(self,
                             shape,
                             offset=offset,
                             quadratic=quadratic,
                             initial=initial,
                             coef=coef)

        if sparse.issparse(counts):
            #Convert sparse success vector to an array
            self.counts = counts.toarray()
        else:
            self.counts = counts

        self.J = self.counts.shape[1]
        #Select the counts for the first J-1 categories
        self.firstcounts = self.counts[:,range(self.J-1)]

        if not np.allclose(np.round(self.counts),self.counts):
            raise ValueError("Counts vector is not integer valued")
        if np.min(self.counts) < 0:
            raise ValueError("Counts vector is not non-negative")

        self.trials = np.sum(self.counts, axis=1)

        if shape[1] != self.J - 1:
            raise ValueError("Primal shape is incorrect - should only have coefficients for first J-1 categories")

        saturated = self.counts / (1. * self.trials[:,np.newaxis])
        loss_terms = np.log(saturated) * self.counts
        loss_terms[np.isnan(loss_terms)] = 0
        loss_constant = - coef * loss_terms.sum()

        devq = identity_quadratic(0,0,0,-loss_constant)
        self.quadratic += devq

    def smooth_objective(self, x, mode='both', check_feasibility=False):
        """
        Evaluate a smooth function and/or its gradient

        if mode == 'both', return both function value and gradient
        if mode == 'grad', return only the gradient
        if mode == 'func', return only the function value
        """
        x = self.apply_offset(x)
        exp_x = np.exp(x)

        #TODO: Using transposes to scale the rows of a 2d array - should we use an affine_transform to do this?
        #JT: should be able to do this with np.newaxis

        if mode == 'both':
            ratio = ((self.trials/(1. + np.sum(exp_x, axis=1))) * exp_x.T).T
            f, g = - self.scale(np.sum(self.firstcounts * x) -  np.dot(self.trials, np.log(1. + np.sum(exp_x, axis=1)))), - self.scale(self.firstcounts - ratio) 
            return f, g
        elif mode == 'grad':
            ratio = ((self.trials/(1. + np.sum(exp_x, axis=1))) * exp_x.T).T
            f, g = None, - self.scale(self.firstcounts - ratio) 
            return g
        elif mode == 'func':
            f, g = - self.scale(np.sum(self.firstcounts * x) -  np.dot(self.trials, np.log(1. + np.sum(exp_x, axis=1)))), None
            return f
        else:
            raise ValueError("mode incorrectly specified")

# is the Cox proportional hazards likelihood available?
# TODO: rewrite the Cox code to be faster -- it is very slow

try:
    from statsmodels.api import PHReg
    PHReg_available = True
except ImportError:
    warnings.warn('unable to import PHReg from statsmodels, objective function is the zero function!')
    PHReg_available = False

class coxph(glm):

    objective_template = r"""\ell^{\text{Cox}}\left(%(var)s\right)"""

    def __init__(self, 
                 X, 
                 times, 
                 status,
                 coef=1., 
                 offset=None,
                 quadratic=None,
                 initial=None):

        """
        Cox proportional hazard loss function.

        Parameters
        ----------

        X : np.float(n,p)
            Design matrix.

        times : np.float(n)
            Event times.

        status : np.bool(n)
            Censoring status.

        """

        smooth_atom.__init__(self,
                             X.shape[1],
                             offset=offset,
                             quadratic=quadratic,
                             initial=initial,
                             coef=coef)

        X = np.asarray(X)
        self.data = X, times, status

    def smooth_objective(self, beta, mode='both', check_feasibility=False):
        """

        Parameters
        ----------

        beta : ndarray
            The current parameter values.

        mode : str
            One of ['func', 'grad', 'both']. 

        check_feasibility : bool
            If True, return `np.inf` when
            point is not feasible, i.e. when `beta` is not
            in the domain.

        Returns
        -------

        If `mode` is 'func' returns just the objective value 
        at `beta`, else if `mode` is 'grad' returns the gradient
        else returns both.
        """
        
        beta = self.apply_offset(beta)

        if mode == 'both':
            if PHReg_available:
                f = - self.scale(self.model.efron_loglike(beta))
                g = - self.scale(self.model.efron_gradient(beta))
            else:
                f, g = 0., np.zeros_like(beta)
            return f, g
        elif mode == 'grad':
            if PHReg_available:
                g = - self.scale(self.model.efron_gradient(beta))
            else:
                g = np.zeros_like(beta)
            return g
        elif mode == 'func':
            if PHReg_available:
                f = - self.scale(self.model.efron_loglike(beta))
            else:
                f = 0.
            return f
        else:
            raise ValueError("mode incorrectly specified")

    def hessian(self, beta):
        """

        Compute the Hessian of the loss $ \nabla^2 \ell(X\beta)$.


        Parameters
        ----------

        beta : ndarray
            Parameters.

        Returns
        -------

        hess : ndarray
            Hessian of the loss at $\beta$, if defined.

        """
        if PHReg_available:
            beta = self.apply_offset(beta)
            return self.scale(-self.model.efron_hessian(beta))
        else:
            p = np.asarray(beta).shape[0]
            return np.zeros((p,p))

    def get_data(self):
        return self.times, self.status

    def set_data(self, data):
        X, times, status = data
        self.X, self.times, self.status = X, times, status
        self.X = X - X.mean(0)[None,:]
        if PHReg_available:
            self.model = PHReg(times, X, status=status)
        else:
            self.model = None

    data = property(get_data, set_data)

    def latexify(self, var=None, idx=''):
        # a trick to get latex representation looking right
        # coxph should be written similar to logistic
        # composed with a linear transform (TODO)
        return smooth_atom.latexify(self, var=var, idx=idx)

def logistic_loss(X, Y, trials=None, coef=1.):
    '''
    Construct a logistic loss function for successes Y and
    affine transform X.

    Parameters
    ----------

    X : [affine_transform, ndarray]
        Design matrix

    Y : ndarray

    '''
    warnings.warn('"logistic_loss" is deprecated use "regreg.smooth.glm.logistic" instead')
    return glm.logistic(X, 
                        Y,
                        trials=trials,
                        coef=coef)