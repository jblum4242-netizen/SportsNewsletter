from yahoofantasy import Context

ctx = Context()
yahoo_leagues = ctx.get_leagues('nfl', 2026)


for league in yahoo_leagues:
    print(f"🏆 Found Yahoo League: {league.name}")
    
    # Loop through all teams in the league to find your manager nickname
    for team in league.teams():
        print(f"📋 Team Name: {team.name} | Manager: {team.manager.nickname}")
        
        # Loop through the roster
        for player in team.players():
            print(f"   - {player.name.full} ({player.display_position})")