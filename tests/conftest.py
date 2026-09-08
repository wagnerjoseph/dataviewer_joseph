"""Test fixtures for dataviewer_joseph."""

import shutil
import tempfile
from pathlib import Path

import pytest

from dataviewer_joseph.config import DataConfig
from dataviewer_joseph.data import generate_dummy_data


@pytest.fixture
def temp_data_dir() -> Path:
    """Create a temporary directory with dummy data."""
    tmpdir = Path(tempfile.mkdtemp())
    generate_dummy_data(tmpdir, n_locations=50, n_tiles=2, seed=42)
    yield tmpdir
    shutil.rmtree(tmpdir)


@pytest.fixture
def data_config(temp_data_dir: Path) -> DataConfig:
    """Create a DataConfig pointing to temporary test data."""
    return DataConfig(root=temp_data_dir)


@pytest.fixture
def small_data_config() -> DataConfig:
    """Create a DataConfig with minimal dummy data."""
    tmpdir = Path(tempfile.mkdtemp())
    generate_dummy_data(tmpdir, n_locations=10, n_tiles=1, seed=42)
    config = DataConfig(root=tmpdir)
    yield config
    shutil.rmtree(tmpdir)
