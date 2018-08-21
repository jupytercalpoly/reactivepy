#!/usr/bin/env python

from setuptools import setup
from setuptools.command.develop import develop
from setuptools.command.install import install
from setuptools import Command
import glob
import argparse
import json
import os
import sys
import shutil

kernel_json = {
    'argv': [sys.executable, '-m', 'reactivepy', '-f', '{connection_file}'],
    'display_name': 'Reactive Python',
    'language': 'python',
}


common_options = [
    ('user=', None, 'Install KernelSpec in user homedirectory'),
    ('sys-prefix=', None,
     'Install KernelSpec in sys.prefix. Useful in conda / virtualenv'),
    ('prefix=', None, 'Install KernelSpec in this prefix')
]


def install_kernel_spec(user=True, prefix=None):
    from jupyter_client.kernelspec import KernelSpecManager
    from IPython.utils.tempdir import TemporaryDirectory

    with TemporaryDirectory() as td:
        os.chmod(td, 0o755)  # Starts off as 700, not user readable
        with open(os.path.join(td, 'kernel.json'), 'w') as f:
            json.dump(kernel_json, f, sort_keys=True)
            shutil.copy2('reactivepy/images/logo-32x32.png', td)
            shutil.copy2('reactivepy/images/logo-64x64.png', td)

        # TODO: Copy any resources

        print('Installing Jupyter kernel spec to', prefix)
        KernelSpecManager().install_kernel_spec(
            td, 'reactivepy', user=user, prefix=prefix)


def _is_root():
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


HERE = os.path.realpath(os.path.dirname(__file__))


def calculate_user_prefix(options):
    user = False
    prefix = None
    if options.sys_prefix:
        prefix = options.prefix
    elif options.prefix:
        prefix = options.prefix
    elif options.user or not _is_root():
        user = True

    return (user, prefix)


class PostDevelopCommand(develop):
    """Post-installation for development mode."""

    user_options = develop.user_options + common_options

    def initialize_options(self):
        develop.initialize_options(self)
        self.user = False
        self.sys_prefix = False
        self.prefix = None

    def finalize_options(self):
        develop.finalize_options(self)

    def run(self):
        develop.run(self)

        user, prefix = calculate_user_prefix(self)
        install_kernel_spec(user=user, prefix=prefix)


class PostInstallCommand(install):
    """Post-installation for installation mode."""

    user_options = install.user_options + common_options

    def initialize_options(self):
        install.initialize_options(self)
        self.user = False
        self.sys_prefix = False
        self.prefix = None

    def finalize_options(self):
        install.finalize_options(self)

    def run(self):
        install.run(self)

        user, prefix = calculate_user_prefix(self)
        install_kernel_spec(user=user, prefix=prefix)


class CleanCommand(Command):
    """Custom clean command to tidy up the project root."""
    CLEAN_FILES = './build ./dist ./*.pyc ./*.tgz ./*.egg-info'.split(' ')

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        global HERE

        for path_spec in self.CLEAN_FILES:
            # Make paths absolute and relative to this path
            abs_paths = glob.glob(
                os.path.normpath(
                    os.path.join(
                        HERE, path_spec)))
            for path in [str(p) for p in abs_paths]:
                if not path.startswith(HERE):
                    # Die if path in CLEAN_FILES is absolute + outside this
                    # directory
                    raise ValueError(
                        "%s is not a path inside %s" %
                        (path, HERE))
                print('removing %s' % os.path.relpath(path))
                shutil.rmtree(path)


setup(name='reactivepy',
      version='0.1.0',
      description='Reactive Kernel for Jupyter',
      author='Richa Gadgil, Takahiro Shimokobe, Declan Kelly',
      author_email='dkelly.home@gmail.com',
      url='https://github.com/jupytercalpoly/reactivepy',
      packages=['reactivepy'],
      package_data={'reactivepy': ["images/*.png"]},
      license='BSD 3-Clause License',
      requires=[
          'ipython',
          'jupyter_client', 'tornado',
          'ipykernel'
      ],
      install_requires=[
          'ipython>=4.0.0',
          'jupyter_client',
          'tornado>=4.0',
          'ipykernel>=4.8'
      ],
      classifiers=[
          'Intended Audience :: Developers',
          'License :: OSI Approved :: BSD License',
          'Programming Language :: Python :: 3',
      ],
      cmdclass={
          'develop': PostDevelopCommand,
          'install': PostInstallCommand,
          'clean': CleanCommand
      },
      )
