# reactivepy

[![Binder](https://beta.mybinder.org/badge.svg)](https://mybinder.org/v2/gh/jupytercalpoly/reactivepy/master?urlpath=lab/tree/examples/BasicAsyncGenerators.ipynb)

A reactive Python kernel. Whenever a variable value is changed, the kernel automatically executes its dependencies (any cells which use that variable) with the updated value. As of now, reactivepy can also support asynchronous functions. 

Each notebook cell for a reactive kernel contains a single definition of a
variable, function, or class. 

When a cell is run, the kernel conducts
static analysis to automatically extract and run dependencies -- saving
users the trouble of remembering dependencies and re-running individual
cells.


# Dependencies

- `ipython>=4.0.0`
- `jupyter_client`
- `tornado>=4.0`
- `ipykernel>=4.8`

# Install

```bash
git clone https://github.com/jupytercalpoly/reactivepy.git

# install dependencies
`Python 3.6` or above.

pip install .
```

# Develop

```bash
git clone https://github.com/jupytercalpoly/reactivepy.git

# install dependencies
`Python 3.6` or above.

pip install -e .
```

# TODO

- Move execution out of a queue, this will allow executions to interleave
- Support deleting unnamed nodes (nodes which do not export any variables). This will reduce space usage and reduce unnecessary computation
- Fix error with being unable to define a node after initially erroring out while creating it

# Testing

## Requirements

Install `pytest` and `pytest-asyncio` using `conda` or `pip`:

```bash
conda install pytest pytest-asyncio
```

Then run

```bash
pytest .
```
