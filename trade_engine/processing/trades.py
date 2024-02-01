import logging

from django.db import transaction

from .. import models

log = logging.getLogger(__name__)


@transaction.atomic()
def save_trades(*trades: models.Trade, silent: bool = False):
    try:
        for t in trades:
            t.save()
    except Exception as e:
        if not silent:
            raise e

        log.warning(f"failed to save trades {trades}: {e}")
