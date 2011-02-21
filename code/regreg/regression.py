import numpy as np

class Regression(object):

    def __init__(self, problem):
        self.problem = problem

    @property
    def output(self):
        """
        Return the 'interesting' part of the problem arguments.
        In the regression case, this is the tuple (beta, r).
        """
        return self.problem.output

    def fit(self):
        """
        Abstract method.
        """
        raise NotImplementedError

class ISTA(Regression):

    debug = False
    inv_step = None
    def fit(self,tol=1e-4,max_its=100,min_its=5,backtrack=True,alpha=1.1,start_inv_step=1.):

        objective_hist = np.zeros(max_its)
        itercount = 0
        obj_cur = np.inf
        if self.inv_step is None:
            self.inv_step = start_inv_step
        while itercount < max_its:
            f_beta = self.problem.obj(self.problem.coefs)
            grad = self.problem.grad(self.problem.coefs)
            objective_hist[itercount] = f_beta
            # Backtracking loop
            if backtrack:
                current_f = self.problem.obj_smooth(self.problem.coefs)
                stop = False
                while not stop:
                    beta = self.problem.proximal(self.problem.coefs, grad, self.inv_step)
                    trial_f = self.problem.obj_smooth(beta)
                    if np.fabs(trial_f - current_f)/trial_f > 1e-10:
                        stop = trial_f <= current_f + np.dot(beta-self.problem.coefs,grad) + 0.5*self.inv_step*np.linalg.norm(beta-self.problem.coefs)**2
                    else:
                        trial_grad = self.problem.grad(beta)
                        stop = np.fabs(np.dot(beta-self.problem.coefs,grad-trial_grad)) <= 0.5*self.inv_step*np.linalg.norm(beta-self.problem.coefs)**2
                    if not stop:
                        self.inv_step *= alpha
            else:
                self.inv_step = self.problem.L
                beta = self.problem.proximal(self.problem.coefs, grad, self.inv_step)

            if self.debug:
                print itercount, obj_cur, self.inv_step, (obj_cur - f_beta) / f_beta, np.linalg.norm(self.problem.coefs - beta) / np.max([1.,np.linalg.norm(beta)])


            if np.linalg.norm(self.problem.coefs - beta) / np.max([1.,np.linalg.norm(beta)]) < tol and itercount >= min_its:
            #if np.fabs((obj_cur - f_beta) / f_beta) < tol and itercount >= min_its:
                self.problem.coefs = beta
                break
            self.problem.coefs = beta
            obj_cur = self.problem.obj(self.problem.coefs)
            

            itercount += 1
        if self.debug:
            print "ISTA used", itercount, "iterations"
        return objective_hist

class FISTA(Regression):

    debug = False
    inv_step = None
    def fit(self,max_its=100,tol=1e-5,min_its=5,backtrack=True,alpha=1.1,start_inv_step=1.,restart=np.inf):

        objective_hist = np.zeros(max_its)
        f = self.problem.obj
        r = self.problem.coefs
        t_old = 1.
        
        obj_cur = np.inf
        itercount = 0
        if self.inv_step is None:
            self.inv_step = start_inv_step
        beta = self.problem.coefs
        while itercount < max_its:
            if np.mod(itercount+1,restart)==0:
                print "Restarting"
                r = self.problem.coefs
                t_old = 1.
                self.inv_step *= 0.5            
            f_beta = f(self.problem.coefs)
            #if self.debug:
            #    print itercount, obj_cur, inv_step, (obj_cur - f_beta) / f_beta, np.linalg.norm(self.problem.coefs - beta) / np.max([1.,np.linalg.norm(beta)])
            
            #if np.fabs((obj_cur - f_beta) / f_beta) < tol and itercount >= min_its:
            #    break
            obj_cur = f_beta
            objective_hist[itercount] = obj_cur
            grad = self.problem.grad(r)
            # Backtracking loop
            if backtrack:
                current_f = self.problem.obj_smooth(r)
                stop = False
                while not stop:
                    beta = self.problem.proximal(r, grad, self.inv_step)
                    trial_f = self.problem.obj_smooth(beta)
                    if np.fabs(trial_f - current_f)/trial_f > 1e-10:
                        stop = trial_f <= current_f + np.dot(beta-r,grad) + 0.5*self.inv_step*np.linalg.norm(beta-r)**2
                    else:
                        trial_grad = self.problem.grad(beta)
                        stop = np.fabs(np.dot(beta-r,grad-trial_grad)) <= 0.5*self.inv_step*np.linalg.norm(beta-r)**2
                    if not stop:
                        self.inv_step *= alpha
            else:
                self.inv_step = self.problem.L
                beta = self.problem.proximal(r, grad, self.inv_step)

            if self.debug:
                print itercount, obj_cur, self.inv_step, (obj_cur - f_beta) / f_beta, np.linalg.norm(self.problem.coefs - beta) / np.max([1.,np.linalg.norm(beta)])

            if np.linalg.norm(self.problem.coefs - beta) / np.max([1.,np.linalg.norm(beta)]) < tol and itercount >= min_its:
                self.problem.coefs = beta
                break

            t_new = 0.5 * (1 + np.sqrt(1+4*(t_old**2)))
            r = beta + ((t_old-1)/(t_new)) * (beta - self.problem.coefs)
            self.problem.coefs = beta
            t_old = t_new
            itercount += 1

        if self.debug:
            print "FISTA used", itercount, "iterations"
        return objective_hist
class NesterovSmooth(Regression):
    
    def fit(self,tol=1e-4,epsilon=0.1,max_its=100):
        import nesterov_smooth
        p = len(self.problem.coefs)
        grad_s, L_s, f_s = self.problem.smooth(self.problem.L, epsilon)
        self.problem.coefs, l = nesterov_smooth.loop(self.problem.coefs, grad_s, L_s, f=f_s, maxiter=max_its, values=True, tol=tol)
        return f_s


import subfunctions as sf
class CWPath(Regression):

    debug = False
    def __init__(self, problem, **kwargs):
        self.problem = problem
            
    def fit(self,tol=1e-4,inner_its=50,max_its=2000,min_its=5):
        
        active = np.arange(self.problem.coefs.shape[0])
        itercount = 0
        stop = False
        while not stop and itercount < max_its:
            bold = self.output
            nonzero = []
            self.problem.update_cwpath(active,nonzero,1,update_nonzero=True)
            if itercount > min_its:
                stop, worst = self.stop(bold,tol=tol,return_worst=True)
                if np.mod(itercount,40)==0 and self.debug:
                    print "Fit iteration", itercount, "with max. relative change", worst
            self.problem.update_cwpath(np.unique(nonzero),nonzero,inner_its)
            itercount += 1

    def stop(self,
             previous,
             tol=1e-4,
             return_worst = False):
        """
        Convergence check: check whether 
        residuals have not significantly changed or
        they are small enough.

        Both old and current are expected to be (beta, r) tuples, i.e.
        regression coefficent and residual tuples.
    
        """

        bold, _ = previous
        bcurrent, _ = self.output

        if return_worst:
            status, worst = sf.coefficientCheckVal(bold, bcurrent, tol)
            if status:
                return True, worst
            return False, worst
        else:
            status = sf.coefficientCheck(bold, bcurrent, tol)
            if status:
                return True
            return False

class Direct(Regression):
    #XXX for PMD problems
    def fit(self,tol=1e-4):
        self.problem.update_direct()
