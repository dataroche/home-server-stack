# SETUP

1. Clear volumes
2. docker compose up
3. `docker compose exec postgres psql -U admin -d admin`
4. `ALTER USER telegraf WITH PASSWORD '...';`