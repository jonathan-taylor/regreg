# Support vector machine

This tutorial illustrates one version of the support vector machine, a linear
example. 
The minimization problem for the support vector machine,
following *ESL* is 
$$
\text{minimize}_{\beta,\gamma} \sum_{i=1}^n (1- y_i(x_i^T\beta+\gamma))^+ \frac{\lambda}{2} \|\beta\|^2_2
$$
We use the $C$ parameterization in (12.25) of *ESL*

$$
\text{minimize}_{\beta,\gamma} C \sum_{i=1}^n (1- y_i(x_i^T\beta+\gamma))^+ \frac{1}{2} \|\beta\|^2_2
$$
This is an example of the positive part atom combined with a smooth
quadratic penalty. Above, the $x_i$ are rows of a matrix of features
and the $y_i$ are labels coded as $\pm 1$.

Let's generate some data appropriate for this problem.

```python
import numpy as np

np.random.seed(400) # for reproducibility
N = 500
P = 2

Y = 2 * np.random.binomial(1, 0.5, size=(N,)) - 1.
X = np.random.standard_normal((N,P))
X[Y==1] += np.array([3,-2])[np.newaxis,:]
X -= X.mean(0)[np.newaxis,:]
```
We now specify the hinge loss part of the problem

```python
import regreg.api as rr
X_1 = np.hstack([X, np.ones((N,1))])
transform = rr.affine_transform(-Y[:,np.newaxis] * X_1, np.ones(N))
C = 0.2 # = 1/\lambda
hinge = rr.positive_part(N, lagrange=C)
hinge_loss = rr.linear_atom(hinge, transform)
```
and the quadratic penalty

```python
quadratic = rr.quadratic.linear(rr.selector(slice(0,P), (P+1,)), coef=0.5)
```

Now, let's solve it

```python
problem = rr.container(quadratic, hinge_loss)
solver = rr.FISTA(problem)
vals = solver.fit()
solver.composite.coefs
```

This determines a line in the plane, specified as $\beta_1 \cdot x + \beta_2 \cdot y + \gamma = 0$ and the classifications are determined by which
side of the line a point is on.

```python
fits = np.dot(X_1, problem.coefs)
labels = 2 * (fits > 0) - 1
accuracy = (1 - np.fabs(Y-labels).sum() / (2. * N))
accuracy
```

```python
import numpy as np
import regreg.api as rr

np.random.seed(400)

N = 500
P = 2

Y = 2 * np.random.binomial(1, 0.5, size=(N,)) - 1.
X = np.random.standard_normal((N,P))
X[Y==1] += np.array([3,-2])[np.newaxis,:]

X_1 = np.hstack([X, np.ones((N,1))])
X_1_signs = -Y[:,np.newaxis] * X_1
transform = rr.affine_transform(X_1_signs, np.ones(N))
C = 0.2
hinge = rr.positive_part(N, lagrange=C)
hinge_loss = rr.linear_atom(hinge, transform)

quadratic = rr.quadratic.linear(rr.selector(slice(0,P), (P+1,)), coef=0.5)
problem = rr.container(quadratic, hinge_loss)
solver = rr.FISTA(problem)
solver.fit()

import pylab
pylab.clf()
pylab.scatter(X[Y==1,0],X[Y==1,1], facecolor='red')
pylab.scatter(X[Y==-1,0],X[Y==-1,1], facecolor='blue')

fits = np.dot(X_1, problem.coefs)
labels = 2 * (fits > 0) - 1

pointX = [X[:,0].min(), X[:,0].max()]
pointY = [-(pointX[0]*problem.coefs[0]+problem.coefs[2])/problem.coefs[1],
          -(pointX[1]*problem.coefs[0]+problem.coefs[2])/problem.coefs[1]]
pylab.plot(pointX, pointY, linestyle='--', label='Separating hyperplane')
pylab.title("Accuracy = %0.1f %%" % (100-100 * np.fabs(labels - Y).sum() / (2 * N)))
#pylab.show()
```


Sparse SVM
~~~~~~~~~~

We can also fit a sparse SVM by adding a sparsity penalty to the original problem, solving the problem

$$
\text{minimize}_{\beta,\gamma} C \sum_{i=1}^n (1- y_i(x_i^T\beta+\gamma))^+ \frac{1}{2} \|\beta\|^2_2 + \lambda \|\beta\|_1
$$

Let's generate a bigger dataset

```python
N = 1000
P = 200

Y = 2 * np.random.binomial(1, 0.5, size=(N,)) - 1.
X = np.random.standard_normal((N,P))
X[Y==1] += np.array([30,-20] + (P-2)*[0])[np.newaxis,:]
X -= X.mean(0)[np.newaxis,:]
```

The hinge loss is defined similarly, and we only need to add a sparsity penalty
```python
X_1 = np.hstack([X, np.ones((N,1))])
transform = rr.affine_transform(-Y[:,np.newaxis] * X_1, np.ones(N))
C = 0.2
hinge = rr.positive_part(N, lagrange=C)
hinge_loss = rr.linear_atom(hinge, transform)

s = rr.selector(slice(0,P), (P+1,))
sparsity = rr.l1norm.linear(s, lagrange=0.2)
quadratic = rr.quadratic.linear(s, coef=0.5)
```

