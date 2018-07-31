from ipykernel.kernelapp import IPKernelApp
from . import ReactivePythonKernel

IPKernelApp.launch_instance(kernel_class=ReactivePythonKernel)
