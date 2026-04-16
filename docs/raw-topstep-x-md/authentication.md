Authenticate (with API key)

We utilize JSON Web Tokens to authenticate all requests sent to the API. This process involves obtaining a session token, which is required for future requests.

Step 1

To begin, ensure you have the following:





An API key obtained from your firm. If you do not have these credentials, please contact your firm.



The connection URLs, obtained  here.

Step 2

API URL:  POST  https://api.topstepx.com/api/Auth/loginKey

API Reference:  /api/Auth/loginKey





cURL Request

curl -X 'POST' \  'https://api.topstepx.com/api/Auth/loginKey' \  -H 'accept: text/plain' \  -H 'Content-Type: application/json' \  -d '{    "userName": "string",    "apiKey": "string"  }'

Step 3

Process the API response, and make sure the result is Success (0), then store your session token in a safe place. This session token will grant full access to the Gateway API.





Response

{    "token": "your_session_token_here",    "success": true,    "errorCode": 0,    "errorMessage": null}



Previous

Authenticate



Authenticate (for authorized applications)

We utilize JSON Web Tokens to authenticate all requests sent to the API.

Step 1

Retrieve the admin credentials (username and password, appId, and verifyKey) that have been provided for your firm. You will need these credentials to authenticate with the API.

If you do not have these credentials, please contact your Account Manager for more information.

Step 2

API URL:  POST  https://api.topstepx.com/api/Auth/loginApp

API Reference:  /api/Auth/loginApp





cURL Request

curl -X 'POST' \  'https://api.topstepx.com/api/Auth/loginApp' \  -H 'accept: text/plain' \  -H 'Content-Type: application/json' \  -d '{    "userName": "yourUsername",    "password": "yourPassword",    "deviceId": "yourDeviceId",    "appId": "yourApplicationID",    "verifyKey": "yourVerifyKey"  }'

Step 3

Process the API response, and make sure the result is Success (0), then store your session token in a safe place. This session token will grant full access to the Gateway API.





Response

{    "token": "your_session_token_here",    "success": true,    "errorCode": 0,    "errorMessage": null}

Validate Session

Once you have successfully authenticated, session tokens are only valid for 24 hours.

If your token has expired, you must re-validate it to receive a new token.

Validate Token

API URL:  POST  https://api.topstepx.com/api/Auth/validate

API Reference:  /api/Auth/validate

To validate your token, you must make a  POST  request to the endpoint referenced above.





cURL



Response

curl -X 'POST' \  'https://api.topstepx.com/api/Auth/validate' \  -H 'accept: text/plain' \  -H 'Content-Type: application/json'





Response

{  "success": true,  "errorCode": 0,  "errorMessage": null,  "newToken": "NEW_TOKEN"}