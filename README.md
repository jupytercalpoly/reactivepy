# reactivepy

A reactive Python kernel.

# Dependencies

- `ipython>=4.0.0`
- `jupyter_client`
- `tornado>=4.0`
- `ipykernel>=4.8`

# Install

```bash
git clone https://github.com/jupytercalpoly/reactivepy.git

# install dependencies

pip install .
```

# Develop

```bash
git clone https://github.com/jupytercalpoly/reactivepy.git

# install dependencies

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
