# -*- coding: utf-8 -*-

from ..base import Property
from .array import StateVector
from .base import Type


class Particle(Type):
    """
    Particle type

    A particle type which contains a state and weight
    """
    state_vector: StateVector = Property(doc="State vector")
    weight: float = Property(doc='Weight of particle')
    parent: 'Particle' = Property(default=None, doc='Parent particle')

    def __init__(self, state_vector, weight, parent=None, *args, **kwargs):
        if parent:
            parent.parent = None
        if state_vector is not None and not isinstance(state_vector, StateVector):
            state_vector = StateVector(state_vector)
        super().__init__(state_vector, weight, parent, *args, **kwargs)

    @property
    def ndim(self):
        return self.state_vector.shape[0]


class MultiModelParticle(Type):
    """
    Particle type

    A MultiModelParticle type which contains a state, weight and the dynamic_model
    """
    state_vector: StateVector = Property(doc="State vector")
    weight: float = Property(doc='Weight of particle')
    parent: 'MultiModelParticle' = Property(default=None, doc='Parent particle')
    dynamic_model: int = Property(doc='Assigned dynamic model')

    def __init__(self, state_vector, weight, dynamic_model, parent=None, *args, **kwargs):
        if parent:
            parent.parent = None

        if state_vector is not None and not isinstance(state_vector, StateVector):
            state_vector = StateVector(state_vector)
        super().__init__(state_vector, weight, dynamic_model, parent, *args, **kwargs)

    @property
    def ndim(self):
        return self.state_vector.shape[0]
