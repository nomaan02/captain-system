Search for Contracts

API URL:  POST  https://api.topstepx.com/api/Contract/search

API Reference:  /api/Contract/search

Description



Search for contracts. Note: The response returns up to 20 contracts at a time.

Parameters



Name

Type

Description

Required

Nullable

searchText

string

The name of the contract to search for.

Required

false

live

boolean

Whether to search for contracts using the sim/live data subscription.

Required

false

Example Usage



Example Request





cURL Request

curl -X 'POST' \  'https://api.topstepx.com/api/Contract/search' \  -H 'accept: text/plain' \  -H 'Content-Type: application/json' \  -d '{    "live": false,    "searchText": "NQ"  }'

Example Response





Success



Error

{  "contracts": [      {          "id": "CON.F.US.ENQ.U25",          "name": "NQU5",          "description": "E-mini NASDAQ-100: September 2025",          "tickSize": 0.25,          "tickValue": 5,          "activeContract": true,          "symbolId": "F.US.ENQ"      },      {          "id": "CON.F.US.MNQ.U25",          "name": "MNQU5",          "description": "Micro E-mini Nasdaq-100: September 2025",          "tickSize": 0.25,          "tickValue": 0.5,          "activeContract": true,          "symbolId": "F.US.MNQ"      },      {          "id": "CON.F.US.NQG.Q25",          "name": "QGQ5",          "description": "E-Mini Natural Gas: August 2025",          "tickSize": 0.005,          "tickValue": 12.5,          "activeContract": true,          "symbolId": "F.US.NQG"      },      {          "id": "CON.F.US.NQM.U25",          "name": "QMU5",          "description": "E-Mini Crude Oil: September 2025",          "tickSize": 0.025,          "tickValue": 12.5,          "activeContract": true,          "symbolId": "F.US.NQM"      }  ],  "success": true,  "errorCode": 0,  "errorMessage": null}

Search for Contract by Id

API URL:  POST  https://api.topstepx.com/api/Contract/searchById

API Reference:  /api/Contract/searchById

Description



Search for contracts.

Parameters



Name

Type

Description

Required

Nullable

contractId

string

The id of the contract to search for.

Required

false

Example Usage



Example Request





cURL Request

curl -X 'POST' \  'https://api.topstepx.com/api/Contract/searchById' \  -H 'accept: text/plain' \  -H 'Content-Type: application/json' \  -d '{    "contractId": "CON.F.US.ENQ.H25"  }'

Example Response





Success



Error

{  "contract": {      "id": "CON.F.US.ENQ.H25",      "name": "NQH5",      "description": "E-mini NASDAQ-100: March 2025",      "tickSize": 0.25,      "tickValue": 5,      "activeContract": false,      "symbolId": "F.US.ENQ"  },  "success": true,  "errorCode": 0,  "errorMessage": null}

List Available Contracts

API URL:  POST  https://api.topstepx.com/api/Contract/available

API Reference:  /api/Contract/available

Description



Lists available contracts based on the provided request parameters.

Parameters



Name

Type

Description

Required

Nullable

live

boolean

Whether to retrieve live contracts. This parameter is required and cannot be null.

Required

false

Example Usage



Example Request





cURL Request

curl -X 'POST' \  'https://api.topstepx.com/api/Contract/available' \  -H 'accept: text/plain' \  -H 'Content-Type: application/json' \  -d '{    "live": true  }'

Example Response





Success

