import pandas as pd
from pathlib import Path

symbols = ["aapl", "msft", "tlt"]

SAMPLE_DATA = pd.concat(
    [pd.read_csv(Path(__file__).parent.joinpath(f"{file}.csv"), parse_dates=True, index_col='Date') for file in symbols],
    axis=1,
    keys=symbols
)
