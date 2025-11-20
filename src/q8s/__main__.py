from ipykernel.kernelapp import IPKernelApp

from . import Q8sKernel

IPKernelApp.launch_instance(kernel_class=Q8sKernel)
