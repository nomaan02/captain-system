Placing Your First Order

This documentation outlines the process for placing your first order using our API. To successfully execute an order, you must have an active trading account associated with your user. Follow the steps below to retrieve your account details, browse available contracts, and place your order.

Step 1

To initiate the order process, you must first retrieve a list of active accounts linked to your user. This step is essential for confirming your account status before placing an order.

API URL:  POST  https://api.topstepx.com/api/Account/search

API Reference:  /api/Account/search





Request



Response



cURL Request

{  "onlyActiveAccounts": true}       

Save the id of the account you want to use for placing orders. This will be used in Step 3.

Step 2

To place an order, you need to retrieve a list of available contracts. This step allows you to browse through the contracts that can be traded.

API URL:  POST  https://api.topstepx.com/api/Contract/available

API Reference:  /api/Contract/available





Request



Response



cURL Request

{  "live": false}

Save the id of the contract on which you would like to place an order. This will be used in Step 3.

Step 3

Now that you have the account ID and a list of available contracts, you can place your order. Use the following endpoint to submit your order request.

API URL:  POST  https://api.topstepx.com/api/Order/place

API Reference:  /api/Order/place





Request



Response



cURL Request

{  "accountId": 1, // Replace with your actual account ID  "contractId": "CON.F.US.BP6.U25", // Replace with the contract ID you want to trade  "type": 2, // Market order  "side": 1, // Ask   "size": 1 // Size of the order}

Example Response





Success



Error

{    "orderId": 9056,    "success": true,    "errorCode": 0,    "errorMessage": null}

Connection URLs

Connection Details:

API Endpoint:  https://api.topstepx.com

User Hub:  https://rtc.topstepx.com/hubs/user

Market Hub:  https://rtc.topstepx.com/hubs/market