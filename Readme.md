# Django Trade Engine

## Motivation
Backtesting and putting a trading strategy live should be the same thing. This means backtesting needs to mimic the 
whole flow: 

 `feed a new price event into the model (stragegy) -> retrieve a signal -> place an order -> get a trade execution -> update the portfolio`  

The only difference between backtesting and having the strategy live is that we don't send the orders to a real broker.
As a consequence we have to implement the order handling (orderbook) for different use cases and brokers. Note that some 
brokers might not support a specific order type and thus a local copy of the orderbook has to be kept in place.

This also means we have full control over all order during backtesting. We can place orders, cancel orders and use
limit orders as well as stop limit orders. Theoretically we could implement trailing stops and _if done_ order types as well. 
Ultimately we could implement volume checks and simulate partial execution. 

On the downside is that this way of backtesting is per definition not as fast as a simple matrix multiplication.

So why and when should you use django trade engine for your backtesting?
 * when you need full control over orders, place limit orders and be able to cancel orders
 * when you want to test strategies like market making
 * when you want to test portfolio construction using target weights in very realistic environment  
 * when you plan to use a reinforcement machine learning model
 * when you plan to use django trade engine to move the strategy into production (well we are far away from that atm)


#### Debugging
keep a database after a test completed:
 * inherit from django.test.SimpleTestCase
 * in settings.py define test db file path: `DATABASES.default.TEST`
 * use --keepdb flag: `./manage.py test trade_engine.tests.test_strategy.test_upfront_orders_strategy.TestUpfrontOrderStrategy.test_sma_strategy --keepdb`

profiling of performance issues:
 * https://github.com/jazzband/django-silk
