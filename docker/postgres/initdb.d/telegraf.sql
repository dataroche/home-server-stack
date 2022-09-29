CREATE USER metrics_reader;
CREATE USER telegraf;

CREATE DATABASE metrics;


CREATE ROLE readaccess;
GRANT CONNECT ON DATABASE metrics TO readaccess;
GRANT USAGE ON SCHEMA public TO readaccess;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readaccess;


GRANT ALL PRIVILEGES ON DATABASE metrics TO telegraf;
GRANT readaccess TO metrics_reader;