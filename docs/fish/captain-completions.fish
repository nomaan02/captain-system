# Tab completions for the captain command
complete -c captain -f  # no file completions by default

# Subcommands
complete -c captain -n '__fish_use_subcommand' -a start   -d 'Light daily startup'
complete -c captain -n '__fish_use_subcommand' -a rebuild  -d 'Full heavy rebuild'
complete -c captain -n '__fish_use_subcommand' -a stop     -d 'Stop containers'
complete -c captain -n '__fish_use_subcommand' -a status   -d 'Health check (read-only)'
complete -c captain -n '__fish_use_subcommand' -a compact  -d 'Compact QuestDB tables'
complete -c captain -n '__fish_use_subcommand' -a update   -d 'Git pull + light rebuild'
complete -c captain -n '__fish_use_subcommand' -a logs     -d 'Tail container logs'
complete -c captain -n '__fish_use_subcommand' -a ps       -d 'Show container status'
complete -c captain -n '__fish_use_subcommand' -a restart  -d 'Rebuild single service'

# Flags for subcommands
complete -c captain -n '__fish_seen_subcommand_from start'   -l build -d 'Force image rebuild'
complete -c captain -n '__fish_seen_subcommand_from stop'    -l wipe  -d 'Remove volumes (destructive)'
complete -c captain -n '__fish_seen_subcommand_from rebuild' -l compact -d 'Compact only'
complete -c captain -n '__fish_seen_subcommand_from rebuild' -l status  -d 'Health check only'

# Service names for logs/restart
set -l __captain_services questdb redis captain-offline captain-online captain-command captain-gui nginx
complete -c captain -n '__fish_seen_subcommand_from logs'    -a "$__captain_services" -d 'Service'
complete -c captain -n '__fish_seen_subcommand_from restart' -a "$__captain_services" -d 'Service'
