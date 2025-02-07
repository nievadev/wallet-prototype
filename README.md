# Bare & Concise Wallet API
## Demonstrates power of Django + Django REST

For configuring, create .env file basing from .env-template

After you are set, run these commands:

```
$ make docker-build
$ make docker-up
$ make join-runserver
/code $ python manage.py migrate
/code $ make test
```

To test with postman, you will have to configure the DB creating a wallet and a user first. 

This API is only for:
- getting wallet data for user
- getting history of transactions
- requesting payment of total wallet available balance (for using this, configure in DB a WalletTransaction with status available first, so there's a balance greater than zero)