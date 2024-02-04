import logging
import sys
from collections import defaultdict
from datetime import datetime
from typing import Iterable, Callable

import numpy as np
import pandas as pd

from trade_engine.strategy.order import Order
from trade_engine.strategy.streaming_orders_strategy import StreamingOrdersStrategy
from trade_engine.tickers.tick import Tick

# TODO implement the trainingsloop of a pytorch model
# Training with PyTorch — PyTorch Tutorials 2.2.0+cu121 documentation
# https://pytorch.org/tutorials/beginner/introyt/trainingyt.html

LOG = logging.getLogger(__name__)


class PyTorchModelStrategy(StreamingOrdersStrategy):

    def __init__(
            self,
            strategy_name: str,
            model,
            loss,
            optimizer,
            signal_to_order: Callable,
            features: pd.DataFrame,
            labels: pd.DataFrame = None,
            weights: pd.DataFrame = None,
            epochs: int = 1
    ):
        super().__init__(strategy=None, strategy_name=strategy_name, features=features.dropna(), labels=labels.dropna(), weights=weights, epochs=epochs)
        import torch
        self.model: torch.nn.Module = model
        self.optimizer: torch.optim.Optimizer = optimizer(model.parameters())
        self.loss_fn: torch.nn.Module = loss
        self.signal_to_order = signal_to_order

        self.best_vloss = sys.float_info.max
        # for each datapoint we have a loss, we build a timeseries for each epoch one loss column
        self.history = defaultdict(lambda: defaultdict(dict))

    def on_bar_end(
            self,
            epoch: int,
            is_training_data: bool,
            ticks: Iterable[Tick],
            features: pd.DataFrame,
            labels: pd.DataFrame = None,
            weights: pd.DataFrame = None,
    ) -> Iterable[Order] | None:
        import torch

        if not len(features) or not len(labels):
            return
        if labels.index[-1] < features.index[-1]:
            return

        # TODO allow to apply a filter i.e. not enough data

        if is_training_data:
            # Make sure gradient tracking is on, and do a pass over the data
            self.model.train(True)
            return self.train_one_batch(epoch, features, labels, weights)
        else:
            # Set the model to evaluation mode, disabling dropout and using population
            # statistics for batch normalization.
            self.model.eval()

            # Disable gradient computation and reduce memory consumption.
            with torch.no_grad():
                order = self.validate_one_batch(epoch, features, labels, weights)

            return order

    def train_one_batch(self, epoch, features, labels, weights):
        # Zero your gradients for every batch!
        self.optimizer.zero_grad()

        # Make predictions for this batch
        outputs = self.model(features)
        if outputs is None: return

        # Compute the loss and its gradients
        loss = self.loss_fn(outputs, labels)
        if loss is None: return

        if weights is not None:
            raise NotImplementedError("weights not yet implemented")

        loss.backward()

        # Adjust learning weights
        self.optimizer.step()

        # Gather data and report
        # running_loss += loss.item()
        print(epoch, "loss", loss.item())
        self.history[epoch]["loss"][features.index[-1]] = loss.item()
        return self.signal_to_order(epoch, outputs)

    def validate_one_batch(self, epoch, features, labels, weights):
        voutputs = self.model(features)
        vloss = self.loss_fn(voutputs, labels)

        if weights is not None:
            raise NotImplementedError("weights not yet implemented")

        print(epoch, "val loss", vloss.item())
        self.history[epoch]["val_loss"][features.index[-1]] = vloss.item()
        return self.signal_to_order(epoch, voutputs)

    def on_epoch_end(self, epoch: int):
        print(
            "epoch loss:",
            np.mean(np.array(list(self.history[epoch]["loss"].values()))),
            "val loss:",
            np.mean(np.array(list(self.history[epoch]["val_loss"].values()))),
        )

        # TODO update history
        """
        avg_vloss = running_vloss / (i + 1)
        LOG.info(f'LOSS train {avg_loss} valid {avg_vloss}')

        # Log the running loss averaged per batch
        # for both training and validation
        LOG.info(f'Training vs. Validation Loss Training: {avg_loss}, Validation: {avg_vloss}, {epoch + 1}')

        # Track best performance, and save the model's state
        if avg_vloss < self.best_vloss:
            self.best_vloss = avg_vloss
            # TODO save model
            # model_path = 'model_{}_{}'.format(datetime.now(), epoch_number)
            # torch.save(model.state_dict(), model_path)
        """
        pass