{    "contracts": [        {            "id": "CON.F.US.BP6.U25",            "name": "6BU5",            "description": "British Pound (Globex): September 2025",            "tickSize": 0.0001,            "tickValue": 6.25,            "activeContract": true,            "symbolId": "F.US.BP6"        },        {            "id": "CON.F.US.CA6.U25",            "name": "6CU5",            "description": "Canadian Dollar (Globex): September 2025",            "tickSize": 0.00005,            "tickValue": 5,            "activeContract": true,            "symbolId": "F.US.CA6"        },        {            "id": "CON.F.US.DA6.U25",            "name": "6AU5",            "description": "Australian Dollar (Globex): September 2025",            "tickSize": 0.00005,            "tickValue": 5,            "activeContract": true,            "symbolId": "F.US.DA6"        },        {            "id": "CON.F.US.EEU.U25",            "name": "E7U5",            "description": "E-mini Euro FX: September 2025",            "tickSize": 0.0001,            "tickValue": 6.25,            "activeContract": true,            "symbolId": "F.US.EEU"        },        {            "id": "CON.F.US.EMD.U25",            "name": "EMDU5",            "description": "E-mini MidCap 400: September 2025",            "tickSize": 0.1,            "tickValue": 10,            "activeContract": true,            "symbolId": "F.US.EMD"        },        {            "id": "CON.F.US.ENQ.U25",            "name": "NQU5",            "description": "E-mini NASDAQ-100: September 2025",            "tickSize": 0.25,            "tickValue": 5,            "activeContract": true,            "symbolId": "F.US.ENQ"        },        {            "id": "CON.F.US.EP.U25",            "name": "ESU5",            "description": "E-Mini S&P 500: September 2025",            "tickSize": 0.25,            "tickValue": 12.5,            "activeContract": true,            "symbolId": "F.US.EP"        },        {            "id": "CON.F.US.EU6.U25",            "name": "6EU5",            "description": "Euro FX (Globex): September 2025",            "tickSize": 0.00005,            "tickValue": 6.25,            "activeContract": true,            "symbolId": "F.US.EU6"        },        {            "id": "CON.F.US.GF.Q25",            "name": "GFQ5",            "description": "Feeder Cattle (Globex): August 2025",            "tickSize": 0.025,            "tickValue": 12.5,            "activeContract": true,            "symbolId": "F.US.GF"        },        {            "id": "CON.F.US.GLE.Q25",            "name": "LEQ5",            "description": "Live Cattle (Globex): August 2025",            "tickSize": 0.025,            "tickValue": 10,            "activeContract": true,            "symbolId": "F.US.GLE"        },        {            "id": "CON.F.US.GMCD.U25",            "name": "MCDU5",            "description": "E-Micro CAD/USD: September 2025",            "tickSize": 0.0001,            "tickValue": 1,            "activeContract": true,            "symbolId": "F.US.GMCD"        },        {            "id": "CON.F.US.GMET.N25",            "name": "METN5",            "description": "Micro Ether: July 2025",            "tickSize": 0.5,            "tickValue": 0.05,            "activeContract": true,            "symbolId": "F.US.GMET"        },        {            "id": "CON.F.US.HE.Q25",            "name": "HEQ5",            "description": "Lean Hogs (Globex): August 2025",            "tickSize": 0.025,            "tickValue": 10,            "activeContract": true,            "symbolId": "F.US.HE"        },        {            "id": "CON.F.US.JY6.U25",            "name": "6JU5",            "description": "Japanese Yen (Globex): September 2025",            "tickSize": 0.0000005,            "tickValue": 6.25,            "activeContract": true,            "symbolId": "F.US.JY6"        },        {            "id": "CON.F.US.M2K.U25",            "name": "M2KU5",            "description": "Micro E-mini Russell 2000: September 2025",            "tickSize": 0.1,            "tickValue": 0.5,            "activeContract": true,            "symbolId": "F.US.M2K"        },        {            "id": "CON.F.US.M6A.U25",            "name": "M6AU5",            "description": "E-Micro AUD/USD: September 2025",            "tickSize": 0.0001,            "tickValue": 1,            "activeContract": true,            "symbolId": "F.US.M6A"        },        {            "id": "CON.F.US.M6B.U25",            "name": "M6BU5",            "description": "E-Micro GBP/USD: September 2025",            "tickSize": 0.0001,            "tickValue": 0.625,            "activeContract": true,            "symbolId": "F.US.M6B"        },        {            "id": "CON.F.US.M6E.U25",            "name": "M6EU5",            "description": "E-Micro EUR/USD: September 2025",            "tickSize": 0.0001,            "tickValue": 1.25,            "activeContract": true,            "symbolId": "F.US.M6E"        },        {            "id": "CON.F.US.MBT.N25",            "name": "MBTN5",            "description": "Micro Bitcoin: July 2025",            "tickSize": 5,            "tickValue": 0.5,            "activeContract": true,            "symbolId": "F.US.MBT"        },        {            "id": "CON.F.US.MES.U25",            "name": "MESU5",            "description": "Micro E-mini S&P 500: September 2025",            "tickSize": 0.25,            "tickValue": 1.25,            "activeContract": true,            "symbolId": "F.US.MES"        },        {            "id": "CON.F.US.MNQ.U25",            "name": "MNQU5",            "description": "Micro E-mini Nasdaq-100: September 2025",            "tickSize": 0.25,            "tickValue": 0.5,            "activeContract": true,            "symbolId": "F.US.MNQ"        },        {            "id": "CON.F.US.MX6.U25",            "name": "6MU5",            "description": "Mexican Peso (Globex): September 2025",            "tickSize": 0.00001,            "tickValue": 5,            "activeContract": true,            "symbolId": "F.US.MX6"        },        {            "id": "CON.F.US.NE6.U25",            "name": "6NU5",            "description": "New Zealand Dollar (Globex): September 2025",            "tickSize": 0.00005,            "tickValue": 5,            "activeContract": true,            "symbolId": "F.US.NE6"        },        {            "id": "CON.F.US.NKD.U25",            "name": "NKDU5",            "description": "Nikkei 225 (Globex): September 2025",            "tickSize": 5,            "tickValue": 25,            "activeContract": true,            "symbolId": "F.US.NKD"        },        {            "id": "CON.F.US.RTY.U25",            "name": "RTYU5",            "description": "E-mini Russell 2000: September 2025",            "tickSize": 0.1,            "tickValue": 5,            "activeContract": true,            "symbolId": "F.US.RTY"        },        {            "id": "CON.F.US.SF6.U25",            "name": "6SU5",            "description": "Swiss Franc (Globex): September 2025",            "tickSize": 0.00005,            "tickValue": 6.25,            "activeContract": true,            "symbolId": "F.US.SF6"        },        {            "id": "CON.F.US.SR3.Z25",            "name": "SR3Z5",            "description": "3 Month SOFR: December 2025",            "tickSize": 0.005,            "tickValue": 12.5,            "activeContract": true,            "symbolId": "F.US.SR3"        }    ],    "success": true,    "errorCode": 0,    "errorMessage": null}