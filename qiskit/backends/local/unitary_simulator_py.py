# -*- coding: utf-8 -*-

# Copyright 2017, IBM.
#
# This source code is licensed under the Apache License, Version 2.0 found in
# the LICENSE.txt file in the root directory of this source tree.

"""Contains a (slow) Python simulator that returns the unitary of the circuit.

It simulates a unitary of a quantum circuit that has been compiled to run on
the simulator. It is exponential in the number of qubits.

The input is the circuit object and the output is the same circuit object with
a result field added results['data']['unitary'] where the unitary is
a 2**n x 2**n complex numpy array representing the unitary matrix.


The input is

    compiled_circuit object

and the output is the results object

The simulator is run using

    UnitarySimulatorPy(compiled_circuit).run().

In the qasm, key operations with type 'measure' and 'reset' are dropped.

Internal circuit_object::

    compiled_circuit =
    {
     "header": {
     "number_of_qubits": 2, // int
     "number_of_clbits": 2, // int
     "qubit_labels": [["q", 0], ["v", 0]], // list[list[string, int]]
     "clbit_labels": [["c", 2]], // list[list[string, int]]
     }
     "operations": // list[map]
        [
            {
                "name": , // required -- string
                "params": , // optional -- list[double]
                "qubits": , // required -- list[int]
                "clbits": , //optional -- list[int]
                "conditional":  // optional -- map
                    {
                        "type": , // string
                        "mask": , // hex string
                        "val":  , // bhex string
                    }
            },
        ]
    }

returned results object::

    result =
            {
            'data':
                {
                'unitary': np.array([[ 0.70710678 +0.00000000e+00j
                                     0.70710678 -8.65956056e-17j
                                     0.00000000 +0.00000000e+00j
                                     0.00000000 +0.00000000e+00j]
                                   [ 0.00000000 +0.00000000e+00j
                                     0.00000000 +0.00000000e+00j
                                     0.70710678 +0.00000000e+00j
                                     -0.70710678 +8.65956056e-17j]
                                   [ 0.00000000 +0.00000000e+00j
                                     0.00000000 +0.00000000e+00j
                                     0.70710678 +0.00000000e+00j
                                     0.70710678 -8.65956056e-17j]
                                   [ 0.70710678 +0.00000000e+00j
                                    -0.70710678 +8.65956056e-17j
                                     0.00000000 +0.00000000e+00j
                                     0.00000000 +0.00000000e+00j]
                }
            'state': 'DONE'
            }
"""
import logging
import uuid

import numpy as np

from qiskit._result import Result
from qiskit.backends import BaseBackend
from qiskit.backends.local.localjob import LocalJob
from qiskit.qobj import qobj_to_dict
from ._simulatortools import enlarge_single_opt, enlarge_two_opt, single_gate_matrix

logger = logging.getLogger(__name__)


# TODO add ["status"] = 'DONE', 'ERROR' especitally for empty circuit error
# does not show up


class UnitarySimulatorPy(BaseBackend):
    """Python implementation of a unitary simulator."""

    DEFAULT_CONFIGURATION = {
        'name': 'local_unitary_simulator_py',
        'url': 'https://github.com/QISKit/qiskit-terra',
        'simulator': True,
        'local': True,
        'description': 'A python simulator for unitary matrix',
        'coupling_map': 'all-to-all',
        'basis_gates': 'u1,u2,u3,cx,id'
    }

    def __init__(self, configuration=None):
        """Initialize the UnitarySimulatorPy object.
        """
        super().__init__(configuration or self.DEFAULT_CONFIGURATION.copy())

        # Define attributes inside __init__.
        self._unitary_state = None
        self._number_of_qubits = 0

    def _add_unitary_single(self, gate, qubit):
        """Apply the single-qubit gate.

        gate is the single-qubit gate.
        qubit is the qubit to apply it on counts from 0 and order
            is q_{n-1} ... otimes q_1 otimes q_0.
        number_of_qubits is the number of qubits in the system.
        """
        unitaty_add = enlarge_single_opt(gate, qubit, self._number_of_qubits)
        self._unitary_state = np.dot(unitaty_add, self._unitary_state)

    def _add_unitary_two(self, gate, q_0, q_1):
        """Apply the two-qubit gate.

        gate is the two-qubit gate
        q0 is the first qubit (control) counts from 0
        q1 is the second qubit (target)
        returns a complex numpy array
        """
        unitaty_add = enlarge_two_opt(gate, q_0, q_1, self._number_of_qubits)
        self._unitary_state = np.dot(unitaty_add, self._unitary_state)

    def run(self, qobj):
        """Run qobj asynchronously.

        Args:
            qobj (dict): job description

        Returns:
            LocalJob: derived from BaseJob
        """
        return LocalJob(self._run_job, qobj)

    def _run_job(self, qobj):
        """Run qobj. This is a blocking call.

        Args:
            qobj (Qobj): job description
        Returns:
            Result: Result object
        """
        result_list = []
        qobj_converted = qobj_to_dict(qobj, version='0.0.1')
        for circuit in qobj_converted['circuits']:
            result_list.append(self.run_circuit(circuit))
        job_id = str(uuid.uuid4())
        return Result(
            {'job_id': job_id, 'result': result_list, 'status': 'COMPLETED'})

    def run_circuit(self, circuit):
        """Apply the single-qubit gate."""
        ccircuit = circuit['compiled_circuit']
        self._number_of_qubits = ccircuit['header']['number_of_qubits']
        result = {}
        result['data'] = {}
        result['name'] = circuit.get('name')
        self._unitary_state = np.identity(2**(self._number_of_qubits),
                                          dtype=complex)
        for operation in ccircuit['operations']:
            if operation['name'] in ['U', 'u1', 'u2', 'u3']:
                if 'params' in operation:
                    params = operation['params']
                else:
                    params = None
                qubit = operation['qubits'][0]
                gate = single_gate_matrix(operation['name'], params)
                self._add_unitary_single(gate, qubit)
            elif operation['name'] in ['id', 'u0']:
                pass
            elif operation['name'] in ['CX', 'cx']:
                qubit0 = operation['qubits'][0]
                qubit1 = operation['qubits'][1]
                gate = np.array([[1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0],
                                 [0, 1, 0, 0]])
                self._add_unitary_two(gate, qubit0, qubit1)
            elif operation['name'] == 'measure':
                logger.info('Warning have dropped measure from unitary '
                            'simulator')
            elif operation['name'] == 'reset':
                logger.info('Warning have dropped reset from unitary '
                            'simulator')
            elif operation['name'] == 'barrier':
                pass
            else:
                result['status'] = 'ERROR'
                return result
        result['data']['unitary'] = self._unitary_state
        result['status'] = 'DONE'
        return result
