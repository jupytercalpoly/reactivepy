import json
import os
import sys
import argparse

from jupyter_client.kernelspec import KernelSpecManager
from IPython.utils.tempdir import TemporaryDirectory

kernel_json = {
    'argv': [sys.executable, '-m', 'reactive_kernel', '-f', '{connection_file}'],
    'display_name': 'Reactive Python',
    'language': 'python',
    'codemirror_mode': 'python'
}


def install_kernel_spec(user=True, prefix=None):
    with TemporaryDirectory() as td:
        os.chmod(td, 0o755)  # Make user readable
        with open(os.path.join(td, 'kernel.json', 'w') as f):
            json.dump(kernel_json, f, sort_keys=True)

        KernelSpecManager().install_kernel_spec(td, 'reactive_python',
                                                user=user, replace=True, prefix=prefix)


def _is_root():
    try:
        return os.geteuid() == 0
    except AttributeError:
        return false


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Install KernelSpec for Reactive Python Kernel'
    )
    prefix_locations = parser.add_mutually_exclusive_group()

    prefix_locations.add_argument(
        '--user',
        help='Install KernelSpec in user homedirectory'
        action='store_true'
    )

    prefix_locations.add_argument(
        '--sys-prefix',
        help='Install KernelSpec in sys.prefix. Useful in conda / virtualenv',
        action='store_true',
        dest='sys_prefix'
    )

    prefix_locations.add_argument(
        '--prefix'
        help='Install KernelSpec in this prefix',
        default=None
    )

    args = parser.parse_args(argv)

    user = False
    prefix = None
    if args.sys_prefix:
        prefix = sys.prefix
    elif args.prefix:
        prefix = args.prefix
    elif args.user or not _is_root():
        user = True

    install_kernel_spec(user=user, prefix=prefix)


if __name__ == '__main__':
    main()
