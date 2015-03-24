'''
Created on 19.01.2015

@author: marscher
'''
from .transformer import Transformer
from pyemma.util.linalg import eig_corr
from pyemma.util.log import getLogger
from pyemma.util.annotators import doc_inherit

import numpy as np

log = getLogger('TICA')
__all__ = ['TICA']


class TICA(Transformer):

    r"""
    Time-lagged independent component analysis (TICA)

    Parameters
    ----------
    tau : int
        lag time
    output_dimension : int
        how many significant TICS to use to reduce dimension of input data
    epsilon : float
        eigenvalue norm cutoff. Eigenvalues of C0 with norms <= epsilon will be
        cut off. The remaining number of Eigenvalues define the size
        of the output.
    force_eigenvalues_le_one : boolean
        Compute covariance matrix and time-lagged covariance matrix such
        that the generalized eigenvalues are always guaranteed to be <= 1.

    Notes
    -----
    Given a sequence of multivariate data :math:`X_t`, computes the mean-free
    covariance and time-lagged covariance matrix:

    .. math::

        C_0 &=      (X_t - \mu)^T (X_t - \mu) \\
        C_{\tau} &= (X_t - \mu)^T (X_t + \tau - \mu)

    and solves the eigenvalue problem

    .. math:: C_{\tau} r_i = C_0 \lambda_i r_i

    where :math:`r_i` are the independent components and :math:`\lambda_i` are
    their respective normalized time-autocorrelations. The eigenvalues are
    related to the relaxation timescale by

    .. math:: t_i = -\tau / \ln |\lambda_i|

    When used as a dimension reduction method, the input data is projected
    onto the dominant independent components.

    """

    def __init__(self, lag, output_dimension, epsilon=1e-6, force_eigenvalues_le_one=False):
        super(TICA, self).__init__()

        # store lag time to set it appropriatly in second pass of parametrize
        self._tau = lag
        self.output_dimension = output_dimension
        self.epsilon = epsilon
        self._force_eigenvalues_le_one = force_eigenvalues_le_one

        # covariances
        self.cov = None
        self.cov_tau = None
        # mean
        self.mu = None
        self.N_mean = 0
        self.N_cov = 0
        self.N_cov_tau = 0
        self.eigenvalues = None
        self.eigenvectors = None
       
    @property
    def tau(self):
        return self._tau
    
    @tau.setter
    def tau(self,new_tau):
        self._parametrized = False
        self._tau = new_tau

    @doc_inherit
    def describe(self):
        return "[TICA, tau = %i; output dimension = %i]" \
            % (self._tau, self.output_dimension)

    def dimension(self):
        """ output dimension"""
        return self.output_dimension

    @doc_inherit
    def get_memory_per_frame(self):
        # temporaries
        dim = self.data_producer.dimension()

        mean_free_vectors = 2 * dim * self.chunksize
        dot_product = 2 * dim * self.chunksize

        return 8 * (mean_free_vectors + dot_product)

    @doc_inherit
    def get_constant_memory(self):
        dim = self.data_producer.dimension()

        # memory for covariance matrices (lagged, non-lagged)
        cov_elements = 2 * dim ** 2
        mu_elements = dim

        # TODO: shall memory req of diagonalize method go here?

        return 8 * (cov_elements + mu_elements)

    @doc_inherit
    def param_init(self):
        dim = self.data_producer.dimension()
        assert dim > 0, "zero dimension from data producer"
        assert self.output_dimension <= dim, \
            ("requested more output dimensions (%i) than dimension"
             " of input data (%i)" % (self.output_dimension, dim))

        self.N_mean = 0
        self.N_cov = 0
        self.N_cov_tau = 0
        # create mean array and covariance matrices
        self.mu = np.zeros(dim)

        self.cov = np.zeros((dim, dim))
        self.cov_tau = np.zeros_like(self.cov)

        log.info("Running TICA with tau=%i; Estimating two covariance matrices"
                 " with dimension (%i, %i)" % (self._tau, dim, dim))

    def param_add_data(self, X, itraj, t, first_chunk, last_chunk_in_traj,
                       last_chunk, ipass, Y=None):
        """
        Chunk-based parameterization of TICA. Iterates through all data twice. In the first pass, the
        data means are estimated, in the second pass the covariance and time-lagged covariance
        matrices are estimated. Finally, the generalized eigenvalue problem is solved to determine
        the independent components.

        :param X:
            coordinates. axis 0: time, axes 1-..: coordinates
        :param itraj:
            index of the current trajectory
        :param t:
            time index of first frame within trajectory
        :param first_chunk:
            boolean. True if this is the first chunk globally.
        :param last_chunk_in_traj:
            boolean. True if this is the last chunk within the trajectory.
        :param last_chunk:
            boolean. True if this is the last chunk globally.
        :param ipass:
            number of pass through data
        :param Y:
            time-lagged data (if available)
        :return:
        """
        if ipass == 0:
            # TODO: maybe use stable sum here, since small chunksizes
            # accumulate more errors
            self.mu += np.sum(X, axis=0, dtype=np.float64)
            self.N_mean += np.shape(X)[0]

            if last_chunk:
                log.debug("mean before norming:\n%s" % self.mu)
                log.debug("norming mean by %i" % self.N_mean)
                self.mu /= self.N_mean
                log.info("calculated mean:\n%s" % self.mu)

                # now we request real lagged data, since we are finished
                # with first pass
                self.lag = self._tau

        if ipass == 1:
            self.N_cov += np.shape(X)[0]
            self.N_cov_tau += np.shape(Y)[0]
            X_meanfree = X - self.mu
            Y_meanfree = Y - self.mu
            # update the time-lagged covariance matrix
            end = min(X_meanfree.shape[0],Y_meanfree.shape[0])
            self.cov_tau += np.dot(X_meanfree[0:end].T, Y_meanfree[0:end])

            # update the instantaneous covariance matrix
            self.cov += np.dot(X_meanfree.T, X_meanfree)
            
            if self._force_eigenvalues_le_one:
                start2 = max(self._tau-t, 0)
                end2   = min(self.trajectory_length(itraj)-self._tau-t, X_meanfree.shape[0])
                if start2 < X_meanfree.shape[0] and end2 > 0 and start2 < end2: 
                    self.cov += np.dot(X_meanfree[start2:end2,:].T, X_meanfree[start2:end2,:])
                    self.N_cov += (end2-start2)

            if last_chunk:
                log.info("finished calculation of Cov and Cov_tau.")
                return True  # finished!

        return False  # not finished yet.

    @doc_inherit
    def param_finish(self):
        if self._force_eigenvalues_le_one:
            # This is a bit unintuitive, for cov we include the frames that
            # we count twice in cov and N_cov during param_add_data.
            # For cov_tau, we don't and we symmetrize only in param_finish.
            # (That is we double the number of frames only in param_finish).
            # However this is mathemtically correct.
            assert self.N_cov == 2*self.N_cov_tau, 'inconsistency in C(0) and C(tau)'
        
        # norm
        self.cov /= self.N_cov - 1
        #self.cov_tau /= self.N - self.lag*(self.number_of_trajectories()-self.n_short) - 1
        self.cov_tau /= self.N_cov_tau - 1 

        # symmetrize covariance matrices
        self.cov = self.cov + self.cov.T
        self.cov /= 2.0

        self.cov_tau = self.cov_tau + self.cov_tau.T
        self.cov_tau /= 2.0

        # diagonalize with low rank approximation
        log.info("diagonalize Cov and Cov_tau")
        self.eigenvalues, self.eigenvectors = \
            eig_corr(self.cov, self.cov_tau, self.epsilon)
        log.info("finished diagonalisation.")

    def map(self, X):
        """Projects the data onto the dominant independent components.

        Parameters
        ----------
        X : ndarray(n, m)
            the input data

        Returns
        -------
        Y : ndarray(n,)
            the projected data
        """
        X_meanfree = X - self.mu
        Y = np.dot(X_meanfree, self.eigenvectors[:, 0:self.output_dimension])
        return Y