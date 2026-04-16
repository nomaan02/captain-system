Market Data

Authorized users have access to order operations, allowing them to search for, modify, place, and cancel orders.

Retrieve Bars

API URL:  POST  https://api.topstepx.com/api/History/retrieveBars

API Reference:  /api/History/retrieveBars

Description



Retrieve bars.



Note:  The maximum number of bars that can be retrieved in a single request is  20,000.

Parameters



Name

Type

Description

Required

Nullable

contractId

integer

The contract ID.

Required

false

live

boolean

Whether to retrieve bars using the sim or live data subscription.

Required

false

startTime

datetime

The start time of the historical data.

Required

false

endTime

datetime

The end time of the historical data.

Required

false

unit

integer

The unit of aggregation for the historical data:
1  = Second
2  = Minute
3  = Hour
4  = Day
5  = Week
6  = Month

Required

false

unitNumber

integer

The number of units to aggregate.

Required

false

limit

integer

The maximum number of bars to retrieve.

Required

false

includePartialBar

boolean

Whether to include a partial bar representing the current time unit.

Required

false

Example Usage



Example Request





cURL Request

curl -X 'POST' \  'https://api.topstepx.com/api/History/retrieveBars' \  -H 'accept: text/plain' \  -H 'Content-Type: application/json' \  -d '{    "contractId": "CON.F.US.RTY.Z24",    "live": false,    "startTime": "2024-12-01T00:00:00Z",    "endTime": "2024-12-31T21:00:00Z",    "unit": 3,    "unitNumber": 1,    "limit": 7,    "includePartialBar": false  }'

Example Response





Success



Error

{    "bars": [        {            "t": "2024-12-20T14:00:00+00:00",            "o": 2208.100000000,            "h": 2217.000000000,            "l": 2206.700000000,            "c": 2210.100000000,            "v": 87        },        {            "t": "2024-12-20T13:00:00+00:00",            "o": 2195.800000000,            "h": 2215.000000000,            "l": 2192.900000000,            "c": 2209.800000000,            "v": 536        },        {            "t": "2024-12-20T12:00:00+00:00",            "o": 2193.600000000,            "h": 2200.300000000,            "l": 2192.000000000,            "c": 2198.000000000,            "v": 180        },        {            "t": "2024-12-20T11:00:00+00:00",            "o": 2192.200000000,            "h": 2194.800000000,            "l": 2189.900000000,            "c": 2194.800000000,            "v": 174        },        {            "t": "2024-12-20T10:00:00+00:00",            "o": 2200.400000000,            "h": 2200.400000000,            "l": 2191.000000000,            "c": 2193.100000000,            "v": 150        },        {            "t": "2024-12-20T09:00:00+00:00",            "o": 2205.000000000,            "h": 2205.800000000,            "l": 2198.900000000,            "c": 2200.500000000,            "v": 56        },        {            "t": "2024-12-20T08:00:00+00:00",            "o": 2207.700000000,            "h": 2210.100000000,            "l": 2198.100000000,            "c": 2204.900000000,            "v": 144        }    ],    "success": true,    "errorCode": 0,    "errorMessage": null}