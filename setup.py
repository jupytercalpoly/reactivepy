#!/usr/bin/env python

from distutils.core import setup

setup(name='reactive-kernel',
      version='0.1.0',
      description='Reactive Kernel for Jupyter',
      author='Richa Gadgil, Takahiro Shimokobe, Declan Kelly',
      url='https://github.com/jupytercalpoly/reactive-kernel',
      packages=['reactive_kernel'],
      license='BSD 3-Clause License,
      scripts=['scripts/install']'
      )
