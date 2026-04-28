list of tweaks to amend


Issue 1:

- trades dont responsively mirror when they hit their TP or SL in the GUI dashboard - Have to open up topstepx and watch side by side for order fill confirmation.
signals appear in the signals panel, when you click on a signal you can see the meter between SL and TP actively moving up and down responsively - this is good
but when a tp or sl is hit, the signal card doesnt respond or provide any feedback that the order has been filled, and there is no record of the final PnL of the order. 
The signal should visually confirm that it has been filled, then remove itself from the signal list, and the tradelog panel at the top right of the gui should populate with the filled order detaisl - the entry, SL, TP and PnL, whether it was long or short and of course the asset. This list should persist across sessions and be loaded everytime the gui is launched.

potential support evidence:
unsure if this is related, but these user streams all return empty in the terminal, are these meant to be the order details form topstepx api? are they not being recieved or stored correctly for output?
captain-online-1  | [ONLINE] 2026-04-22 09:51:37,222 INFO __main__: UserStream ORDER: id=None status=None type=None
captain-online-1  | [ONLINE] 2026-04-22 09:51:37,223 INFO __main__: UserStream ORDER: id=None status=None type=None
captain-online-1  | [ONLINE] 2026-04-22 09:51:37,224 INFO __main__: UserStream ORDER: id=None status=None type=None
captain-online-1  | [ONLINE] 2026-04-22 09:51:37,233 INFO __main__: UserStream ORDER: id=None status=None type=None
captain-online-1  | [ONLINE] 2026-04-22 09:51:37,234 INFO __main__: UserStream TRADE: price=None pnl=None fees=None
captain-online-1  | [ONLINE] 2026-04-22 09:51:37,240 INFO __main__: UserStream POSITION: contract=None size=0 avgPrice=None
captain-online-1  | [ONLINE] 2026-04-22 09:51:37,250 INFO __main__: UserStream ACCOUNT: balance=None
captain-online-1  | [ONLINE] 2026-04-22 09:51:37,254 INFO __main__: UserStream ORDER: id=None status=None type=None
captain-online-1  | [ONLINE] 2026-04-22 09:51:37,256 INFO __main__: UserStream ORDER: id=None status=None type=None
captain-online-1  | [ONLINE] 2026-04-22 09:51:37,343 INFO captain_online.blocks.orchestrator: Position opened: MNQ for user primary_user (3 contracts)
captain-online-1  | [ONLINE] 2026-04-22 09:51:39,776 INFO __main__: UserStream ACCOUNT: balance=None
captain-online-1  | [ONLINE] 2026-04-22 09:52:07,014 WARNING captain_online.blocks.b7_position_monitor: ON-B7: Commission data missing for account 20319811 — notifying user
captain-online-1  | [ONLINE] 2026-04-22 09:52:07,037 INFO captain_online.blocks.b7_position_monitor: ON-B7: Published trade outcome TRD-1D81DE53A504 to stream
captain-online-1  | [ONLINE] 2026-04-22 09:52:07,038 INFO captain_online.blocks.b7_position_monitor: ON-B7: Position resolved — MNQ SL_HIT primary_user net_pnl=-3337.50 trade_id=TRD-1D81DE53A504
captain-online-1  | [ONLINE] 2026-04-22 09:52:08,063 INFO __main__: UserStream ORDER: id=None status=None type=None
captain-online-1  | [ONLINE] 2026-04-22 09:52:08,064 INFO __main__: UserStream TRADE: price=None pnl=None fees=None
captain-online-1  | [ONLINE] 2026-04-22 09:52:08,064 INFO __main__: UserStream TRADE: price=None pnl=None fees=None
captain-online-1  | [ONLINE] 2026-04-22 09:52:08,067 INFO __main__: UserStream POSITION: contract=None size=0 avgPrice=None
captain-online-1  | [ONLINE] 2026-04-22 09:52:08,075 INFO __main__: UserStream ACCOUNT: balance=None
captain-online-1  | [ONLINE] 2026-04-22 09:52:08,080 INFO __main__: UserStream ORDER: id=None status=None type=None
captain-online-1  | [ONLINE] 2026-04-22 09:52:08,988 INFO __main__: UserStream ACCOUNT: balance=None


---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

Issue 2:

not so much an issue, but would be useful to incorporate - but if a signal is generated and the signal doesn't appear in the dashboard because it is parity skipped, then the signal should still appear in the signals panel but with reduced opacity and overlaying text reading 'parity skip'
this is just to make it easier to see at a glance why some trades execute and some do not. 


---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

issue 3:

small one but the profit target should be set to $9000


---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

action 4:

need to validate full online flow against 33_P3_Online_Full_Pseudocode - in /context extract


---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

issue 5:





