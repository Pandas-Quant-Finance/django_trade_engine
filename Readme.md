# Django Trade Engine

## Motivation
Backtesting and putting a trading strategy live should be the same thing. This means backtesting needs to mimic the 
whole flow: 

 `feed a new price event into the model (stragegy) -> retrieve a signal -> place an order -> get a trade execution -> update the portfolio`  

The only difference between backtesting and having the strategy live is that we don't send the orders to a real broker.
As a consequence we have to implement the order handling (orderbook) for different use cases and brokers.

This also means we have full control over all order during backtesting. We can place orders, cancel orders and use
limit orders as well as stop limit orders. Theoretically we could implement trailing stops and if done order types as well.  


#### Debugging
keep a database after a test completed:
 * inherit from django.test.SimpleTestCase
 * in settings.py define test db file path: `DATABASES.default.TEST`
 * use --keepdb flag: `./manage.py test trade_engine.tests.test_strategy.test_upfront_orders_strategy.TestUpfrontOrderStrategy.test_sma_strategy --keepdb`
