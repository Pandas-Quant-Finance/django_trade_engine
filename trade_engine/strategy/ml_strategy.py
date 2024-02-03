import logging
import sys
from datetime import datetime
from typing import Iterable

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
        self.best_vloss = sys.float_info.max
        # for each datapoint we have a loss, we build a timeseries for each epoch one loss column
        self.history = {}

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

        # TODO allow to apply a filter i.e. not enough data

        if is_training_data:
            # Make sure gradient tracking is on, and do a pass over the data
            self.model.train(True)
            self.train_one_batch(epoch, features, labels, weights)
            # TODO we need something to convert the predictions to orders
        else:
            # Set the model to evaluation mode, disabling dropout and using population
            # statistics for batch normalization.
            self.model.eval()

            # Disable gradient computation and reduce memory consumption.
            with torch.no_grad():
                self.validate_one_batch(epoch, features, labels, weights)
                # TODO we need something to convert the predictions to orders

        # FIXME return an order
        return None

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

    def validate_one_batch(self, epoch, features, labels, weights):

        voutputs = self.model(features)
        vloss = self.loss_fn(voutputs, labels)

        if weights is not None:
            raise NotImplementedError("weights not yet implemented")

        print(epoch, "val loss", vloss.item())

    def on_epoch_end(self):
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