"""Rocket Mission Lab: educational six degree-of-freedom simulation."""
import os
# Bound BLAS pools before NumPy/SciPy load, including subprocess entry points.
# Otherwise several training/evaluation processes can each spawn dozens of threads.
for _name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[_name]="2"
