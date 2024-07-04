'''
Hamiltonian Simulation Benchmark Program - Qiskit Kernel
(C) Quantum Economic Development Consortium (QED-C) 2024.
'''

'''
There are multiple Hamiltonians and three methods defined for this kernel.
The Hamiltonian name is specified in the "hamiltonian" argument.
The "method" argument indicates the type of fidelity comparison that will be done. 
In this case, method 3 is used to create a mirror circuit for scalability.
'''

from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
import h5py
import re
import os
import requests
import zipfile
import json
from qiskit.quantum_info import SparsePauliOp, Pauli
from qiskit.circuit import QuantumCircuit
from qiskit.circuit.library import PauliEvolutionGate


# Saved circuits and subcircuits for display
QC_ = None
QCI_ = None
HAM_ = None
EVO_ = None


from hamlib_utils import process_hamiltonian_file, needs_normalization, normalize_data_format, parse_hamiltonian_to_sparsepauliop, determine_qubit_count

def process_data(data):
    """
    Process the given data to construct a Hamiltonian in the form of a SparsePauliOp and determine the number of qubits.

    Args:
        data (str or bytes): The Hamiltonian data to be processed. Can be a string or bytes.

    Returns:
        tuple: A tuple containing the Hamiltonian as a SparsePauliOp and the number of qubits.
    """
    if needs_normalization(data) == "Yes":
        data = normalize_data_format(data)
    parsed_pauli_list = parse_hamiltonian_to_sparsepauliop(data)
    num_qubits = determine_qubit_count(parsed_pauli_list)
    hamiltonian = sparse_pauliop(parsed_pauli_list, num_qubits)
    return hamiltonian, num_qubits


def sparse_pauliop(terms, num_qubits):
    """
    Construct a SparsePauliOp from a list of Pauli terms and the number of qubits.

    Args:
        terms (list): A list of tuples, where each tuple contains a dictionary representing the Pauli operators and 
                      their corresponding qubit indices, and a complex coefficient.
        num_qubits (int): The total number of qubits.

    Returns:
        SparsePauliOp: The Hamiltonian represented as a SparsePauliOp.
    """
    pauli_list = []
    
    for pauli_dict, coefficient in terms:
        label = ['I'] * num_qubits  # Start with identity on all qubits
        for qubit, pauli_op in pauli_dict.items():
            label[qubit] = pauli_op
        label = ''.join(label)
        pauli_list.append((label, coefficient))
    
    hamiltonian = SparsePauliOp.from_list(pauli_list, num_qubits=num_qubits)
    return hamiltonian

def get_valid_qubits(min_qubits, max_qubits, skip_qubits):
    """
    Get an array of valid qubits within the specified range, removing duplicates.

    Returns:
        list: A list of valid qubits.
    """
    global dataset_name_template, filename

    # Create an array with the given min, max, and skip values
    qubit_candidates = list(range(min_qubits, max_qubits + 1, skip_qubits))
    valid_qubits_set = set()  # Use a set to avoid duplicates

    for qubits in qubit_candidates:
        initial_n_spins = qubits // 2 if "{n_qubits/2}" in dataset_name_template else qubits
        n_spins = initial_n_spins

        # print(f"Starting check for qubits = {qubits}, initial n_spins = {n_spins}")

        found_valid_dataset = False

        while n_spins <= max_qubits:
            dataset_name = dataset_name_template.replace("{n_qubits}", str(n_spins)).replace("{n_qubits/2}", str(n_spins))
            # print(f"Checking dataset: {dataset_name}")

            data = process_hamiltonian_file(filename, dataset_name)
            if data is not None:
                # print(f"Valid dataset found for n_spins = {n_spins}")
                if "{n_qubits/2}" in dataset_name_template:
                    valid_qubits_set.add(n_spins * 2)  # Add the original qubits value
                else:
                    valid_qubits_set.add(qubits)
                found_valid_dataset = True
                break
            else:
                # print(f"Dataset not available for n_spins = {n_spins}. Trying next value...")
                n_spins += 1
                if n_spins >= (qubits + skip_qubits) // 2 if "{n_qubits/2}" in dataset_name_template else (qubits + skip_qubits):
                    print(f"No valid dataset found for qubits = {qubits}")
                    break

        if found_valid_dataset:
            continue  # Move to the next candidate in the original skip sequence

    valid_qubits = list(valid_qubits_set)  # Convert set to list to remove duplicates
    valid_qubits.sort()  # Sorting the qubits for consistent order
    
    if verbose:
        print(f"Final valid qubits: {valid_qubits}")
        
    return valid_qubits  

# In hamiltonian_simulation_kernel.py

dataset_name_template = ""
filename = ""

