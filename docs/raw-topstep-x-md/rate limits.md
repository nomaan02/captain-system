Rate Limits

Overview

The Gateway API employs a rate limiting system for all authenticated requests. Its goal is to promote fair usage, prevent abuse, and ensure the stability and reliability of the service, while clearly defining the level of performance clients can expect.

Rate Limit Table

Endpoint(s)

Limit

POST /api/History/retrieveBars

50 requests / 30 seconds

All other Endpoints

200 requests / 60 seconds

What Happens If You Exceed Rate Limits?

If you exceed the allowed rate limits, the API will respond with an HTTP  429 Too Many Requests  error. When this occurs, you should reduce your request frequency and try again after a short delay.

Search for Account

API URL:  POST  https://api.topstepx.com/api/Account/search

API Reference:  /api/Account/search

Description



Search for accounts.

Parameters



Name

Type

Description

Required

Nullable

onlyActiveAccounts

boolean

Whether to filter only active accounts.

Required

false

Example Usage



Example Request





cURL Request

curl -X 'undefined' \  'https://api.topstepx.com/api/Account/search' \  -H 'accept: text/plain' \  -H 'Content-Type: application/json'

Example Response





Success



Error

{  "accounts": [      {          "id": 1,          "name": "TEST_ACCOUNT_1",          "balance": 50000,          "canTrade": true,          "isVisible": true      }  ],  "success": true,  "errorCode": 0,  "errorMessage": null}         