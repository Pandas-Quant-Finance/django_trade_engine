# define signals
import django.dispatch

tick = django.dispatch.Signal()
position_updated = django.dispatch.Signal()
trade_executed = django.dispatch.Signal()