def create_circuit(n_spins: int, time: float = 0.2, num_trotter_steps: int = 5):
    """
    Create a quantum circuit based on the Hamiltonian data from an HDF5 file.

    Steps:
        1. Extract Hamiltonian data from an HDF5 file.
        2. Process the data to obtain a SparsePauliOp and determine the number of qubits.
        3. Build a quantum circuit with an initial state and an evolution gate based on the Hamiltonian.
        4. Measure all qubits and print the circuit details.

    Returns:
        tuple: A tuple containing the constructed QuantumCircuit and the Hamiltonian as a SparsePauliOp.
    """
    global dataset_name_template, filename
    # global filename
    global QCI_

    # Replace placeholders with actual n_qubits value: n_spins
    dataset_name = dataset_name_template.replace("{n_qubits}", str(n_spins)).replace("{n_qubits/2}", str(n_spins // 2))

    if verbose:
        print(f"Trying dataset: {dataset_name}")  # Debug print

    data = process_hamiltonian_file(filename, dataset_name)
    if data is not None:
        # print(f"Using dataset: {dataset_name}")
        # print("Raw Hamiltonian Data: ", data)
        hamiltonian, num_qubits = process_data(data)

        # print("Number of qubits:", num_qubits)
        if verbose:
            print(f"... Evolution operator = {hamiltonian}")

        operator = hamiltonian  # Use the SparsePauliOp object directly

        # Build the evolution gate
        # label = "e\u2071\u1D34\u1D57"    # superscripted, but doesn't look good
        evo_label = "e^iHt"
        evo = PauliEvolutionGate(operator, time=time/num_trotter_steps, label=evo_label)

        # Plug it into a circuit
        circuit = QuantumCircuit(operator.num_qubits)
        
        # first insert the initial_state
        init_state = "checkerboard"
        QCI_ = initial_state(num_qubits, init_state)
        circuit.append(QCI_, range(operator.num_qubits))
        circuit.barrier()
        
        # Append K trotter steps
        for _ in range (num_trotter_steps):
            circuit.append(evo, range(operator.num_qubits))
        circuit.barrier()

        circuit.measure_all()
        
        # circuit.draw(output="mpl")
        # circuit.decompose(reps=2).draw(output="mpl", style="iqp")
        return circuit, hamiltonian, evo
    else:
        # print(f"Dataset not available for n_spins = {n_spins}.")
        return None, None, None


############### Circuit Definition

def initial_state(n_spins: int, initial_state: str = "checker") -> QuantumCircuit:
    """
    Initialize the quantum state.
    
    Args:
        n_spins (int): Number of spins (qubits).
        initial_state (str): The chosen initial state. By default applies the checkerboard state, but can also be set to "ghz", the GHZ state.

    Returns:
        QuantumCircuit: The initialized quantum circuit.
    """
    qc = QuantumCircuit(n_spins)

    if initial_state.strip().lower() == "checkerboard" or initial_state.strip().lower() == "neele":
        # Checkerboard state, or "Neele" state
        qc.name = "Neele"
        for k in range(0, n_spins, 2):
            qc.x([k])
    elif initial_state.strip().lower() == "ghz":
        # GHZ state: 1/sqrt(2) (|00...> + |11...>)
        qc.name = "GHZ"
        qc.h(0)
        for k in range(1, n_spins):
            qc.cx(k-1, k)

    return qc


def HamiltonianSimulation(n_spins: int, K: int, t: float,
            hamiltonian: str, w: float, hx: list[float], hz: list[float],
            use_XX_YY_ZZ_gates: bool = False,
            method: int = 1) -> QuantumCircuit:
    """
    Construct a Qiskit circuit for Hamiltonian simulation.

    Args:
        n_spins (int): Number of spins (qubits).
        K (int): The Trotterization order.
        t (float): Duration of simulation.
        hamiltonian (str): Which hamiltonian to run. "heisenberg" by default but can also choose "TFIM". 
        w (float): Strength of two-qubit interactions for heisenberg hamiltonian. 
        hx (list[float]): Strength of internal disorder parameter for heisenberg hamiltonian. 
        hz (list[float]): Strength of internal disorder parameter for heisenberg hamiltonian. 

    Returns:
        QuantumCircuit: The constructed Qiskit circuit.
    """
    
    num_qubits = n_spins
    secret_int = f"{K}-{t}"

    # Allocate qubits
    qr = QuantumRegister(n_spins)
    cr = ClassicalRegister(n_spins)
    qc = QuantumCircuit(qr, cr, name=f"hamsim-{num_qubits}-{secret_int}")
    tau = t / K

    h_x = hx[:n_spins]
    h_z = hz[:n_spins]

    hamiltonian = hamiltonian.strip().lower()
    
    if hamiltonian == "hamlib":
        qc, ham_op, evo = create_circuit(n_spins)

    else:
        raise ValueError("Invalid Hamiltonian specification.")

    # Measure all qubits
    # for i_qubit in range(n_spins):
    #     qc.measure(qr[i_qubit], cr[i_qubit])

    # Save smaller circuit example for display
    global QC_, HAM_, EVO_
    if QC_ is None or n_spins <= 6:
        if n_spins < 9:
            QC_ = qc
            HAM_ = ham_op
            EVO_ = evo
            
    # Collapse the sub-circuits used in this benchmark (for Qiskit)
    qc2 = qc.decompose().decompose()
            
    return qc2
    
    
############### Circuit Drawer

# Draw the circuits of this benchmark program
def kernel_draw(hamiltonian: str = "heisenberg", use_XX_YY_ZZ_gates: bool = False, method: int = 1):
                          
    # Print a sample circuit
    print("Sample Circuit:")
    if QC_ is not None:
        print(f"  H = {HAM_}")
        print(QC_)
        
        # create a small circuit, just to display this evolution subciruit structure
        print("  Evolution Operator (e^iHt) =")
        qctt = QuantumCircuit(QC_.num_qubits)
        qctt.append(EVO_, range(QC_.num_qubits))
        print(transpile(qctt, optimization_level=3))
               
        if QCI_ is not None:
            print(f"  Initial State {QCI_.name}:")
            print(QCI_)
    
    else:
        print("  ... circuit too large!")


    