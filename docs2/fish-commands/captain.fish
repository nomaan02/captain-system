function captain --description 'Captain System management commands'
    # Auto-detect project directory
    set -l captain_dir
    if set -q CAPTAIN_DIR
        set captain_dir $CAPTAIN_DIR
    else if test -d ~/captain-system
        set captain_dir ~/captain-system
    else
        echo "captain: cannot find captain-system directory" >&2
        echo "  Set CAPTAIN_DIR or ensure ~/captain-system exists" >&2
        return 1
    end

    set -l compose_cmd "docker compose -f docker-compose.yml -f docker-compose.local.yml"

    if test (count $argv) -eq 0
        echo "Usage: captain <command> [args]"
        echo ""
        echo "Commands:"
        echo "  start [--build]   Light daily startup (captain-start.sh)"
        echo "  rebuild           Full heavy rebuild (stop -> clean -> init -> bootstrap -> start)"
        echo "  stop [--wipe]     Stop containers (--wipe removes volumes)"
        echo "  status            Health check (read-only)"
        echo "  compact           Compact QuestDB state tables"
        echo "  update            Git pull + light rebuild (captain-update.sh)"
        echo "  logs [service]    Tail container logs"
        echo "  ps                Show container status"
        echo "  restart [svc]     Rebuild and restart a single service"
        return 0
    end

    switch $argv[1]
        case start
            bash $captain_dir/captain-start.sh $argv[2..]

        case rebuild
            bash $captain_dir/captain-rebuild.sh $argv[2..]

        case stop
            bash $captain_dir/captain-stop.sh $argv[2..]

        case status
            bash $captain_dir/captain-rebuild.sh --status

        case compact
            bash $captain_dir/captain-rebuild.sh --compact

        case update
            if test -f $captain_dir/scripts/captain-update.sh
                bash $captain_dir/scripts/captain-update.sh $argv[2..]
            else
                echo "captain: captain-update.sh not found" >&2
                return 1
            end

        case logs
            cd $captain_dir
            if test (count $argv) -gt 1
                eval $compose_cmd logs -f --tail 100 $argv[2..]
            else
                eval $compose_cmd logs -f --tail 50
            end

        case ps
            cd $captain_dir
            eval $compose_cmd ps

        case restart
            if test (count $argv) -lt 2
                echo "Usage: captain restart <service>" >&2
                echo "  Services: captain-offline captain-online captain-command captain-gui" >&2
                return 1
            end
            cd $captain_dir
            eval $compose_cmd up -d --build $argv[2]

        case '*'
            echo "captain: unknown command '$argv[1]'" >&2
            echo "  Run 'captain' for usage" >&2
            return 1
    end
end
