# -*- coding: utf-8 -*-

import numpy as np
from functools import lru_cache, partial

from ..base import Property
from .base import Predictor
from ..types.prediction import InformationStatePrediction
from ..types.update import InformationStateUpdate # To check incoming "prior" data
from ..types.state import InformationState # To check incoming "prior" data
from ..models.base import LinearModel
from ..models.transition import TransitionModel
from ..models.transition.linear import LinearGaussianTransitionModel
from ..models.control import ControlModel
from ..models.control.linear import LinearControlModel
from ..functions import gauss2sigma, unscented_transform
from numpy.linalg import inv


class InfoFilterPredictor(Predictor):
    r"""A predictor class which forms the basis of the information filter. Here

    .. math::

      f_k( \mathbf{x}_{k-1}) = F_k \mathbf{x}_{k-1},  \ b_k( \mathbf{x}_k) =
      B_k \mathbf{x}_k \ \mathrm{and} \ \mathbf{\nu}_k \sim \mathcal{N}(0,Q_k)
        y_{k|k-1} = [1 = \Omega_k G^T_k] F^{-T}_k y_{k-1|k-1} + Y_{k|k-1} B_k u_k

    Notes
    -----
    In the Information filter (similar to the Kalman filter), transition and control models must be
     linear. Accepts both InformationStateUpdate and GaussianStateUpdate


    Raises
    ------
    ValueError
        If no :class:`~.TransitionModel` is specified.


    """

    transition_model = Property(
        LinearGaussianTransitionModel,
        doc="The transition model to be used.")
    control_model = Property(
        LinearControlModel,
        default=None,
        doc="The control model to be used. Default `None` where the predictor "
            "will create a zero-effect linear :class:`~.ControlModel`.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # If no control model insert a linear zero-effect one
        # TODO: Think about whether it's more efficient to leave this out
        if self.control_model is None:
            ndims = self.transition_model.ndim_state
            self.control_model = LinearControlModel(ndims, [],
                                                    np.zeros([ndims, 1]),
                                                    np.zeros([ndims, ndims]),
                                                    np.zeros([ndims, ndims]))

    def _noise_transition_matrix(self, **kwargs):
        """Return the noise transition matrix

        Parameters
        ----------
        **kwargs : various, optional
            These are passed to :meth:`~.LinearGaussianTransitionModel.matrix`

        Returns
        -------
        : :class:`numpy.ndarray`
            The noise transition matrix, :math:`G`

        """
        return np.identity(self.transition_model.ndim_state)



    def _transition_matrix(self, **kwargs):
        """Return the transition matrix

        Parameters
        ----------
        **kwargs : various, optional
            These are passed to :meth:`~.LinearGaussianTransitionModel.matrix`

        Returns
        -------
        : :class:`numpy.ndarray`
            The transition matrix, :math:`F_k`

        """
        return self.transition_model.matrix(**kwargs)

    def _transition_function(self, prior, **kwargs):
        r"""Applies the linear transition function to a single vector in the
        absence of a control input, returns a single predicted state.

        Parameters
        ----------
        prior : :class:`~.State`
            The prior state, :math:`\mathbf{x}_{k-1}`

        **kwargs : various, optional
            These are passed to :meth:`~.LinearGaussianTransitionModel.matrix`

        Returns
        -------
        : :class:`~.State`
            The predicted state

        """
        return self.transition_model.matrix(**kwargs) @ prior.state_vector

    @property
    def _control_matrix(self):
        r"""Convenience function which returns the control matrix

        Returns
        -------
        : :class:`numpy.ndarray`
            control matrix, :math:`B_k`

        """
        return self.control_model.matrix()

    def _predict_over_interval(self, prior, timestamp):
        """Private function to get the prediction interval (or None)

        Parameters
        ----------
        prior : :class:`~.State`
            The prior state

        timestamp : :class:`datetime.datetime`, optional
            The (current) timestamp

        Returns
        -------
        : :class:`datetime.timedelta`
            time interval to predict over

        """

        # Deal with undefined timestamps
        if timestamp is None or prior.timestamp is None:
            predict_over_interval = None
        else:
            predict_over_interval = timestamp - prior.timestamp

        return predict_over_interval

    @lru_cache()
    def predict(self, prior, timestamp=None, **kwargs):
        r"""The predict function

        Parameters
        ----------
        prior : :class:`~.State`
            :math:`\mathbf{x}_{k-1}`
        timestamp : :class:`datetime.datetime`, optional
            :math:`k`
        **kwargs :
            These are passed, via :meth:`~.KalmanFilter.transition_function` to
            :meth:`~.LinearGaussianTransitionModel.matrix`

        Returns
        -------
        : :class:`~.State`
            :math:`\mathbf{x}_{k|k-1}`, the predicted state and the predicted
            state covariance :math:`P_{k|k-1}`

        """

        # Get the prediction interval
        predict_over_interval = self._predict_over_interval(prior, timestamp)

        # Prediction of the mean
        x_pred = self._transition_function(
            prior, time_interval=predict_over_interval, **kwargs) \
            + self.control_model.control_input()

        # As this is Kalman-like, the control model must be capable of
        # returning a control matrix (B)

        transition_matrix = self._transition_matrix(
            prior=prior, time_interval=predict_over_interval, **kwargs)
        transition_covar = self.transition_model.covar(
            time_interval=predict_over_interval, **kwargs)

        control_matrix = self._control_matrix
        control_noise = self.control_model.control_noise

        print(prior)

        if isinstance(prior, InformationStateUpdate) or isinstance(prior, InformationStatePrediction) or isinstance(prior, InformationState):
            p_pred = transition_matrix @ prior.info_matrix @ transition_matrix.T \
                + transition_covar \
                + control_matrix @ control_noise @ control_matrix.T
        else:
            p_pred = transition_matrix @ prior.covar @ transition_matrix.T \
                     + transition_covar \
                     + control_matrix @ control_noise @ control_matrix.T

        ndims = self.transition_model.ndim

        G = self._noise_transition_matrix()
        F = transition_matrix
        Q = transition_covar # transition covar - not sure about this though
        if isinstance(prior, InformationStateUpdate) or isinstance(prior, InformationStatePrediction) or isinstance(prior, InformationState):
            Y = prior.info_matrix # fisher information (I think?)
        else:
            Y = prior.covar

        M = inv(transition_matrix.T) @ Y @ inv(transition_matrix) # Eq 252

        Sigma = G @ M @ G + inv(transition_covar) # Eq 254

        Omega = M @ G @ inv(Sigma) # Eq 253

        Y_pred = M - Omega @ Sigma @ Omega.T # Eq 251

        # Get the information state
        y = prior.state_vector

        y_pred = (np.ones((ndims, ndims)) - Omega @ G.transpose()) @ inv(F.transpose()) @ y \
            + Y @ self.control_model.control_input()

        return InformationStatePrediction(y_pred, Y_pred, timestamp=timestamp)