```python
problem = rr.container(quadratic, hinge_loss, sparsity)
solver = rr.FISTA(problem)
solver.fit()
solver.composite.coefs
```

In high dimensions, it becomes easier to separate
points.

```python
fits = np.dot(X_1, problem.coefs)
labels = 2 * (fits > 0) - 1
accuracy = (1 - np.fabs(Y-labels).sum() / (2. * N))
accuracy
```

```python
import numpy as np
import regreg.api as rr

np.random.seed(400)

N = 1000
P = 200

Y = 2 * np.random.binomial(1, 0.5, size=(N,)) - 1.
X = np.random.standard_normal((N,P))
X[Y==1] += np.array([30,-20] + (P-2)*[0])[np.newaxis,:]
X -= X.mean(0)[np.newaxis,:]

X_1 = np.hstack([X, np.ones((N,1))])
transform = rr.affine_transform(-Y[:,np.newaxis] * X_1, np.ones(N))
C = 0.2
hinge = rr.positive_part(N, lagrange=C)
hinge_loss = rr.linear_atom(hinge, transform)

s = rr.selector(slice(0,P), (P+1,))
sparsity = rr.l1norm.linear(s, lagrange=0.2)
quadratic = rr.quadratic.linear(s, coef=0.5)
problem = rr.container(quadratic, hinge_loss, sparsity)
solver = rr.FISTA(problem)
solver.debug = True
solver.fit()
solver.composite.coefs


fits = np.dot(X_1, problem.coefs)
labels = 2 * (fits > 0) - 1
accuracy = (1 - np.fabs(Y-labels).sum() / (2. * N))
print accuracy
```

Sparse Huberized SVM
~~~~~~~~~~~~~~~~~~~~

We can also smooth the hinge loss to yield a Huberized version of SVM.
In fact, it is easier to write the python code to specify the problem then
to write it out formally.

The hinge loss is defined similarly, and we only need to add a sparsity penalty

```python
X_1 = np.hstack([X, np.ones((N,1))])
transform = rr.affine_transform(-Y[:,np.newaxis] * X_1, np.ones(N))
C = 0.2
hinge = rr.positive_part(N, lagrange=C)
hinge_loss = rr.linear_atom(hinge, transform)
epsilon = 0.04
Q = rr.identity_quadratic(epsilon, 0., 0., 0.)
smoothed_hinge_loss = hinge_loss.smoothed(Q)

s = rr.selector(slice(0,P), (P+1,))
sparsity = rr.l1norm.linear(s, lagrange=0.2)
quadratic = rr.quadratic.linear(s, coef=0.5)
```

Now, let's fit it. For this problem, we can use a known bound for the Lipschitz
constant. We'll first get a bound on the largest squared singular value of X

```python
from regreg.affine import power_L
singular_value_sq = power_L(X)
# the other smooth piece is a quadratic with identity
# for quadratic form, so its lipschitz constant is 1

lipschitz = 1.05 * singular_value_sq / epsilon + 1
```

Now, we can solve the problem without having to backtrack.
```python
problem = rr.container(quadratic, 
                       smoothed_hinge_loss, sparsity)
solver = rr.FISTA(problem)
solver.composite.lipschitz = lipschitz
solver.perform_backtrack = False
vals = solver.fit()
solver.composite.coefs
```

In high dimensions, it becomes easier to separate
points.

```python
fits = np.dot(X_1, problem.coefs)
labels = 2 * (fits > 0) - 1
accuracy = (1 - np.fabs(Y-labels).sum() / (2. * N))
accuracy
```

```python
import numpy as np
import regreg.api as rr

np.random.seed(400)

N = 1000
P = 200

Y = 2 * np.random.binomial(1, 0.5, size=(N,)) - 1.
X = np.random.standard_normal((N,P))
X[Y==1] += np.array([30,-20] + (P-2)*[0])[np.newaxis,:]
X -= X.mean(0)[np.newaxis, :]

X_1 = np.hstack([X, np.ones((N,1))])
transform = rr.affine_transform(-Y[:,np.newaxis] * X_1, np.ones(N))
C = 0.2
hinge = rr.positive_part(N, lagrange=C)
hinge_loss = rr.linear_atom(hinge, transform)
epsilon = 0.04
Q = rr.identity_quadratic(epsilon, 0., 0., 0.)
smoothed_hinge_loss = hinge_loss.smoothed(Q)

s = rr.selector(slice(0,P), (P+1,))
sparsity = rr.l1norm.linear(s, lagrange=3.)
quadratic = rr.quadratic.linear(s, coef=0.5)


from regreg.affine import power_L
ltransform = rr.linear_transform(X_1)
singular_value_sq = power_L(X_1)
# the other smooth piece is a quadratic with identity
# for quadratic form, so its lipschitz constant is 1

lipschitz = 1.05 * singular_value_sq / epsilon + 1.1


problem = rr.container(quadratic, 
                       smoothed_hinge_loss, sparsity)
solver = rr.FISTA(problem)
solver.composite.lipschitz = lipschitz
solver.debug = True
solver.perform_backtrack = False
solver.fit()
solver.composite.coefs


fits = np.dot(X_1, problem.coefs)
labels = 2 * (fits > 0) - 1
accuracy = (1 - np.fabs(Y-labels).sum() / (2. * N))
print accuracy
```